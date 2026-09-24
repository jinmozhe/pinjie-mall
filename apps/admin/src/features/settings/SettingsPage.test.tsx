import type { AdminRead, AdminSiteSettingRead } from "@pinjie/api-client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App, ConfigProvider } from "antd";
import zhCN from "antd/locale/zh_CN";
import { http, HttpResponse } from "msw";

import { afterEach, describe, expect, it, vi } from "vitest";

import { AdminContext } from "@/features/auth";
import { adminApi } from "@/lib/api/admin";
import { server } from "@/test/setup";
import { SettingsPage } from "./SettingsPage";

const now = "2026-08-29T08:00:00Z";
const admin: AdminRead = {
  id: "01900000-0000-7000-8000-000000000001",
  username: "settings-admin",
  display_name: "设置管理员",
  is_active: true,
  is_superuser: true,
  roles: [],
  permissions: [],
  created_at: now,
  updated_at: now,
};
const siteSetting: AdminSiteSettingRead = {
  name: "品界",
  logo: {
    url: "/static/settings/site/logo.png?v=1",
    mime_type: "image/png",
    file_size: 128,
  },
  title: "品界网络科技",
  keywords: ["品界", "网络科技"],
  description: "可靠的数字产品与服务",
  revision: 1,
  updated_at: now,
  updated_by: { id: admin.id, display_name: admin.display_name },
};

const ok = <T,>(data: T) =>
  HttpResponse.json({ code: "OK", message: "操作成功", data, request_id: "test-request" });

function renderSettingsPage(principal: AdminRead = admin, client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })) {
  return render(
    <ConfigProvider locale={zhCN}>
      <App>
        <QueryClientProvider client={client}>
          <AdminContext.Provider value={principal}>
            <SettingsPage />
          </AdminContext.Provider>
        </QueryClientProvider>
      </App>
    </ConfigProvider>,
  );
}

