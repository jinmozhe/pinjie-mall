import type { AdminRead } from "@pinjie/api-client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { ConfigProvider } from "antd";
import zhCN from "antd/locale/zh_CN";
import { describe, expect, it, vi } from "vitest";

import { AdminContext } from "@/features/auth";
import { WelcomePage } from "./WelcomePage";

const { push } = vi.hoisted(() => ({
  push: vi.fn(),
}));

vi.mock("@umijs/max", () => ({
  history: { push },
}));

const mockAdmin: AdminRead = {
  id: "01900000-0000-7000-8000-000000000001",
  username: "welcome-admin",
  display_name: "欢迎管理员",
  is_active: true,
  is_superuser: true,
  roles: [],
  permissions: [],
  created_at: "2026-08-24T00:00:00Z",
  updated_at: "2026-08-24T00:00:00Z",
};

function renderWelcomePage(principal: AdminRead = mockAdmin) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <ConfigProvider locale={zhCN}>
      <QueryClientProvider client={client}>
        <AdminContext.Provider value={principal}>
          <WelcomePage />
        </AdminContext.Provider>
      </QueryClientProvider>
    </ConfigProvider>,
  );
}

describe("WelcomePage", () => {
  it("renders welcome banner with current admin display name", () => {
    renderWelcomePage(mockAdmin);
    expect(screen.getByText("欢迎使用 Pinjie Mall 管理后台")).toBeInTheDocument();
    expect(screen.getByText("您好，欢迎管理员！")).toBeInTheDocument();
    expect(screen.getByText("管理后台基础能力")).toBeInTheDocument();
    expect(screen.getByText("高性能后端")).toBeInTheDocument();
    expect(screen.getByText("安全与会话隔离")).toBeInTheDocument();
    expect(screen.getByText("现代化管理控制台")).toBeInTheDocument();
    expect(screen.getByText("微信小程序端")).toBeInTheDocument();
  });

  it("handles navigation clicks to workspace features", () => {
    renderWelcomePage(mockAdmin);
    fireEvent.click(screen.getByRole("button", { name: /开始管理工作区/ }));
    expect(push).toHaveBeenCalledWith("/users");

    fireEvent.click(screen.getByText("用户管理"));
    expect(push).toHaveBeenCalledWith("/users");

    fireEvent.click(screen.getByText("管理员"));
    expect(push).toHaveBeenCalledWith("/admins");

    fireEvent.click(screen.getByText("安全日志"));
    expect(push).toHaveBeenCalledWith("/security");

    fireEvent.click(screen.getByText("系统状态"));
    expect(push).toHaveBeenCalledWith("/system");
  });

  it("renders username when display name is not set", () => {
    const adminWithoutDisplayName = { ...mockAdmin, display_name: null, username: "simple-admin" };
    renderWelcomePage(adminWithoutDisplayName);
    expect(screen.getByText("您好，simple-admin！")).toBeInTheDocument();
  });
});
