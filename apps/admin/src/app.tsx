import type { AdminRead } from "@pinjie/api-client";
import { LogoutOutlined, SettingOutlined } from "@ant-design/icons";
import { history, Link } from "@umijs/max";
import {
  QueryClient,
  QueryClientProvider,
  useMutation,
} from "@tanstack/react-query";
import {
  Button,
  ConfigProvider,
  Dropdown,
  Result,
  Typography,
  message,
  theme,
} from "antd";
import zhCN from "antd/locale/zh_CN";
import type { ReactNode } from "react";

import defaultSettings from "../config/defaultSettings";
import { AdminAvatar } from "./components/AdminAvatar";
import { AdminContext } from "./features/auth/auth-context";
import { adminApi } from "./lib/api/admin";
import { errorMessage, isSessionError, setSessionExpiredHandler } from "./lib/api/http";
import logoSvg from "./assets/logo.svg";
import "./styles.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: false, staleTime: 15_000 },
    mutations: { retry: false },
  },
});

let authenticated = false;
setSessionExpiredHandler(() => {
  if (!authenticated) return;
  authenticated = false;
  queryClient.clear();
  const { pathname, search, hash } = history.location;
  if (pathname === "/login") return;
  history.replace(`/login?redirect=${encodeURIComponent(pathname + search + hash)}`);
  // 重新初始化 Umi，移除旧 initialState、权限与正在执行的页面状态。
  if (process.env.NODE_ENV !== "test") window.location.reload();
});

export type AdminInitialState = {
  currentAdmin?: AdminRead;
  bootstrapError?: string;
  settings: typeof defaultSettings;
};

export async function getInitialState(): Promise<AdminInitialState> {
  authenticated = false;
  const settings = defaultSettings;
  if (history.location.pathname === "/login") return { settings };
  try {
    const currentAdmin = await adminApi.me();
    authenticated = true;
    return { currentAdmin, settings };
  } catch (error) {
    if (isSessionError(error)) {
      const { pathname, search, hash } = history.location;
      history.replace(
        `/login?redirect=${encodeURIComponent(pathname + search + hash)}`,
      );
      return { settings };
    }
    return { settings, bootstrapError: errorMessage(error) };
  }
}

function AccountMenu({ admin }: { admin: AdminRead }) {
  const logout = useMutation({
    mutationFn: adminApi.logout,
    onSuccess: () => {
      queryClient.clear();
      history.replace("/login");
      window.location.reload();
    },
    onError: (error) => message.error(errorMessage(error)),
  });
  return (
    <Dropdown
      menu={{
        items: [
          {
            key: "settings",
            icon: <SettingOutlined />,
            label: "个人设置",
            onClick: () => history.push("/account/settings"),
          },
          { type: "divider" },
          {
            key: "logout",
            icon: <LogoutOutlined />,
            label: "退出登录",
            danger: true,
            disabled: logout.isPending,
            onClick: () => logout.mutate(),
          },
        ],
      }}
    >
      <Button
        type="text"
        className="account-trigger"
        aria-label={`账户菜单：${admin.display_name || admin.username}`}
      >
        <AdminAvatar admin={admin} />
        <span>{admin.display_name || admin.username}</span>
      </Button>
    </Dropdown>
  );
}

function AdminLayoutFrame({
  initialState,
  children,
}: {
  initialState: AdminInitialState;
  children: ReactNode;
}) {
  if (initialState.bootstrapError) {
    return (
      <main className="bootstrap-state">
        <Result
          status="warning"
          title="管理服务暂不可用"
          subTitle={initialState.bootstrapError}
          extra={
            <Button type="primary" onClick={() => window.location.reload()}>
              重试
            </Button>
          }
        />
      </main>
    );
  }
  if (!initialState.currentAdmin)
    return (
      <main className="bootstrap-state">
        <Typography.Text>正在初始化管理工作区</Typography.Text>
      </main>
    );
  return (
    <AdminContext.Provider value={initialState.currentAdmin}>
      {children}
    </AdminContext.Provider>
  );
}

export const layout = ({ initialState }: { initialState?: unknown }) => {
  const state = initialState as AdminInitialState | undefined;
  return {
    title: "PinJie Console",
    logo: logoSvg,
    menuItemRender: (item: { path?: string }, dom: ReactNode) =>
      item.path ? <Link to={item.path}>{dom}</Link> : dom,
    avatarProps: state?.currentAdmin
      ? {
          title: state.currentAdmin.display_name || state.currentAdmin.username,
          size: "small",
          render: () =>
            state.currentAdmin ? (
              <AccountMenu admin={state.currentAdmin} />
            ) : null,
        }
      : undefined,
    actionsRender: () => [],
    footerRender: () => (
      <footer className="admin-footer">Pinjie Console · 品界网络科技</footer>
    ),
    childrenRender: (children: ReactNode) => (
      <AdminLayoutFrame initialState={state ?? { settings: defaultSettings }}>
        {children}
      </AdminLayoutFrame>
    ),
    ...state?.settings,
    siderWidth: 256,
    token: {
      bgLayout: "#f5f7fa",
      header: {
        colorBgHeader: "#ffffff",
        colorBgScrollHeader: "#ffffff",
        colorHeaderTitle: "#101828",
        colorTextRightActionsItem: "#475467",
        heightLayoutHeader: 56,
      },
      sider: {
        colorMenuBackground: "#ffffff",
        colorBgMenuItemCollapsedElevated: "#ffffff",
        colorMenuItemDivider: "#f0f2f5",
        colorBgMenuItemHover: "#f5f7fa",
        colorBgMenuItemActive: "#e6f4ff",
        colorBgMenuItemSelected: "#e6f4ff",
        colorTextMenuSelected: "#0958d9",
        colorTextMenuItemHover: "#0958d9",
        colorTextMenuActive: "#0958d9",
        colorTextMenu: "#475467",
        colorTextMenuSecondary: "#667085",
        colorTextMenuTitle: "#101828",
        colorTextSubMenuSelected: "#0958d9",
      },
      pageContainer: {
        colorBgPageContainer: "#f5f7fa",
        colorBgPageContainerFixed: "#ffffff",
        paddingInlinePageContainerContent: 40,
        paddingBlockPageContainerContent: 24,
      },
    },
  };
};

export function rootContainer(container: ReactNode) {
  return (
    <ConfigProvider
      locale={zhCN}
      theme={{
        algorithm: theme.defaultAlgorithm,
        token: {
          borderRadius: 8,
          borderRadiusLG: 8,
          controlHeight: 36,
          colorError: "#cf1322",
          colorErrorText: "#a8071a",
          colorBgLayout: "#f5f7fa",
          colorPrimary: "#0958d9",
          colorLink: "#0958d9",
          colorLinkHover: "#003eb3",
          colorSuccess: "#237804",
          colorSuccessBg: "#f6ffed",
          colorSuccessBorder: "#b7eb8f",
          colorSuccessText: "#237804",
          colorTextDescription: "#667085",
          colorTextSecondary: "#667085",
          fontFamily:
            '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
        },
        components: {
          Card: { headerBg: "#ffffff", colorBgContainer: "#ffffff" },
          Table: {
            headerBg: "#fafafa",
            headerColor: "#1d2939",
            rowHoverBg: "#f8fafc",
          },
        },
      }}
    >
      <QueryClientProvider client={queryClient}>
        {container}
      </QueryClientProvider>
    </ConfigProvider>
  );
}
