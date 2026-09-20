import type { AdminRead } from "@pinjie/api-client";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import defaultSettings from "../config/defaultSettings";
import { getInitialState, layout, rootContainer } from "./app";
import { server } from "./test/setup";
import { apiRequest } from "./lib/api/http";
import { LoginPage } from "./features/auth/LoginPage";

const { history } = vi.hoisted(() => {
  const location: { hash: string; pathname: string; search: string; state?: unknown } = { hash: "", pathname: "/", search: "" };
  const navigate = (target: string, state?: unknown) => {
    const url = new globalThis.URL(target, "http://localhost");
    location.hash = url.hash;
    location.pathname = url.pathname;
    location.search = url.search;
    location.state = state;
  };
  return {
    history: {
      location,
      push: vi.fn(navigate),
      replace: vi.fn(navigate),
    },
  };
});

vi.mock("@umijs/max", () => ({
  history,
  Link: ({ children, to }: { children: ReactNode; to: string }) => <a href={to}>{children}</a>,
}));

const now = "2026-08-22T00:00:00Z";
const currentAdmin: AdminRead = {
  id: "01900000-0000-7000-8000-000000000001",
  username: "stage-admin",
  display_name: "Stage Admin",
  avatar: "/static/uploads/avatar.png",
  is_active: true,
  is_superuser: true,
  roles: [],
  permissions: [],
  created_at: now,
  updated_at: now,
};

