import type { AdminRead, PermissionRead } from "@pinjie/api-client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ConfigProvider } from "antd";
import zhCN from "antd/locale/zh_CN";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";

import { afterEach, describe, expect, it, vi } from "vitest";

import { AdminsPage } from "./admins/AdminsPage";
import { AssetsPage } from "./assets/AssetsPage";
import { LoginPage } from "./auth/LoginPage";
import { AdminContext } from "./auth/auth-context";
import {
  RolesPage,
  buildPermissionTree,
  filterPermissionCodes,
  filterPermissionTree,
  mergeVisiblePermissionSelection,
  updatePermissionSelection,
} from "./roles/RolesPage";
import { SecurityPage } from "./security/SecurityPage";
import { UsersPage } from "./users/UsersPage";
import { server } from "../test/setup";
import { adminApi } from "@/lib/api/admin";

const now = "2026-08-15T00:00:00Z";
const current: AdminRead = { id: "01900000-0000-7000-8000-000000000001", username: "stage-admin", display_name: "Stage Admin", is_active: true, is_superuser: true, roles: [], permissions: [], created_at: now, updated_at: now };
const restricted: AdminRead = { ...current, id: "01900000-0000-7000-8000-000000000009", username: "read-only", display_name: "Read Only", is_superuser: false, permissions: ["users:read", "admins:read", "roles:read", "assets:read"] };
const otherAdmin: AdminRead = { ...current, id: "01900000-0000-7000-8000-000000000010", username: "other-admin", display_name: "Other Admin", avatar: "/static/uploads/avatar/other.png", is_superuser: false };

function renderPage(node: ReactNode, principal: AdminRead | null = current) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  window.history.replaceState({}, "", "/");
  return render(<ConfigProvider locale={zhCN}><QueryClientProvider client={client}>{principal ? <AdminContext.Provider value={principal}>{node}</AdminContext.Provider> : node}</QueryClientProvider></ConfigProvider>);
}

async function confirmWarning(user: ReturnType<typeof userEvent.setup>, title: string) {
  const titleElement = await screen.findByText(title);
  const dialog = titleElement.closest('[role="dialog"]');
  if (!(dialog instanceof globalThis.HTMLElement)) throw new Error(`警告标题“${title}”未处于对话框中`);
  expect(within(dialog).queryByLabelText("当前密码")).not.toBeInTheDocument();
  await user.click(within(dialog).getByRole("button", { name: /确\s*定/ }));
}

