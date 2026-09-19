import type { AdminRead } from "@pinjie/api-client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ConfigProvider } from "antd";
import zhCN from "antd/locale/zh_CN";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AdminContext } from "@/features/auth";
import { adminApi } from "@/lib/api/admin";
import { server } from "@/test/setup";
import { AccountSettingsPage } from "./AccountSettingsPage";

const mockAdmin: AdminRead = {
  id: "01900000-0000-7000-8000-000000000001",
  username: "settings-admin",
  display_name: "设置管理员",
  avatar: "https://example.com/avatar.png",
  is_active: true,
  is_superuser: true,
  roles: [{ id: "01900000-0000-7000-8000-000000000002", code: "super_admin", name: "超级管理组" }],
  permissions: ["users:read", "users:update"],
  created_at: "2026-08-24T00:00:00Z",
  updated_at: "2026-08-24T00:00:00Z",
};

function renderAccountSettingsPage(principal: AdminRead = mockAdmin) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <ConfigProvider locale={zhCN}>
      <QueryClientProvider client={client}>
        <AdminContext.Provider value={principal}>
          <AccountSettingsPage />
        </AdminContext.Provider>
      </QueryClientProvider>
    </ConfigProvider>,
  );
}

describe("AccountSettingsPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders base settings tab with admin information", () => {
    renderAccountSettingsPage(mockAdmin);
    expect(screen.getByText("个人设置")).toBeInTheDocument();
    expect(screen.getByText("基本设置")).toBeInTheDocument();
    expect(screen.getByText("安全设置")).toBeInTheDocument();
    expect(screen.getByDisplayValue("settings-admin")).toBeDisabled();
    expect(screen.getByDisplayValue("设置管理员")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "头像预览" })).toHaveAttribute("src", "https://example.com/avatar.png");
  });

  it("uploads an avatar and updates the form preview", async () => {
    const upload = vi.spyOn(adminApi, "uploadAsset").mockResolvedValue({
      id: "01900000-0000-7000-8000-000000000010",
      uploader_type: "admin",
      uploader_id: mockAdmin.id,
      storage_driver: "local",
      file_key: "avatar/20260825/avatar.png",
      original_name: "avatar.png",
      mime_type: "image/png",
      file_size: 16,
      file_hash: "a".repeat(64),
      url: "/static/uploads/avatar/20260825/avatar.png",
      scene: "avatar",
      created_at: "2026-08-25T00:00:00Z",
      updated_at: "2026-08-25T00:00:00Z",
    });
    const user = userEvent.setup();
    const { container } = renderAccountSettingsPage(mockAdmin);
    const input = container.querySelector<globalThis.HTMLInputElement>('input[type="file"]');
    expect(input).not.toBeNull();

    await user.upload(input!, new globalThis.File(["png-content"], "avatar.png", { type: "image/png" }));

    await waitFor(() => {
      expect(document.querySelector('img[src="/static/uploads/avatar/20260825/avatar.png"]')).not.toBeNull();
    });
    expect(upload).toHaveBeenCalledWith(expect.any(globalThis.File), "avatar");
  });

  it("submits profile update successfully", async () => {
    server.use(
      http.patch("http://localhost:3000/api/v1/admin/auth/profile", () =>
        HttpResponse.json({
          code: "OK",
          message: "个人资料已更新",
          data: { ...mockAdmin, display_name: "新昵称" },
        }),
      ),
    );

    const user = userEvent.setup();
    renderAccountSettingsPage(mockAdmin);

    const displayNameInput = screen.getByDisplayValue("设置管理员");
    await user.clear(displayNameInput);
    await user.type(displayNameInput, "新昵称");
    await user.click(screen.getByRole("button", { name: "更新基本信息" }));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "更新基本信息" })).toBeInTheDocument();
    });
  });

  it("blocks profile submission during upload and allows retry after upload failure", async () => {
    let rejectUpload: (error: Error) => void = () => { throw new Error("Upload not started"); };
    vi.spyOn(adminApi, "uploadAsset").mockImplementation(() => new Promise((_, reject) => { rejectUpload = reject; }));
    const save = vi.spyOn(adminApi, "updateProfile").mockRejectedValue(new Error("保留资料"));
    const user = userEvent.setup();
    const { container } = renderAccountSettingsPage();
    const input = container.querySelector<globalThis.HTMLInputElement>('input[type="file"]');
    if (!input) throw new Error("Missing upload input");
    await user.upload(input, new globalThis.File(["png"], "avatar.png", { type: "image/png" }));
    expect(screen.getByRole("button", { name: "更新基本信息" })).toBeDisabled();
    const form = input.closest("form");
    if (!form) throw new Error("Missing profile form");
    fireEvent.submit(form);
    await screen.findByText("头像正在上传，请完成后再保存");
    expect(save).not.toHaveBeenCalled();
    rejectUpload(new Error("上传失败"));
    await screen.findByText("上传失败");
    await waitFor(() => expect(screen.getByRole("button", { name: "更新基本信息" })).toBeEnabled());
    await user.click(screen.getByRole("button", { name: "更新基本信息" }));
    await waitFor(() => expect(save).toHaveBeenCalledTimes(1));
  });

  it("switches to security tab and renders password form and security metadata", async () => {
    renderAccountSettingsPage(mockAdmin);
    fireEvent.click(screen.getByText("安全设置"));

    expect(screen.getByText("修改账户密码")).toBeInTheDocument();
    expect(screen.getByLabelText("当前密码")).toBeInTheDocument();
    expect(screen.getByLabelText("新密码")).toBeInTheDocument();
    expect(screen.getByLabelText("确认新密码")).toBeInTheDocument();

    expect(screen.getByText("账号身份与安全信息")).toBeInTheDocument();
    expect(screen.getByText("超级管理员")).toBeInTheDocument();
    expect(screen.getByText("超级管理组")).toBeInTheDocument();
    expect(screen.getByText("2 项有效权限")).toBeInTheDocument();
  });

  it("changes the current password and resets the security form", async () => {
    let passwordPayload: unknown;
    server.use(
      http.post("http://localhost:3000/api/v1/admin/auth/password", async ({ request }) => {
        passwordPayload = await request.json();
        return HttpResponse.json({ code: "OK", message: "密码已更新", data: { completed: true } });
      }),
    );
    const user = userEvent.setup();
    renderAccountSettingsPage(mockAdmin);
    await user.click(screen.getByText("安全设置"));

    await user.type(screen.getByLabelText("当前密码"), "current-password");
    await user.type(screen.getByLabelText("新密码"), "replacement-password");
    await user.type(screen.getByLabelText("确认新密码"), "replacement-password");
    await user.click(screen.getByRole("button", { name: "修改密码" }));

    await waitFor(() => expect(passwordPayload).toEqual({
      current_password: "current-password",
      new_password: "replacement-password",
    }));
    await waitFor(() => expect(screen.getByLabelText("当前密码")).toHaveValue(""));
  });

  it("rejects mismatched password confirmation", async () => {
    const user = userEvent.setup();
    renderAccountSettingsPage(mockAdmin);
    await user.click(screen.getByText("安全设置"));

    await user.type(screen.getByLabelText("当前密码"), "current-password");
    await user.type(screen.getByLabelText("新密码"), "replacement-password");
    await user.type(screen.getByLabelText("确认新密码"), "different-password");
    await user.click(screen.getByRole("button", { name: "修改密码" }));

    expect(await screen.findByText("两次输入的新密码不一致")).toBeInTheDocument();
  });

  it("renders ordinary administrators without assigned roles", async () => {
    renderAccountSettingsPage({
      ...mockAdmin,
      is_superuser: false,
      roles: [],
      permissions: [],
    });
    fireEvent.click(screen.getByText("安全设置"));

    expect(await screen.findByText("普通管理员")).toBeInTheDocument();
    expect(screen.getByText("-")).toBeInTheDocument();
    expect(screen.getByText("0 项有效权限")).toBeInTheDocument();
  });
});