describe("admin runtime lifecycle", () => {
  it("skips bootstrap on login and loads the current administrator elsewhere", async () => {
    history.push("/login");
    await expect(getInitialState()).resolves.toEqual({ settings: defaultSettings });

    history.push("/users");
    await expect(getInitialState()).resolves.toMatchObject({ currentAdmin: { username: "stage-admin" } });
  });

  it("redirects only after authentication recovery fails", async () => {
    const replace = vi.spyOn(history, "replace");
    history.push("/users?search=locked#row");
    server.use(
      http.get("http://localhost:3000/api/v1/admin/auth/me", () =>
        HttpResponse.json({ code: "AUTH_REQUIRED", message: "需要登录" }, { status: 401 }),
      ),
      http.post("http://localhost:3000/api/v1/admin/auth/refresh", () =>
        HttpResponse.json({ code: "AUTH_REQUIRED", message: "需要登录" }, { status: 401 }),
      ),
    );

    await expect(getInitialState()).resolves.toEqual({ settings: defaultSettings });
    expect(replace).toHaveBeenCalledWith(expect.stringMatching(/^\/login\?redirect=/));
    replace.mockRestore();
  });

  it("keeps non-authentication bootstrap failures visible", async () => {
    history.push("/users");
    server.use(
      http.get("http://localhost:3000/api/v1/admin/auth/me", () =>
        HttpResponse.json({ code: "SERVICE_UNAVAILABLE", message: "管理服务暂不可用" }, { status: 503 }),
      ),
    );

    await expect(getInitialState()).resolves.toMatchObject({ bootstrapError: "管理服务暂不可用" });
    expect(history.location.pathname).toBe("/users");
  });

  it("returns an expired running session to login with its original destination", async () => {
    history.push("/users?search=active#row");
    await getInitialState();
    server.use(
      http.get("http://localhost:3000/api/v1/admin/users", () =>
        HttpResponse.json({ code: "AUTH_SESSION_REVOKED" }, { status: 401 })),
      http.post("http://localhost:3000/api/v1/admin/auth/refresh", () =>
        HttpResponse.json({ code: "AUTH_SESSION_REVOKED" }, { status: 401 })),
    );
    await expect(apiRequest("/api/v1/admin/users")).rejects.toMatchObject({ code: "AUTH_SESSION_REVOKED" });
    expect(history.location.pathname).toBe("/login");
    expect(new URLSearchParams(history.location.search).get("redirect")).toBe("/users?search=active#row");
  });

  it.each([[429, "RATE_LIMITED"], [403, "CSRF_REJECTED"], [503, "REQUEST_FAILED"]] as const)("keeps the current route for refresh failure %s / %s during bootstrap", async (status, code) => {
    history.push("/users");
    server.use(
      http.get("http://localhost:3000/api/v1/admin/auth/me", () =>
        HttpResponse.json({ code: "AUTH_REQUIRED" }, { status: 401 }),
      ),
      http.post("http://localhost:3000/api/v1/admin/auth/refresh", () =>
        HttpResponse.json({ code, message: "会话服务暂不可用" }, { status }),
      ),
    );
    await expect(getInitialState()).resolves.toMatchObject({ bootstrapError: "会话服务暂不可用" });
    expect(history.location.pathname).toBe("/users");
  });

  it("redirects a bootstrap refresh outage to login with diagnostics and no recovery loop", async () => {
    history.push("/users?search=active#row");
    let refreshCalls = 0;
    let meCalls = 0;
    server.use(
      http.get("http://localhost:3000/api/v1/admin/auth/me", () => {
        meCalls += 1;
        return HttpResponse.json({ code: "AUTH_REQUIRED" }, { status: 401 });
      }),
      http.post("http://localhost:3000/api/v1/admin/auth/refresh", () => {
        refreshCalls += 1;
        return HttpResponse.json({ code: "SERVICE_UNAVAILABLE", message: "认证服务暂时不可用", request_id: "refresh-request" }, { status: 503 });
      }),
    );

    await expect(getInitialState()).resolves.toEqual({ settings: defaultSettings });
    expect(history.location.pathname).toBe("/login");
    expect(new URLSearchParams(history.location.search).get("redirect")).toBe("/users?search=active#row");
    expect(history.location.search).not.toContain("refresh-request");
    render(rootContainer(<LoginPage />));
    expect(screen.getByText("登录状态恢复失败，请稍后重试")).toBeInTheDocument();
    expect(screen.getByText("认证服务暂时不可用")).toBeInTheDocument();
    expect(screen.getByText("错误：503 / SERVICE_UNAVAILABLE")).toBeInTheDocument();
    expect(screen.getByText("请求编号：refresh-request")).toBeInTheDocument();
    expect(screen.queryByText(/本地开发请检查 Redis/)).not.toBeInTheDocument();
    await expect(getInitialState()).resolves.toEqual({ settings: defaultSettings });
    expect(refreshCalls).toBe(1);
    expect(meCalls).toBe(1);
  });

  it("keeps a running workspace on refresh service failure", async () => {
    history.push("/users?search=active#row");
    await getInitialState();
    server.use(
      http.get("http://localhost:3000/api/v1/admin/users", () =>
        HttpResponse.json({ code: "AUTH_REQUIRED" }, { status: 401 })),
      http.post("http://localhost:3000/api/v1/admin/auth/refresh", () =>
        HttpResponse.json({ code: "SERVICE_UNAVAILABLE" }, { status: 503 })),
    );
    await expect(apiRequest("/api/v1/admin/users")).rejects.toMatchObject({ status: 503, source: "refresh" });
    expect(history.location.pathname + history.location.search + history.location.hash).toBe("/users?search=active#row");
  });

  it.each([200, 503])("preserves the replay outcome %s after a successful bootstrap refresh", async (status) => {
    history.push("/users");
    let meCalls = 0;
    server.use(
      http.get("http://localhost:3000/api/v1/admin/auth/me", () => {
        meCalls += 1;
        if (meCalls === 1) return HttpResponse.json({ code: "AUTH_REQUIRED" }, { status: 401 });
        return status === 200
          ? HttpResponse.json({ code: "OK", data: currentAdmin })
          : HttpResponse.json({ code: "SERVICE_UNAVAILABLE", message: "读取管理员失败" }, { status });
      }),
      http.post("http://localhost:3000/api/v1/admin/auth/refresh", () => HttpResponse.json({ code: "OK" })),
    );
    await expect(getInitialState()).resolves.toMatchObject(status === 200
      ? { currentAdmin } : { bootstrapError: "读取管理员失败" });
    expect(history.location.pathname).toBe("/users");
    expect(meCalls).toBe(2);
  });

  it("keeps the bootstrap error page on a refresh network failure", async () => {
    history.push("/users");
    server.use(
      http.get("http://localhost:3000/api/v1/admin/auth/me", () =>
        HttpResponse.json({ code: "AUTH_REQUIRED" }, { status: 401 })),
      http.post("http://localhost:3000/api/v1/admin/auth/refresh", () => HttpResponse.error()),
    );
    await expect(getInitialState()).resolves.toMatchObject({ bootstrapError: expect.any(String) });
    expect(history.location.pathname).toBe("/users");
  });

  it("replaces the recovery notice with the latest login failure", async () => {
    history.replace("/login", { authRecoveryError: { message: "认证服务暂时不可用" } });
    server.use(http.post("http://localhost:3000/api/v1/admin/auth/login", () =>
      HttpResponse.json({ code: "AUTH_INVALID_CREDENTIALS", message: "用户名或密码错误" }, { status: 401 })));
    const user = userEvent.setup();
    render(rootContainer(<LoginPage />));
    expect(screen.queryByText(/请求编号/)).not.toBeInTheDocument();
    await user.type(screen.getByLabelText("用户名"), "stage-admin");
    await user.type(screen.getByLabelText("密码"), "invalid-password");
    await user.click(screen.getByRole("button", { name: /登\s*录/ }));
    expect(await screen.findByText("用户名或密码错误")).toBeInTheDocument();
    expect(screen.queryByText("登录状态恢复失败，请稍后重试")).not.toBeInTheDocument();
    expect(history.location.pathname).toBe("/login");
  });

  it("navigates to account settings from dropdown menu", async () => {
    const user = userEvent.setup();
    const runtime = layout({ initialState: { settings: defaultSettings, currentAdmin } });
    render(rootContainer(runtime.avatarProps?.render?.() ?? null));
    expect(screen.getByRole("img", { name: "Stage Admin的头像" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "账户菜单：Stage Admin" }));
    await user.click(await screen.findByText("个人设置"));

    expect(history.location.pathname).toBe("/account/settings");
  });

  it("shows logout failures without redirecting", async () => {
    const user = userEvent.setup();
    server.use(
      http.post("http://localhost:3000/api/v1/admin/auth/logout", () =>
        HttpResponse.json({ code: "SERVICE_UNAVAILABLE", message: "退出失败，请重试" }, { status: 503 }),
      ),
    );
    history.push("/users");
    const runtime = layout({ initialState: { settings: defaultSettings, currentAdmin } });
    render(rootContainer(runtime.avatarProps?.render?.() ?? null));

    await user.click(screen.getByRole("button", { name: "账户菜单：Stage Admin" }));
    await user.click(await screen.findByText("退出登录"));

    expect(await screen.findByText("退出失败，请重试")).toBeInTheDocument();
    expect(history.location.pathname).toBe("/users");
  });

  it("renders bootstrap error, loading, and authenticated layout states", () => {
    const failed = layout({ initialState: { settings: defaultSettings, bootstrapError: "连接失败" } });
    const loading = layout({ initialState: { settings: defaultSettings } });
    const ready = layout({ initialState: { settings: defaultSettings, currentAdmin } });

    const failedView = render(rootContainer(failed.childrenRender?.(<span>内容</span>) ?? null));
    expect(screen.getByText("管理服务暂不可用")).toBeInTheDocument();
    failedView.unmount();

    const loadingView = render(rootContainer(loading.childrenRender?.(<span>内容</span>) ?? null));
    expect(screen.getByText("正在初始化管理工作区")).toBeInTheDocument();
    loadingView.unmount();

    render(rootContainer(ready.childrenRender?.(<span>受保护内容</span>) ?? null));
    expect(screen.getByText("受保护内容")).toBeInTheDocument();
    expect(ready.title).toBe("PinJie Console");
    expect(ready.siderWidth).toBe(256);
    expect(ready.token?.pageContainer?.paddingInlinePageContainerContent).toBe(40);
  });
});
