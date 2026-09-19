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

const { history } = vi.hoisted(() => {
  const location = { hash: "", pathname: "/", search: "" };
  const navigate = (target: string) => {
    const url = new globalThis.URL(target, "http://localhost");
    location.hash = url.hash;
    location.pathname = url.pathname;
    location.search = url.search;
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

  it.each([429, 503])("keeps the current route when refresh returns %s during bootstrap", async (status) => {
    history.push("/users");
    server.use(
      http.get("http://localhost:3000/api/v1/admin/auth/me", () =>
        HttpResponse.json({ code: "AUTH_REQUIRED" }, { status: 401 }),
      ),
      http.post("http://localhost:3000/api/v1/admin/auth/refresh", () =>
        HttpResponse.json({ code: status === 429 ? "RATE_LIMITED" : "SERVICE_UNAVAILABLE", message: "会话服务暂不可用" }, { status }),
      ),
    );
    await expect(getInitialState()).resolves.toMatchObject({ bootstrapError: "会话服务暂不可用" });
    expect(history.location.pathname).toBe("/users");
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