describe("SettingsPage", () => {
  afterEach(() => vi.restoreAllMocks());

  it.each([false, true])("keeps the site draft revision after background refresh, including logo write: %s", async (writeLogo) => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    let latest = siteSetting;
    const save = vi.spyOn(adminApi, "updateSiteSetting").mockRejectedValue(new Error("保留草稿"));
    const upload = vi.spyOn(adminApi, "uploadSiteLogo").mockResolvedValue({ ...siteSetting, name: "远端名称", revision: 3 });
    server.use(http.get("http://localhost:3000/api/v1/admin/settings/site", () => ok(latest)));
    const user = userEvent.setup();
    const { container } = renderSettingsPage(admin, client);
    const name = await screen.findByLabelText("站点名称");
    await user.clear(name);
    await user.type(name, "本地草稿");
    latest = { ...siteSetting, name: "远端名称", revision: 2 };
    await act(async () => { await client.refetchQueries({ queryKey: ["settings", "site"] }); });
    if (writeLogo) {
      const input = container.querySelector<globalThis.HTMLInputElement>('input[type="file"]');
      if (!input) throw new Error("Missing upload input");
      await user.upload(input, new globalThis.File(["logo"], "logo.png", { type: "image/png" }));
      await waitFor(() => expect(upload).toHaveBeenCalledWith(expect.any(globalThis.File), 2));
      await waitFor(() => expect(screen.getByRole("button", { name: /保存设置/ })).toBeEnabled());
    }
    expect(name).toHaveValue("本地草稿");
    await user.click(screen.getByRole("button", { name: /保存设置/ }));
    await waitFor(() => expect(save).toHaveBeenCalledWith(expect.objectContaining({ name: "本地草稿", revision: 1 })));
  });

  it("advances the draft revision for its own logo update without losing text", async () => {
    const save = vi.spyOn(adminApi, "updateSiteSetting").mockRejectedValue(new Error("保留草稿"));
    vi.spyOn(adminApi, "uploadSiteLogo").mockResolvedValue({ ...siteSetting, revision: 2 });
    server.use(http.get("http://localhost:3000/api/v1/admin/settings/site", () => ok(siteSetting)));
    const user = userEvent.setup();
    const { container } = renderSettingsPage();
    fireEvent.change(await screen.findByLabelText("站点名称"), { target: { value: "本地草稿" } });
    const input = container.querySelector<globalThis.HTMLInputElement>('input[type="file"]');
    if (!input) throw new Error("Missing upload input");
    await user.upload(input, new globalThis.File(["logo"], "logo.png", { type: "image/png" }));
    await waitFor(() => expect(screen.getByRole("button", { name: /保存设置/ })).toBeEnabled());
    await user.click(screen.getByRole("button", { name: /保存设置/ }));
    await waitFor(() => expect(save).toHaveBeenCalledWith(expect.objectContaining({ name: "本地草稿", revision: 2 })));
  });

  it("keeps the registration draft revision after background refresh", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    let revision = 1;
    const save = vi.spyOn(adminApi, "updateRegistrationSetting").mockRejectedValue(new Error("保留草稿"));
    server.use(http.get("http://localhost:3000/api/v1/admin/settings/registration", () => ok({ enabled: false, revision, updated_at: now, updated_by: null })));
    const user = userEvent.setup();
    renderSettingsPage({ ...admin, is_superuser: false, permissions: ["settings:registration:read", "settings:registration:update"] }, client);
    await user.click(await screen.findByRole("switch", { name: "开放用户注册" }));
    revision = 2;
    await act(async () => { await client.refetchQueries({ queryKey: ["settings", "registration"] }); });
    await user.click(screen.getByRole("button", { name: /保存设置/ }));
    await waitFor(() => expect(save).toHaveBeenCalledWith({ enabled: true, revision: 1 }));
  });

  it("loads and saves site settings with the current revision", async () => {
    let payload: unknown;
    server.use(
      http.get("http://localhost:3000/api/v1/admin/settings/site", () => ok(siteSetting)),
      http.patch("http://localhost:3000/api/v1/admin/settings/site", async ({ request }) => {
        payload = await request.json();
        return ok({ ...siteSetting, name: "新站点", revision: 2 });
      }),
    );
    const user = userEvent.setup();
    renderSettingsPage();

    const name = await screen.findByLabelText("站点名称");
    expect(screen.getByRole("img", { name: "当前站点 LOGO" })).toHaveAttribute(
      "src",
      siteSetting.logo?.url,
    );
    expect(screen.getByText(/设置管理员/)).toBeInTheDocument();
    await user.clear(name);
    await user.type(name, "新站点");
    await user.click(screen.getByRole("button", { name: /保存设置/ }));

    await waitFor(() =>
      expect(payload).toEqual({
        name: "新站点",
        title: siteSetting.title,
        keywords: siteSetting.keywords,
        description: siteSetting.description,
        revision: 1,
      }),
    );
    await waitFor(() => expect(screen.getByLabelText("站点名称")).toHaveValue("新站点"));
  });

  it("uploads and removes a valid site logo", async () => {
    let deletedRevision: string | null = null;
    const upload = vi.spyOn(adminApi, "uploadSiteLogo").mockResolvedValue({
      ...siteSetting,
      revision: 2,
      logo: { url: "/static/settings/site/new-logo.png?v=2", mime_type: "image/png", file_size: 10 },
    });
    server.use(
      http.get("http://localhost:3000/api/v1/admin/settings/site", () => ok(siteSetting)),
      http.delete("http://localhost:3000/api/v1/admin/settings/site/logo", ({ request }) => {
        deletedRevision = new globalThis.URL(request.url).searchParams.get("revision");
        return ok({ ...siteSetting, revision: 3, logo: null });
      }),
    );
    const user = userEvent.setup();
    const { container } = renderSettingsPage();

    await screen.findByLabelText("站点名称");
    const fileInput = container.querySelector<globalThis.HTMLInputElement>('input[type="file"]');
    expect(fileInput).not.toBeNull();
    await user.upload(fileInput!, new globalThis.File(["logo"], "logo.png", { type: "image/png" }));
    await waitFor(() => expect(upload).toHaveBeenCalledWith(expect.any(globalThis.File), 1));
    await waitFor(() =>
      expect(screen.getByRole("img", { name: "当前站点 LOGO" })).toHaveAttribute(
        "src",
        "/static/settings/site/new-logo.png?v=2",
      ),
    );

    await user.click(screen.getByRole("button", { name: /移除/ }));
    const confirmation = await screen.findByRole("dialog", { name: "确认移除站点 LOGO" });
    expect(deletedRevision).toBeNull();
    await user.click(within(confirmation).getByRole("button", { name: /取\s*消/ }));
    expect(deletedRevision).toBeNull();
    expect(screen.getByRole("img", { name: "当前站点 LOGO" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /移除/ }));
    await user.click(within(await screen.findByRole("dialog", { name: "确认移除站点 LOGO" })).getByRole("button", { name: /确\s*定/ }));
    await waitFor(() => expect(deletedRevision).toBe("2"));
    expect(await screen.findByText("未上传")).toBeInTheDocument();
  });

  it("preserves the logo and site draft after a failed removal and permits retry", async () => {
    let attempts = 0;
    server.use(
      http.get("http://localhost:3000/api/v1/admin/settings/site", () => ok(siteSetting)),
      http.delete("http://localhost:3000/api/v1/admin/settings/site/logo", () => {
        attempts += 1;
        return attempts === 1
          ? HttpResponse.json({ code: "STORAGE_UNAVAILABLE", message: "LOGO 存储暂不可用", request_id: "test-request" }, { status: 503 })
          : ok({ ...siteSetting, revision: 2, logo: null });
      }),
    );
    const user = userEvent.setup();
    renderSettingsPage();
    const name = await screen.findByLabelText("站点名称");
    await user.clear(name);
    await user.type(name, "未保存的站点名称");
    await user.click(screen.getByRole("button", { name: /移除/ }));
    const dialog = await screen.findByRole("dialog", { name: "确认移除站点 LOGO" });
    await user.click(within(dialog).getByRole("button", { name: /确\s*定/ }));
    expect(await within(dialog).findByText("LOGO 存储暂不可用")).toBeVisible();
    expect(screen.getByRole("img", { name: "当前站点 LOGO" })).toBeInTheDocument();
    expect(name).toHaveValue("未保存的站点名称");
    await user.click(within(dialog).getByRole("button", { name: /确\s*定/ }));
    expect(await screen.findByText("未上传")).toBeInTheDocument();
    expect(name).toHaveValue("未保存的站点名称");
  });

  it("requires reloading and fresh confirmation after a logo revision conflict", async () => {
    const revisions: string[] = [];
    let latest = siteSetting;
    server.use(
      http.get("http://localhost:3000/api/v1/admin/settings/site", () => ok(latest)),
      http.delete("http://localhost:3000/api/v1/admin/settings/site/logo", ({ request }) => {
        const revision = new globalThis.URL(request.url).searchParams.get("revision");
        revisions.push(revision ?? "");
        if (revision === "1") {
          latest = { ...siteSetting, revision: 2 };
          return HttpResponse.json({ code: "SETTINGS_REVISION_MISMATCH", message: "站点配置版本冲突", request_id: "test-request" }, { status: 412 });
        }
        return ok({ ...latest, revision: 3, logo: null });
      }),
    );
    const user = userEvent.setup();
    renderSettingsPage();
    await screen.findByLabelText("站点名称");
    await user.click(screen.getByRole("button", { name: /移除/ }));
    const dialog = await screen.findByRole("dialog", { name: "确认移除站点 LOGO" });
    await user.click(within(dialog).getByRole("button", { name: /确\s*定/ }));
    expect(await within(dialog).findByText("站点配置版本冲突")).toBeVisible();
    await user.click(within(dialog).getByRole("button", { name: /确\s*定/ }));
    expect(await within(dialog).findByText("设置已变更，请取消后加载最新配置，再重新确认移除")).toBeVisible();
    expect(revisions).toEqual(["1"]);
    await user.click(within(dialog).getByRole("button", { name: /取\s*消/ }));
    await user.click(screen.getByRole("button", { name: /加载最新配置/ }));
    await waitFor(() => expect(screen.getByRole("button", { name: /移除/ })).toBeEnabled());
    await user.click(screen.getByRole("button", { name: /移除/ }));
    await user.click(within(await screen.findByRole("dialog", { name: "确认移除站点 LOGO" })).getByRole("button", { name: /确\s*定/ }));
    expect(await screen.findByText("未上传")).toBeInTheDocument();
    expect(revisions).toEqual(["1", "2"]);
  });

  it("rejects unsupported and oversized logo files before upload", async () => {
    const upload = vi.spyOn(adminApi, "uploadSiteLogo");
    const { container } = renderSettingsPage();

    await screen.findByLabelText("站点名称");
    const fileInput = container.querySelector<globalThis.HTMLInputElement>('input[type="file"]');
    expect(fileInput).not.toBeNull();
    fireEvent.change(fileInput!, {
      target: { files: [new globalThis.File(["text"], "logo.txt", { type: "text/plain" })] },
    });
    expect(await screen.findByText("仅支持 PNG、JPEG 或 WebP 图片")).toBeInTheDocument();

    const oversized = new globalThis.File([new Uint8Array(2 * 1024 * 1024 + 1)], "large.png", {
      type: "image/png",
    });
    const currentFileInput = container.querySelector<globalThis.HTMLInputElement>('input[type="file"]');
    expect(currentFileInput).not.toBeNull();
    fireEvent.change(currentFileInput!, { target: { files: [oversized] } });
    expect(await screen.findByText("站点 LOGO 不能超过 2 MB")).toBeInTheDocument();
    expect(upload).not.toHaveBeenCalled();
  });

  it("keeps edited values on a revision conflict and can load the latest site settings", async () => {
    let reads = 0;
    server.use(
      http.get("http://localhost:3000/api/v1/admin/settings/site", () => {
        reads += 1;
        return ok(reads === 1 ? siteSetting : { ...siteSetting, name: "远端站点", revision: 2 });
      }),
      http.patch("http://localhost:3000/api/v1/admin/settings/site", () =>
        HttpResponse.json(
          { code: "SETTINGS_REVISION_MISMATCH", message: "设置已被修改", request_id: "test-request" },
          { status: 412 },
        ),
      ),
    );
    const user = userEvent.setup();
    renderSettingsPage();

    const name = await screen.findByLabelText("站点名称");
    await user.clear(name);
    await user.type(name, "本地草稿");
    await user.click(screen.getByRole("button", { name: /保存设置/ }));
    expect(await screen.findByText("设置已被其他管理员修改")).toBeInTheDocument();
    expect(name).toHaveValue("本地草稿");

    await user.click(screen.getByRole("button", { name: /加载最新配置/ }));
    await waitFor(() => expect(name).toHaveValue("远端站点"));
  });

  it("shows a site query failure and retries successfully", async () => {
    let reads = 0;
    server.use(
      http.get("http://localhost:3000/api/v1/admin/settings/site", () => {
        reads += 1;
        return reads === 1
          ? HttpResponse.json(
              { code: "SERVICE_UNAVAILABLE", message: "站点设置暂时不可用", request_id: "test-request" },
              { status: 503 },
            )
          : ok({ ...siteSetting, logo: null });
      }),
    );
    const user = userEvent.setup();
    renderSettingsPage();

    expect(await screen.findByText("站点设置暂时不可用")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /重\s*试/ }));
    expect(await screen.findByLabelText("站点名称")).toHaveValue(siteSetting.name);
    expect(screen.getByText("未上传")).toBeInTheDocument();
  });

  it("renders site settings as read-only without update permission", async () => {
    server.use(http.get("http://localhost:3000/api/v1/admin/settings/site", () => ok(siteSetting)));
    renderSettingsPage({
      ...admin,
      is_superuser: false,
      permissions: ["settings:site:read"],
    });

    expect(await screen.findByText("当前账号只有查看权限，设置内容不可修改。")).toBeInTheDocument();
    expect(screen.getByLabelText("站点名称")).toBeDisabled();
    expect(screen.getByRole("button", { name: /上传 LOGO/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: /移除/ })).toBeDisabled();
  });

  it("loads and saves the registration policy", async () => {
    let payload: unknown;
    server.use(
      http.patch("http://localhost:3000/api/v1/admin/settings/registration", async ({ request }) => {
        payload = await request.json();
        return ok({ enabled: true, revision: 2, updated_at: now, updated_by: null });
      }),
    );
    const user = userEvent.setup();
    renderSettingsPage({
      ...admin,
      is_superuser: false,
      permissions: ["settings:registration:read", "settings:registration:update"],
    });

    await user.click(await screen.findByRole("switch", { name: "开放用户注册" }));
    await user.click(screen.getByRole("button", { name: /保存设置/ }));
    await waitFor(() => expect(payload).toEqual({ enabled: true, revision: 1 }));
  });

  it("handles a registration revision conflict and reloads the current policy", async () => {
    let reads = 0;
    server.use(
      http.get("http://localhost:3000/api/v1/admin/settings/registration", () => {
        reads += 1;
        return ok({ enabled: reads > 1, revision: reads, updated_at: now, updated_by: null });
      }),
      http.patch("http://localhost:3000/api/v1/admin/settings/registration", () =>
        HttpResponse.json(
          { code: "SETTINGS_REVISION_MISMATCH", message: "设置已被修改", request_id: "test-request" },
          { status: 412 },
        ),
      ),
    );
    const user = userEvent.setup();
    renderSettingsPage({
      ...admin,
      is_superuser: false,
      permissions: ["settings:registration:read", "settings:registration:update"],
    });

    const toggle = await screen.findByRole("switch", { name: "开放用户注册" });
    expect(toggle).not.toBeChecked();
    await user.click(toggle);
    await user.click(screen.getByRole("button", { name: /保存设置/ }));
    expect(await screen.findByText("设置已被其他管理员修改")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /加载最新配置/ }));
    await waitFor(() => expect(toggle).toBeChecked());
  });

  it("shows read-only registration settings and denies principals without read permissions", async () => {
    const { unmount } = renderSettingsPage({
      ...admin,
      is_superuser: false,
      permissions: ["settings:registration:read"],
    });
    expect(await screen.findByText("当前账号只有查看权限，注册开关不可修改。")).toBeInTheDocument();
    expect(screen.getByRole("switch", { name: "开放用户注册" })).toBeDisabled();

    unmount();
    renderSettingsPage({ ...admin, is_superuser: false, permissions: [] });
    expect(screen.getByText("无权访问系统设置")).toBeInTheDocument();
  });

  it("reports non-conflict save failures without replacing the form", async () => {
    server.use(
      http.patch("http://localhost:3000/api/v1/admin/settings/site", () =>
        HttpResponse.json(
          { code: "SETTINGS_WRITE_FAILED", message: "保存失败", request_id: "test-request" },
          { status: 500 },
        ),
      ),
    );
    const user = userEvent.setup();
    renderSettingsPage();

    const description = await screen.findByLabelText("站点描述");
    fireEvent.change(description, { target: { value: "本地描述" } });
    await user.click(screen.getByRole("button", { name: /保存设置/ }));
    expect(await screen.findByText("保存失败")).toBeInTheDocument();
    expect(description).toHaveValue("本地描述");
  });
});