describe("stage C admin workspace", () => {
  afterEach(() => vi.restoreAllMocks());

  it("logs in with an accessible form", async () => {
    const user = userEvent.setup();
    renderPage(<LoginPage authenticated={false} />, null);
    await user.type(screen.getByLabelText("用户名"), "stage-admin");
    expect(screen.getByLabelText("密码")).toHaveAttribute("maxlength", "64");
    await user.type(screen.getByLabelText("密码"), "stage-c-admin-password");
    await user.click(screen.getByRole("button", { name: /登\s*录/ }));
    await waitFor(() => expect(screen.getByRole("button", { name: /登\s*录/ })).toBeEnabled());
  });

  it("redirects authenticated administrators away from the login page", () => {
    renderPage(<LoginPage authenticated />, null);
    expect(window.location.pathname).toBe("/welcome");
  });

  it("loads users and supports editing and session inspection", async () => {
    const user = userEvent.setup();
    renderPage(<UsersPage />);
    expect(await screen.findByText("Browser User")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /编辑/ }));
    const displayName = screen.getByLabelText("显示名称");
    await user.clear(displayName);
    await user.type(displayName, "Updated User");
    await user.click(screen.getByRole("button", { name: /保\s*存/ }));
    await waitFor(() => {
      const dialog = screen.queryByRole("dialog", { name: "编辑用户资料" });
      if (dialog) expect(dialog).not.toBeVisible();
      else expect(dialog).toBeNull();
    });
    await user.click(await screen.findByRole("button", { name: /会\s*话/ }));
    expect(await screen.findByText("暂无数据", { selector: "div" })).toBeVisible();
  });

  it("creates a user with an administrator supplied initial password", async () => {
    const user = userEvent.setup();
    let createPayload: unknown;
    server.use(
      http.post("http://localhost:3000/api/v1/admin/users", async ({ request }) => {
        createPayload = await request.json();
        return HttpResponse.json({
          code: "OK",
          message: "用户创建成功",
          data: {
            id: "01900000-0000-7000-8000-000000000011",
            username: "managed-user",
            display_name: "Managed User",
            email: "managed@example.com",
            is_active: false,
            created_at: now,
            updated_at: now,
            deleted_at: null,
            deleted_by_id: null,
            deleted_by_type: null,
            deletion_reason: null,
            can_restore: false,
          },
          request_id: "test-request",
        });
      }),
    );
    renderPage(<UsersPage />);

    expect(await screen.findByText("Browser User")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /新建用户/ }));
    await user.type(screen.getByLabelText("用户名"), "managed-user");
    await user.type(screen.getByLabelText("显示名称"), "Managed User");
    await user.type(screen.getByLabelText("邮箱"), "managed@example.com");
    await user.type(screen.getByLabelText("初始密码"), "initial-password");
    await user.type(screen.getByLabelText("确认初始密码"), "initial-password");
    await user.click(screen.getByRole("checkbox", { name: "允许登录" }));
    await user.click(screen.getByRole("button", { name: /创\s*建/ }));

    await waitFor(() => expect(createPayload).toEqual({
      username: "managed-user",
      display_name: "Managed User",
      email: "managed@example.com",
      initial_password: "initial-password",
      is_active: false,
    }));
  });

  it("executes user status, credential, and session operations without password confirmation", async () => {
    const user = userEvent.setup();
    let statusPayload: unknown;
    server.use(http.patch("http://localhost:3000/api/v1/admin/users/:id/status", async ({ request }) => {
      statusPayload = await request.json();
      return HttpResponse.json({ code: "OK", message: "操作成功", data: {}, request_id: "test-request" });
    }));
    renderPage(<UsersPage />);
    expect(await screen.findByText("Browser User")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "停用用户：browser-user" }));
    await waitFor(() => expect(statusPayload).toEqual({ is_active: false }));

    await user.click(screen.getByRole("button", { name: /重置密码/ }));
    expect(screen.getByLabelText("新密码")).toHaveAttribute("maxlength", "64");
    await user.type(screen.getByLabelText("新密码"), "replacement-password");
    await user.click(screen.getByRole("button", { name: /确\s*定/ }));

    await user.click(await screen.findByRole("button", { name: /会话/ }));
    expect(await screen.findByText("暂无数据", { selector: "div" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: /撤销全部/ }));
    expect(screen.queryByLabelText("当前密码")).not.toBeInTheDocument();
  }, 120_000);

  it("selects users and sends one atomic bulk soft-delete request", async () => {
    const user = userEvent.setup();
    let bulkPayload: unknown;
    server.use(
      http.delete("http://localhost:3000/api/v1/admin/users/batch", async ({ request }) => {
        bulkPayload = await request.json();
        return HttpResponse.json({
          code: "OK",
          message: "操作成功",
          data: { completed_count: 1, target_ids: ["01900000-0000-7000-8000-000000000002"] },
          request_id: "test-request",
        });
      }),
    );
    renderPage(<UsersPage />);

    expect(await screen.findByText("Browser User")).toBeInTheDocument();
    await user.click(screen.getByRole("checkbox", { name: /Select row/ }));
    expect(screen.getByText("已选择 1 项")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /批量删除/ }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("确认将 1 名用户移入回收站")).toBeInTheDocument();
    expect(within(dialog).getByLabelText("删除原因")).toBeInTheDocument();
    expect(bulkPayload).toBeUndefined();
    await user.click(within(dialog).getByRole("button", { name: /取\s*消/ }));
    expect(bulkPayload).toBeUndefined();
    expect(screen.getByText("已选择 1 项")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /批量删除/ }));
    await confirmWarning(user, "确认将 1 名用户移入回收站");

    await waitFor(() =>
      expect(bulkPayload).toEqual({ user_ids: ["01900000-0000-7000-8000-000000000002"], deletion_reason: null }),
    );
  }, 60_000);

  it.each(["single", "bulk"])("retains %s user deletion targets and reason on failure", async (mode) => {
    const user = userEvent.setup();
    let attempts = 0;
    let bulkPayload: unknown;
    server.use(
      http.delete("http://localhost:3000/api/v1/admin/users/batch", async ({ request }) => {
        attempts += 1;
        bulkPayload = await request.json();
        return attempts === 1
          ? HttpResponse.json({ code: "USER_STATE_CONFLICT", message: "用户状态已变更", request_id: "test-request" }, { status: 409 })
          : HttpResponse.json({ code: "OK", message: "操作成功", data: { completed_count: 1, target_ids: ["01900000-0000-7000-8000-000000000002"] }, request_id: "test-request" });
      }),
    );
    renderPage(<UsersPage />);
    await screen.findByText("Browser User");
    if (mode === "bulk") await user.click(screen.getByRole("checkbox", { name: /Select row/ }));
    await user.click(screen.getByRole("button", { name: mode === "bulk" ? /批量删除/ : /删\s*除/ }));
    const dialog = await screen.findByRole("dialog");
    const reason = within(dialog).getByLabelText("删除原因");
    await user.type(reason, "重复账户");
    expect(bulkPayload).toBeUndefined();
    await user.click(within(dialog).getByRole("button", { name: /确\s*定/ }));
    expect(await within(dialog).findByText("用户状态已变更")).toBeVisible();
    expect(reason).toHaveValue("重复账户");
    if (mode === "bulk") expect(screen.getByText("已选择 1 项")).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: /确\s*定/ }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(bulkPayload).toEqual({ user_ids: ["01900000-0000-7000-8000-000000000002"], deletion_reason: "重复账户" });
    if (mode === "bulk") expect(screen.queryByText("已选择 1 项")).not.toBeInTheDocument();
  }, 60_000);

  it("loads the recycle bin and sends one atomic bulk restore request", async () => {
    const user = userEvent.setup();
    let restorePayload: unknown;
    const ok = (data: unknown) => HttpResponse.json({ code: "OK", message: "操作成功", data, request_id: "test-request" });
    const deletedUser = {
      id: "01900000-0000-7000-8000-000000000002",
      username: "browser-user",
      display_name: "Browser User",
      email: "browser@example.test",
      is_active: false,
      created_at: now,
      updated_at: now,
      deleted_at: now,
      deleted_by_id: current.id,
      deleted_by_type: "admin",
      deletion_reason: "admin_deleted",
      can_restore: true,
    };
    server.use(
      http.get("http://localhost:3000/api/v1/admin/users", ({ request }) => {
        const lifecycle = new globalThis.URL(request.url).searchParams.get("lifecycle");
        return ok({
          items: lifecycle === "deleted" ? [deletedUser] : [],
          page: 1,
          page_size: 20,
          total: lifecycle === "deleted" ? 1 : 0,
          total_pages: lifecycle === "deleted" ? 1 : 0,
        });
      }),
      http.post("http://localhost:3000/api/v1/admin/users/restore/batch", async ({ request }) => {
        restorePayload = await request.json();
        return ok({ completed_count: 1, target_ids: [deletedUser.id] });
      }),
    );
    renderPage(<UsersPage />);

    await user.click(await screen.findByText("回收站"));
    expect(await screen.findByText("可恢复")).toBeInTheDocument();
    await user.click(screen.getByRole("checkbox", { name: /Select row/ }));
    await user.click(screen.getByRole("button", { name: /批量恢复/ }));

    await waitFor(() => expect(restorePayload).toEqual({ user_ids: [deletedUser.id] }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  }, 60_000);

  it("loads administrators and assigns roles directly", async () => {
    const user = userEvent.setup();
    server.use(http.get("http://localhost:3000/api/v1/admin/admins", () => HttpResponse.json({ code: "OK", message: "操作成功", data: { items: [otherAdmin], page: 1, page_size: 20, total: 1, total_pages: 1 }, request_id: "test-request" })));
    renderPage(<AdminsPage />);
    expect(await screen.findByText("Other Admin")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /角色/ }));
    expect(screen.getByText("分配角色")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /保\s*存/ }));
  }, 60_000);

  it("protects administrator status and session operations", async () => {
    const user = userEvent.setup();
    let statusPayload: unknown;
    server.use(
      http.get("http://localhost:3000/api/v1/admin/admins", () => HttpResponse.json({
        code: "OK",
        message: "操作成功",
        data: { items: [otherAdmin], page: 1, page_size: 20, total: 1, total_pages: 1 },
        request_id: "test-request",
      })),
      http.patch("http://localhost:3000/api/v1/admin/admins/:id/status", async ({ request }) => {
        statusPayload = await request.json();
        return HttpResponse.json({ code: "OK", message: "操作成功", data: { ...otherAdmin, is_active: false }, request_id: "test-request" });
      }),
    );
    renderPage(<AdminsPage />);
    expect(await screen.findByText("Other Admin")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "停用管理员：other-admin" }));
    await waitFor(() => expect(statusPayload).toEqual({ is_active: false }));
    await user.click(screen.getByRole("button", { name: /会\s*话/ }));
    expect(await screen.findByText("暂无数据", { selector: "div" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: /撤销全部/ }));
    expect(screen.queryByLabelText("当前密码")).not.toBeInTheDocument();
  }, 60_000);

  it("edits administrator avatar and display name", async () => {
    const user = userEvent.setup();
    let updatePayload: unknown;
    server.use(
      http.get("http://localhost:3000/api/v1/admin/admins", () => HttpResponse.json({ code: "OK", message: "操作成功", data: { items: [otherAdmin], page: 1, page_size: 20, total: 1, total_pages: 1 }, request_id: "test-request" })),
      http.patch("http://localhost:3000/api/v1/admin/admins/:id", async ({ request }) => {
        updatePayload = await request.json();
        return HttpResponse.json({ code: "OK", message: "操作成功", data: otherAdmin, request_id: "test-request" });
      }),
    );
    renderPage(<AdminsPage />);

    expect(await screen.findByRole("img", { name: "Other Admin的头像" })).toHaveAttribute("src", "/static/uploads/avatar/other.png");
    await user.click(screen.getByRole("button", { name: /编辑/ }));
    const displayName = screen.getByLabelText("显示名称");
    await user.clear(displayName);
    await user.type(displayName, "Updated Admin");
    await user.click(screen.getByRole("button", { name: "移除头像" }));
    const confirmation = await screen.findByRole("dialog", { name: "确认移除管理员“other-admin”的头像" });
    expect(updatePayload).toBeUndefined();
    await user.click(within(confirmation).getByRole("button", { name: /取\s*消/ }));
    expect(screen.getByRole("button", { name: "移除头像" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "移除头像" }));
    await confirmWarning(user, "确认移除管理员“other-admin”的头像");
    expect(updatePayload).toBeUndefined();
    await user.click(screen.getByRole("button", { name: /保\s*存/ }));

    await waitFor(() => expect(updatePayload).toEqual({ avatar: null, display_name: "Updated Admin" }));
  }, 60_000);

  it("switches administrator identity directly", async () => {
    const user = userEvent.setup();
    let updatePayload: unknown;
    server.use(
      http.get("http://localhost:3000/api/v1/admin/admins", () => HttpResponse.json({ code: "OK", message: "操作成功", data: { items: [otherAdmin], page: 1, page_size: 20, total: 1, total_pages: 1 }, request_id: "test-request" })),
      http.patch("http://localhost:3000/api/v1/admin/admins/:id/superuser", async ({ request }) => {
        updatePayload = await request.json();
        return HttpResponse.json({ code: "OK", message: "操作成功", data: { ...otherAdmin, is_superuser: true }, request_id: "test-request" });
      }),
    );
    renderPage(<AdminsPage />);

    await user.click(await screen.findByRole("button", { name: "设为超级管理员：other-admin" }));
    await waitFor(() => expect(updatePayload).toEqual({ is_superuser: true }));
  }, 60_000);

  it("keeps superuser grants read-only for ordinary administrators with update permission", async () => {
    const user = userEvent.setup();
    const ordinaryUpdater: AdminRead = {
      ...current,
      id: "01900000-0000-7000-8000-000000000011",
      username: "ordinary-updater",
      is_superuser: false,
      permissions: ["admins:read", "admins:create", "admins:update"],
    };
    server.use(http.get("http://localhost:3000/api/v1/admin/admins", () => HttpResponse.json({
      code: "OK",
      message: "操作成功",
      data: { items: [otherAdmin], page: 1, page_size: 20, total: 1, total_pages: 1 },
      request_id: "test-request",
    })));
    renderPage(<AdminsPage />, ordinaryUpdater);

    expect(await screen.findByText("Other Admin")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "设为超级管理员：other-admin" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /新建管理员/ }));
    expect(screen.queryByRole("checkbox", { name: "超级管理员" })).not.toBeInTheDocument();
  });

  it("prevents a regular administrator from operating a superuser", async () => {
    const protectedSuperuser: AdminRead = { ...otherAdmin, is_superuser: true };
    const ordinaryOperator: AdminRead = {
      ...restricted,
      permissions: [
        "admins:read",
        "admins:update",
        "admins:roles:assign",
        "admins:sessions:read",
        "admins:sessions:revoke",
        "admins:credentials:reset",
        "roles:read",
      ],
    };
    server.use(http.get("http://localhost:3000/api/v1/admin/admins", () => HttpResponse.json({
      code: "OK",
      message: "操作成功",
      data: { items: [protectedSuperuser], page: 1, page_size: 20, total: 1, total_pages: 1 },
      request_id: "test-request",
    })));

    renderPage(<AdminsPage />, ordinaryOperator);

    const protectedRow = (await screen.findByText("Other Admin")).closest("tr");
    if (!protectedRow) throw new Error("超级管理员所在表格行未渲染");
    expect(within(protectedRow).getByRole("button", { name: /编\s*辑/ })).toBeDisabled();
    expect(within(protectedRow).getByRole("button", { name: /角\s*色/ })).toBeDisabled();
    expect(within(protectedRow).getByRole("button", { name: /会\s*话/ })).toBeDisabled();
    expect(screen.queryByRole("button", { name: "停用管理员：other-admin" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "更多操作：other-admin" })).not.toBeInTheDocument();
    const rowCheckbox = document.querySelector('.ant-table-tbody input[type="checkbox"]');
    expect(rowCheckbox).toBeDisabled();
  });

  it("resets an administrator password from the more menu", async () => {
    const user = userEvent.setup();
    let resetPayload: unknown;
    server.use(
      http.get("http://localhost:3000/api/v1/admin/admins", () => HttpResponse.json({ code: "OK", message: "操作成功", data: { items: [otherAdmin], page: 1, page_size: 20, total: 1, total_pages: 1 }, request_id: "test-request" })),
      http.put("http://localhost:3000/api/v1/admin/admins/:id/credentials/password", async ({ request }) => {
        resetPayload = await request.json();
        return HttpResponse.json({ code: "OK", message: "操作成功", data: { completed: true }, request_id: "test-request" });
      }),
    );
    renderPage(<AdminsPage />);

    await user.click(await screen.findByRole("button", { name: "更多操作：other-admin" }));
    await user.click(await screen.findByRole("menuitem", { name: /重置密码/ }));
    await user.type(screen.getByLabelText("新密码"), "replacement-password");
    await user.type(screen.getByLabelText("确认新密码"), "replacement-password");
    await user.click(screen.getByRole("button", { name: /确\s*定/ }));

    await waitFor(() => expect(resetPayload).toEqual({ new_password: "replacement-password" }));
  }, 60_000);

  it("selects administrators and performs one atomic bulk status request", async () => {
    const user = userEvent.setup();
    const thirdAdmin: AdminRead = { ...otherAdmin, id: "01900000-0000-7000-8000-000000000011", username: "third-admin", display_name: "Third Admin" };
    let bulkPayload: unknown;
    server.use(
      http.get("http://localhost:3000/api/v1/admin/admins", () => HttpResponse.json({ code: "OK", message: "操作成功", data: { items: [current, otherAdmin, thirdAdmin], page: 1, page_size: 20, total: 3, total_pages: 1 }, request_id: "test-request" })),
      http.patch("http://localhost:3000/api/v1/admin/admins/status/batch", async ({ request }) => {
        bulkPayload = await request.json();
        return HttpResponse.json({ code: "OK", message: "操作成功", data: [otherAdmin, thirdAdmin], request_id: "test-request" });
      }),
    );
    renderPage(<AdminsPage />);

    expect(await screen.findByText("Third Admin")).toBeInTheDocument();
    const rowCheckboxes = screen.getAllByRole("checkbox", { name: /Select row/ });
    expect(rowCheckboxes[0]).toBeDisabled();
    const secondCheckbox = rowCheckboxes[1];
    const thirdCheckbox = rowCheckboxes[2];
    if (!secondCheckbox || !thirdCheckbox) throw new Error("批量选择列未完整渲染");
    await user.click(secondCheckbox);
    await user.click(thirdCheckbox);
    expect(screen.getByText("已选择 2 项")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /批量停用/ }));

    await waitFor(() => expect(bulkPayload).toEqual({ admin_ids: [otherAdmin.id, thirdAdmin.id], is_active: false }));
    expect(screen.getByRole("columnheader", { name: "操作" })).toHaveStyle({ whiteSpace: "nowrap" });
    expect(document.querySelector('col[style*="width: 1%"]')).not.toBeNull();
  }, 60_000);

  it("renders inactive records, empty fields, and active session details", async () => {
    const user = userEvent.setup();
    let roleStatusPayload: unknown;
    const inactiveUser = {
      id: "01900000-0000-7000-8000-000000000020",
      username: "inactive-user",
      display_name: null,
      email: null,
      is_active: false,
      created_at: now,
      updated_at: now,
    };
    const inactiveAdmin = {
      ...current,
      id: "01900000-0000-7000-8000-000000000021",
      username: "inactive-admin",
      display_name: null,
      is_active: false,
      is_superuser: false,
      roles: [{ id: "01900000-0000-7000-8000-000000000022", code: "auditors", name: "审计员" }],
    };
    const activeSession = { id: "01900000-0000-7000-8000-000000000023", device_name: null, ip_masked: null, last_seen_at: now, revoked_at: null };
    const revokedSession = { ...activeSession, id: "01900000-0000-7000-8000-000000000024", device_name: "旧设备", revoked_at: now };
    const ok = (data: unknown) => HttpResponse.json({ code: "OK", message: "操作成功", data, request_id: "test-request" });
    server.use(
      http.get("http://localhost:3000/api/v1/admin/users", () => ok({ items: [inactiveUser], page: 1, page_size: 20, total: 1, total_pages: 1 })),
      http.get("http://localhost:3000/api/v1/admin/users/:id/sessions", () => ok({ items: [activeSession, revokedSession], page: 1, page_size: 20, total: 2, total_pages: 1 })),
      http.post("http://localhost:3000/api/v1/admin/users/:id/sessions/revoke-all", () => ok({ completed: true })),
      http.get("http://localhost:3000/api/v1/admin/admins", () => ok({ items: [inactiveAdmin], page: 1, page_size: 20, total: 1, total_pages: 1 })),
      http.get("http://localhost:3000/api/v1/admin/admins/:id/sessions", () => ok({ items: [activeSession, revokedSession], page: 1, page_size: 20, total: 2, total_pages: 1 })),
      http.get("http://localhost:3000/api/v1/admin/roles", () => ok({ items: [{ id: "01900000-0000-7000-8000-000000000025", code: "auditors", name: "审计员", description: null, is_active: false, permissions: [], created_at: now, updated_at: now }], page: 1, page_size: 100, total: 1, total_pages: 1 })),
      http.patch("http://localhost:3000/api/v1/admin/roles/:id", async ({ request }) => {
        roleStatusPayload = await request.json();
        return ok({ id: "01900000-0000-7000-8000-000000000025", code: "auditors", name: "审计员", description: null, is_active: true, permissions: [], created_at: now, updated_at: now });
      }),
      http.get("http://localhost:3000/api/v1/admin/permissions", () => ok([{ id: "01900000-0000-7000-8000-000000000026", code: "users:read", name: "查看用户", description: null, is_active: false, catalog_version: "v1", assignable_to_roles: true }])),
    );

    const users = renderPage(<UsersPage />);
    expect((await screen.findAllByText("inactive-user")).length).toBeGreaterThan(0);
    expect(screen.getByText("停用", { selector: "span" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "启用用户：inactive-user" }));
    await user.click(screen.getByRole("button", { name: /会\s*话/ }));
    expect(await screen.findByText("旧设备")).toBeInTheDocument();
    expect(screen.getByText("未知设备")).toBeInTheDocument();
    expect(screen.getByText("已撤销")).toBeInTheDocument();
    users.unmount();

    const admins = renderPage(<AdminsPage />);
    expect((await screen.findAllByText("inactive-admin")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("审计员").length).toBeGreaterThan(0);
    await user.click(screen.getByRole("button", { name: "更多操作：inactive-admin" }));
    await user.click(await screen.findByRole("menuitem", { name: /启\s*用/ }));
    await user.click(screen.getByRole("button", { name: /会\s*话/ }));
    expect(await screen.findByText("旧设备")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /撤销全部/ }));
    admins.unmount();

    renderPage(<RolesPage />);
    expect(await screen.findByText("审计员")).toBeInTheDocument();
    expect(screen.getByText("停用")).toBeInTheDocument();
    expect(screen.getByText("0")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "启用角色：auditors" }));
    await waitFor(() => expect(roleStatusPayload).toEqual({ is_active: true }));
  }, 60_000);

  it("creates an administrator directly", async () => {
    const user = userEvent.setup();
    renderPage(<AdminsPage />);
    expect(await screen.findByText("Stage Admin")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "停用管理员：stage-admin" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /新建管理员/ }));
    await user.type(screen.getByLabelText("用户名"), "new-operator");
    expect(screen.getByLabelText("初始密码")).toHaveAttribute("maxlength", "64");
    await user.type(screen.getByLabelText("初始密码"), "new-operator-password");
    await user.click(screen.getByRole("button", { name: /保\s*存/ }));

  }, 60_000);

  it("rejects administrator passwords shorter than six characters", async () => {
    const user = userEvent.setup();
    renderPage(<AdminsPage />);
    expect(await screen.findByText("Stage Admin")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /新建管理员/ }));
    await user.type(screen.getByLabelText("用户名"), "new-operator");
    await user.type(screen.getByLabelText("初始密码"), "short");
    await user.click(screen.getByRole("button", { name: /保\s*存/ }));
    expect(await screen.findByText("密码必须为 6 至 64 个字符")).toBeInTheDocument();
  });

  it("groups the source-controlled permission catalog without losing unknown permissions", () => {
    const catalog: PermissionRead[] = [
      { id: "permission-users", code: "users:read", name: "查看用户", description: null, is_active: true, catalog_version: "v1", assignable_to_roles: true },
      { id: "permission-admins", code: "admins:read", name: "查看管理员", description: null, is_active: true, catalog_version: "v1", assignable_to_roles: true },
      { id: "permission-superuser", code: "admins:superuser:change", name: "设为超级管理员", description: null, is_active: true, catalog_version: "v1", assignable_to_roles: false },
      { id: "permission-roles", code: "roles:update", name: "修改角色", description: null, is_active: true, catalog_version: "v1", assignable_to_roles: true },
      { id: "permission-system", code: "system:overview:read", name: "查看系统概览", description: null, is_active: true, catalog_version: "v1", assignable_to_roles: true },
      { id: "permission-assets", code: "assets:delete", name: "删除文件资产", description: null, is_active: false, catalog_version: "v1", assignable_to_roles: true },
      { id: "permission-other", code: "reports:export", name: "导出报表", description: null, is_active: true, catalog_version: "v1", assignable_to_roles: true },
    ];

    const tree = buildPermissionTree(catalog);
    expect(tree.map((node) => node.label)).toEqual(["用户管理", "管理员管理", "角色与权限", "安全与系统", "文件资产", "其他权限"]);
    expect(tree.find((node) => node.label === "文件资产")?.children?.[0]).toMatchObject({ disabled: true, key: "assets:delete" });
    expect(tree.find((node) => node.label === "管理员管理")?.children?.find((node) => node.key === "admins:superuser:change")).toMatchObject({ disabled: true });
    expect(tree.find((node) => node.label === "其他权限")?.children?.[0]).toMatchObject({ key: "reports:export", searchText: expect.stringContaining("reports:export") });
    const filteredTree = filterPermissionTree(tree, "system:overview");
    expect(filteredTree).toMatchObject([{ label: "安全与系统", children: [{ key: "system:overview:read" }] }]);
    expect(filterPermissionTree(tree, "角色与权限").find((node) => node.label === "角色与权限")?.children).toHaveLength(1);
    expect(filterPermissionCodes(["users:read", "__permission_group__:users", "users:read", "missing:read"], catalog)).toEqual(["users:read"]);
    expect(filterPermissionCodes(["admins:superuser:change"], catalog)).toEqual([]);
    expect(mergeVisiblePermissionSelection(["system:overview:read"], ["users:read"], filteredTree, catalog)).toEqual([
      "users:read",
      "system:overview:read",
    ]);
    expect(updatePermissionSelection("all", ["assets:delete"], catalog)).toEqual([
      "assets:delete",
      "users:read",
      "admins:read",
      "roles:update",
      "system:overview:read",
      "reports:export",
    ]);
    expect(updatePermissionSelection("invert", ["users:read", "assets:delete"], catalog)).toEqual([
      "assets:delete",
      "admins:read",
      "roles:update",
      "system:overview:read",
      "reports:export",
    ]);
    expect(updatePermissionSelection("clear", ["users:read", "assets:delete"], catalog)).toEqual(["assets:delete"]);
  });

  it("shows the permission tree directly and supports search and bulk selection", async () => {
    const user = userEvent.setup();
    let assignPayload: unknown;
    const catalog: PermissionRead[] = [
      { id: "permission-users", code: "users:read", name: "查看用户", description: null, is_active: true, catalog_version: "v1", assignable_to_roles: true },
      { id: "permission-superuser", code: "admins:superuser:change", name: "设为超级管理员", description: null, is_active: true, catalog_version: "v1", assignable_to_roles: false },
      { id: "permission-roles", code: "roles:update", name: "修改角色", description: null, is_active: true, catalog_version: "v1", assignable_to_roles: true },
      { id: "permission-system", code: "system:overview:read", name: "查看系统概览", description: null, is_active: true, catalog_version: "v1", assignable_to_roles: true },
      { id: "permission-assets", code: "assets:delete", name: "删除文件资产", description: null, is_active: false, catalog_version: "v1", assignable_to_roles: true },
      { id: "permission-other", code: "reports:export", name: "导出报表", description: null, is_active: true, catalog_version: "v1", assignable_to_roles: true },
    ];
    server.use(
      http.get("http://localhost:3000/api/v1/admin/permissions", () => HttpResponse.json({ code: "OK", message: "操作成功", data: catalog, request_id: "test-request" })),
      http.put("http://localhost:3000/api/v1/admin/roles/:id/permissions", async ({ request }) => {
        assignPayload = await request.json();
        return HttpResponse.json({ code: "OK", message: "操作成功", data: {}, request_id: "test-request" });
      }),
    );
    renderPage(<RolesPage />);
    expect(await screen.findByText("运营人员")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /权限/ }));
    expect(await screen.findByRole("tree")).toBeInTheDocument();
    expect(screen.getByText("查看用户")).toBeInTheDocument();
    expect(await screen.findByText("用户管理")).toBeInTheDocument();
    expect(screen.getAllByText("角色与权限").length).toBeGreaterThan(0);
    expect(screen.getByText("其他权限")).toBeInTheDocument();
    expect(screen.getByText("删除文件资产").closest('[role="treeitem"]')).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByText((_, element) => element?.textContent?.replaceAll(" ", "") === "已选1/4")).toBeInTheDocument();

    const permissionSearch = screen.getByLabelText("搜索权限");
    await user.type(permissionSearch, "system:overview:read");
    expect(await screen.findByText("查看系统概览")).toBeInTheDocument();
    expect(screen.queryByText("查看用户")).not.toBeInTheDocument();
    await user.clear(permissionSearch);
    await user.click(screen.getByRole("button", { name: /反选/ }));
    expect(screen.getByText((_, element) => element?.textContent?.replaceAll(" ", "") === "已选3/4")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "收起全部权限分组" }));
    await user.click(screen.getByRole("button", { name: "展开全部权限分组" }));
    await user.click(screen.getByRole("button", { name: /保\s*存/ }));

    await waitFor(() => expect(assignPayload).toEqual({ permission_codes: ["roles:update", "system:overview:read", "reports:export"] }));
  }, 60_000);

  it("prevents permission writes until the catalog is available and preserves assigned permissions", async () => {
    let fail = true;
    server.use(http.get("http://localhost:3000/api/v1/admin/permissions", () => fail
      ? HttpResponse.json({ code: "SERVICE_UNAVAILABLE", message: "权限目录不可用" }, { status: 503 })
      : HttpResponse.json({ data: [{ id: "read", code: "users:read", name: "查看用户", is_active: true, assignable_to_roles: true }] })));
    const assign = vi.spyOn(adminApi, "assignPermissions");
    const user = userEvent.setup();
    renderPage(<RolesPage />);
    await screen.findByText("运营人员");
    await user.click(screen.getByRole("button", { name: /权限/ }));
    const dialog = await screen.findByRole("dialog", { name: "配置 运营人员 的权限" });
    await within(dialog).findByText("权限目录不可用");
    expect(within(dialog).getByRole("button", { name: /保\s*存/ })).toBeDisabled();
    const form = dialog.querySelector("form");
    if (!form) throw new Error("Missing permission form");
    fireEvent.submit(form);
    await within(dialog).findByText("权限目录尚未成功加载，请重试后保存");
    expect(assign).not.toHaveBeenCalled();
    fail = false;
    await user.click(within(dialog).getByRole("button", { name: /重\s*试/ }));
    await waitFor(() => expect(within(dialog).getByRole("button", { name: /保\s*存/ })).toBeEnabled());
    await user.click(within(dialog).getByRole("button", { name: /保\s*存/ }));
    await waitFor(() => expect(assign).toHaveBeenCalledWith("01900000-0000-7000-8000-000000000003", ["users:read"]));
  });

  it("loads the next role page and clears the previous selection", async () => {
    const pages: number[] = [];
    server.use(http.get("http://localhost:3000/api/v1/admin/roles", ({ request }) => {
      const page = Number(new globalThis.URL(request.url).searchParams.get("page"));
      pages.push(page);
      return HttpResponse.json({ data: { items: [{ id: `role-${page}`, code: `role_${page}`, name: `角色页${page}`, description: null, is_active: true, permissions: [], created_at: now, updated_at: now }], page, page_size: 100, total: 101, total_pages: 2 } });
    }));
    const user = userEvent.setup();
    renderPage(<RolesPage />);
    await screen.findByText("角色页1");
    await user.click(screen.getByRole("checkbox", { name: /Select row/ }));
    expect(screen.getByText("已选择 1 项")).toBeInTheDocument();
    await user.click(screen.getByTitle("2"));
    expect(await screen.findByText("角色页2")).toBeInTheDocument();
    expect(pages).toEqual([1, 2]);
    expect(screen.queryByText("已选择 1 项")).not.toBeInTheDocument();
  });

  it("selects roles and sends one atomic bulk hard-delete request", async () => {
    const user = userEvent.setup();
    let bulkPayload: unknown;
    server.use(
      http.delete("http://localhost:3000/api/v1/admin/roles/batch", async ({ request }) => {
        bulkPayload = await request.json();
        return HttpResponse.json({
          code: "OK",
          message: "操作成功",
          data: { completed_count: 1, target_ids: ["01900000-0000-7000-8000-000000000003"] },
          request_id: "test-request",
        });
      }),
    );
    renderPage(<RolesPage />);

    expect(await screen.findByText("运营人员")).toBeInTheDocument();
    await user.click(screen.getByRole("checkbox", { name: /Select row/ }));
    expect(screen.getByText("已选择 1 项")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /批量删除/ }));
    await confirmWarning(user, "确认批量删除 1 个角色");

    await waitFor(() =>
      expect(bulkPayload).toEqual({ role_ids: ["01900000-0000-7000-8000-000000000003"] }),
    );
  }, 60_000);

  it("creates and edits source-controlled roles", async () => {
    const user = userEvent.setup();
    renderPage(<RolesPage />);
    expect(await screen.findByText("运营人员")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /新建角色/ }));
    await user.type(screen.getByLabelText("角色代码"), "auditors");
    await user.type(screen.getByLabelText("名称"), "审计员");
    await user.click(screen.getByRole("button", { name: /保\s*存/ }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "新建角色" })).not.toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: /编辑/ }));
    const dialog = await screen.findByRole("dialog", { name: "编辑角色" });
    const name = within(dialog).getByLabelText("名称");
    await user.clear(name);
    await user.type(name, "运营管理员");
    await user.click(within(dialog).getByRole("button", { name: /保\s*存/ }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "编辑角色" })).not.toBeInTheDocument());
  }, 60_000);

  it("switches between login, audit, and request metadata logs", async () => {
    const user = userEvent.setup();
    renderPage(<SecurityPage />);
    expect((await screen.findAllByText("成功")).length).toBeGreaterThan(0);
    await user.click(screen.getByRole("tab", { name: "审计事件" }));
    expect(await screen.findByText("users:update")).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "请求元数据" }));
    expect(await screen.findByText("/api/v1/users/me")).toBeInTheDocument();
  });

  it("renders denied login, in-progress audit, and failed request states", async () => {
    const ok = (data: unknown) => HttpResponse.json({ code: "OK", message: "操作成功", data, request_id: "test-request" });
    server.use(
      http.get("http://localhost:3000/api/v1/admin/security/login-events", () => ok({ items: [{ id: "01900000-0000-7000-8000-000000000015", principal_type: "admin", principal_id: null, event_type: "login", succeeded: false, reason_code: "invalid_credentials", ip_address: null, user_agent_summary: null, request_id: "test-request", occurred_at: now }], page: 1, page_size: 20, total: 1, total_pages: 1 })),
      http.get("http://localhost:3000/api/v1/admin/security/audit-events", () => ok({ items: [{ id: "01900000-0000-7000-8000-000000000016", actor_id: current.id, action: "roles:update", target_type: "role", target_id: null, result: "started", changed_fields: {}, request_id: "test-request", occurred_at: now, completed_at: null }], page: 1, page_size: 20, total: 1, total_pages: 1 })),
      http.get("http://localhost:3000/api/v1/admin/system/request-logs", () => ok({ items: [{ id: "01900000-0000-7000-8000-000000000017", request_id: "test-request", trace_id: "test-trace", method: "POST", route_template: "/api/v1/admin/roles", status_code: 500, duration_ms: 12, principal_type: "admin", release_version: "test", occurred_at: now, request_body: '{"password":"***"}' }], page: 1, page_size: 20, total: 1, total_pages: 1 })),
    );
    const user = userEvent.setup();
    renderPage(<SecurityPage />);
    expect(await screen.findByText("拒绝")).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "审计事件" }));
    expect(await screen.findByText("处理中")).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "请求元数据" }));
    expect(await screen.findByText("500")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "查看入参" }));
    expect(await screen.findByText('{"password":"***"}')).toBeInTheDocument();
  });

  it("explains when request metadata logging is disabled", async () => {
    server.use(http.get("http://localhost:3000/api/v1/admin/system/request-logs", () => HttpResponse.json({ code: "REQUEST_LOG_DISABLED", message: "请求日志功能已关闭", details: null, request_id: "test-request" }, { status: 409 })));
    const user = userEvent.setup();
    renderPage(<SecurityPage />);
    await user.click(screen.getByRole("tab", { name: "请求元数据" }));
    expect(await screen.findByText("请求元数据日志当前未启用")).toBeInTheDocument();
  });

  it("loads file assets and applies filename, scene, and uploader filters", async () => {
    const user = userEvent.setup();
    const matchMedia = vi.spyOn(window, "matchMedia").mockImplementation((query) => ({
      matches: query.includes("min-width"),
      media: query,
      onchange: null,
      addListener: () => undefined,
      removeListener: () => undefined,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      dispatchEvent: () => false,
    }));
    let lastQuery = "";
    server.use(
      http.get("http://localhost:3000/api/v1/assets", ({ request }) => {
        lastQuery = new globalThis.URL(request.url).search;
        return HttpResponse.json({
          code: "OK",
          message: "操作成功",
          data: {
            items: [{
              id: "01900000-0000-7000-8000-000000000008",
              uploader_type: "admin",
              uploader_id: current.id,
              storage_driver: "local",
              file_key: "product/catalog-cover.png",
              original_name: "catalog-cover.png",
              mime_type: "image/png",
              file_size: 2048,
              file_hash: "a".repeat(64),
              url: "/static/uploads/product/catalog-cover.png",
              scene: "product",
              created_at: now,
              updated_at: now,
            }],
            page: 1,
            page_size: 20,
            total: 1,
            total_pages: 1,
          },
          request_id: "test-request",
        });
      }),
    );
    renderPage(<AssetsPage />);

    expect(await screen.findByText("catalog-cover.png")).toBeInTheDocument();
    expect(screen.queryByText(current.id)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /复制上传主体 ID/ }));
    expect(await screen.findByText("上传主体 ID 已复制")).toBeInTheDocument();
    await user.type(screen.getByLabelText("搜索文件名"), "catalog{Enter}");
    const sceneSelector = screen.getByLabelText("筛选使用场景").closest(".ant-select");
    if (!(sceneSelector instanceof globalThis.HTMLElement)) throw new Error("使用场景筛选控件未完整渲染");
    fireEvent.mouseDown(sceneSelector);
    await user.click(await screen.findByText("商品", { selector: ".ant-select-item-option-content" }));
    const uploaderSelector = screen.getByLabelText("筛选上传主体").closest(".ant-select");
    if (!(uploaderSelector instanceof globalThis.HTMLElement)) throw new Error("上传主体筛选控件未完整渲染");
    fireEvent.mouseDown(uploaderSelector);
    await user.click(await screen.findByText("管理员", { selector: ".ant-select-item-option-content" }));

    await waitFor(() => {
      const params = new URLSearchParams(lastQuery);
      expect(params.get("search")).toBe("catalog");
      expect(params.get("scene")).toBe("product");
      expect(params.get("uploader_type")).toBe("admin");
    });
    await user.click(screen.getByRole("button", { name: /重置/ }));
    await waitFor(() => {
      const params = new URLSearchParams(lastQuery);
      expect(params.get("search")).toBeNull();
      expect(params.get("scene")).toBeNull();
      expect(params.get("uploader_type")).toBeNull();
    });
    matchMedia.mockRestore();
  }, 60_000);

  it("previews image assets in place and keeps other files opening in a new tab", async () => {
    const user = userEvent.setup();
    server.use(
      http.get("http://localhost:3000/api/v1/assets", () => HttpResponse.json({
        code: "OK",
        message: "操作成功",
        data: {
          items: [
            {
              id: "01900000-0000-7000-8000-000000000008",
              uploader_type: "admin",
              uploader_id: current.id,
              storage_driver: "local",
              file_key: "product/catalog-cover.png",
              original_name: "catalog-cover.png",
              mime_type: "image/png",
              file_size: 2048,
              file_hash: "a".repeat(64),
              url: "/static/uploads/product/catalog-cover.png",
              scene: "product",
              created_at: now,
              updated_at: now,
            },
            {
              id: "01900000-0000-7000-8000-000000000011",
              uploader_type: "admin",
              uploader_id: current.id,
              storage_driver: "local",
              file_key: "document/guide.pdf",
              original_name: "guide.pdf",
              mime_type: "application/pdf",
              file_size: 4096,
              file_hash: "b".repeat(64),
              url: "/static/uploads/document/guide.pdf",
              scene: "document",
              created_at: now,
              updated_at: now,
            },
          ],
          page: 1,
          page_size: 20,
          total: 2,
          total_pages: 1,
        },
        request_id: "test-request",
      })),
    );
    renderPage(<AssetsPage />);

    expect(await screen.findByText("guide.pdf")).toBeInTheDocument();
    const imageOpen = screen.getByRole("button", { name: /打\s*开/ });
    const documentOpen = screen.getByRole("link", { name: /打\s*开/ });
    expect(documentOpen).toHaveAttribute("href", "/static/uploads/document/guide.pdf");
    expect(documentOpen).toHaveAttribute("target", "_blank");

    await user.click(imageOpen);
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
  }, 60_000);

  it("handles compact assets, copy failures, pagination, and single deletion", async () => {
    const user = userEvent.setup();
    const matchMedia = vi.spyOn(window, "matchMedia").mockImplementation((query) => ({
      matches: query.includes("min-width"),
      media: query,
      onchange: null,
      addListener: () => undefined,
      removeListener: () => undefined,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      dispatchEvent: () => false,
    }));
    let lastPage = "";
    let deletedAssetId = "";
    server.use(
      http.get("http://localhost:3000/api/v1/assets", ({ request }) => {
        lastPage = new globalThis.URL(request.url).searchParams.get("page") ?? "";
        return HttpResponse.json({
          code: "OK",
          message: "操作成功",
          data: {
            items: [
              {
                id: "01900000-0000-7000-8000-000000000030",
                uploader_type: "system",
                uploader_id: null,
                storage_driver: "local",
                file_key: "temp/tiny.txt",
                original_name: "tiny.txt",
                mime_type: "text/plain",
                file_size: 512,
                file_hash: "c".repeat(64),
                url: "/static/uploads/temp/tiny.txt",
                scene: "temp",
                created_at: now,
                updated_at: now,
              },
              {
                id: "01900000-0000-7000-8000-000000000031",
                uploader_type: "admin",
                uploader_id: current.id,
                storage_driver: "local",
                file_key: "document/archive.zip",
                original_name: "archive.zip",
                mime_type: "application/zip",
                file_size: 2 * 1024 * 1024,
                file_hash: "d".repeat(64),
                url: "/static/uploads/document/archive.zip",
                scene: "document",
                created_at: now,
                updated_at: now,
              },
            ],
            page: Number(lastPage),
            page_size: 20,
            total: 21,
            total_pages: 2,
          },
          request_id: "test-request",
        });
      }),
      http.delete("http://localhost:3000/api/v1/assets/:id", ({ params }) => {
        deletedAssetId = String(params.id);
        return HttpResponse.json({ code: "OK", message: "操作成功", data: true, request_id: "test-request" });
      }),
    );
    vi.spyOn(globalThis.navigator.clipboard, "writeText").mockRejectedValueOnce(new Error("clipboard denied"));
    renderPage(<AssetsPage />);

    expect(await screen.findByText(/512 B/)).toBeInTheDocument();
    expect(screen.getByText(/2\.0 MB/)).toBeInTheDocument();
    expect(screen.getByText("系统任务")).toBeInTheDocument();
    const tinyRow = screen.getByRole("row", { name: /tiny\.txt/ });
    await user.click(within(tinyRow).getByRole("button", { name: /复制地址/ }));
    expect(await screen.findByText("clipboard denied")).toBeInTheDocument();
    await user.click(within(tinyRow).getByRole("button", { name: /删除/ }));
    await confirmWarning(user, "永久删除文件“tiny.txt”");
    await waitFor(() => expect(deletedAssetId).toBe("01900000-0000-7000-8000-000000000030"));

    await user.click(screen.getByTitle("下一页"));
    await waitFor(() => expect(lastPage).toBe("2"));
    matchMedia.mockRestore();
  }, 60_000);

  it("selects assets and sends one atomic bulk hard-delete request", async () => {
    const user = userEvent.setup();
    let bulkPayload: unknown;
    server.use(
      http.delete("http://localhost:3000/api/v1/assets/batch", async ({ request }) => {
        bulkPayload = await request.json();
        return HttpResponse.json({
          code: "OK",
          message: "操作成功",
          data: { completed_count: 1, target_ids: ["01900000-0000-7000-8000-000000000008"] },
          request_id: "test-request",
        });
      }),
    );
    renderPage(<AssetsPage />);

    expect(await screen.findByText("catalog-cover.png")).toBeInTheDocument();
    await user.click(screen.getByRole("checkbox", { name: /Select row/ }));
    expect(screen.getByText("已选择 1 项")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "取消选择" }));
    expect(screen.queryByText("已选择 1 项")).not.toBeInTheDocument();
    await user.click(screen.getByRole("checkbox", { name: /Select row/ }));
    await user.click(screen.getByRole("button", { name: /批量删除/ }));
    await confirmWarning(user, "确认批量删除 1 个文件资产");

    await waitFor(() =>
      expect(bulkPayload).toEqual({ asset_ids: ["01900000-0000-7000-8000-000000000008"] }),
    );
  }, 60_000);

  it("hides mutation controls from read-only administrators", async () => {
    const users = renderPage(<UsersPage />, restricted);
    expect(await screen.findByText("Browser User")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /新建用户|编辑|停用|会话|重置密码/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    users.unmount();

    const admins = renderPage(<AdminsPage />, restricted);
    expect(await screen.findByText("Stage Admin")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /新建管理员|编辑|角色|更多操作|会话/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /启用管理员|停用管理员/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    admins.unmount();

    const roles = renderPage(<RolesPage />, restricted);
    expect(await screen.findByText("运营人员")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /新建角色|编辑|权限|删除/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /启用角色|停用角色/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    roles.unmount();

    renderPage(<AssetsPage />, restricted);
    expect(await screen.findByText("catalog-cover.png")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /删除|批量删除/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  }, 60_000);
});
