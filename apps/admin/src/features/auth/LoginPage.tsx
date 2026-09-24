import {
  LockOutlined,
  SafetyCertificateOutlined,
  UserOutlined,
} from "@ant-design/icons";
import { history } from "@umijs/max";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Form, Input, Tooltip } from "antd";
import { useEffect } from "react";

import { adminApi } from "@/lib/api/admin";
import { errorMessage } from "@/lib/api/http";

type LoginValues = { username: string; password: string };

function getRecoveryError(state: unknown): { message: string; requestId?: string } | undefined {
  if (!state || typeof state !== "object" || !("authRecoveryError" in state)) return;
  const error = state.authRecoveryError;
  if (!error || typeof error !== "object" || !("message" in error) || typeof error.message !== "string") return;
  return {
    message: error.message,
    requestId: "requestId" in error && typeof error.requestId === "string" ? error.requestId : undefined,
  };
}

function getSafeRedirectTarget(): string {
  if (typeof window === "undefined") return "/welcome";
  const params = new URLSearchParams(window.location.search);
  const redirect = params.get("redirect");
  if (!redirect) return "/welcome";
  // 仅允许以单个斜杠开头的站内相对路径，防止开放重定向漏洞
  const hasUnsafeCharacter = [...redirect].some((character) => {
    const code = character.charCodeAt(0);
    return character === "\\" || code < 32 || code === 127;
  });
  if (redirect.startsWith("/") && !redirect.startsWith("//") && !hasUnsafeCharacter) {
    try {
      const target = new globalThis.URL(redirect, window.location.origin);
      if (target.origin === window.location.origin && target.pathname.startsWith("/")) return `${target.pathname}${target.search}${target.hash}`;
    } catch { /* fall through to the safe default */ }
  }
  return "/welcome";
}

export function LoginPage({
  authenticated = false,
}: {
  authenticated?: boolean;
}) {
  const queryClient = useQueryClient();
  const recoveryError = getRecoveryError(history.location.state);

  useEffect(() => {
    if (authenticated) {
      history.replace(getSafeRedirectTarget());
    }
  }, [authenticated]);

  const login = useMutation({
    mutationFn: (values: LoginValues) => adminApi.login(values),
    onSuccess: (session) => {
      queryClient.setQueryData(["admin-me"], session.principal);
      history.replace(getSafeRedirectTarget());
      if (process.env.NODE_ENV !== "test") window.location.reload();
    },
  });

  if (authenticated) {
    return null;
  }

  return (
    <main className="login-screen">
      <section className="login-content" aria-labelledby="login-title">
        <div className="login-shell">
          <header className="login-top">
            <div className="login-header">
              <span className="login-header__logo" aria-hidden="true" />
              <h1 className="login-header__title" id="login-title">
                Pinjie Console&nbsp;&nbsp;
              </h1>
            </div>
            <p className="login-desc">
              统一身份、精细权限、全链路审计的管理中枢
            </p>
          </header>

          <div className="login-main">
            {recoveryError && !login.isError && (
              <Alert
                className="login-alert"
                title="登录状态恢复失败，请稍后重试"
                description={
                  <>
                    <div>{recoveryError.message}</div>
                    <div>错误：503 / SERVICE_UNAVAILABLE</div>
                    {recoveryError.requestId && <div>请求编号：{recoveryError.requestId}</div>}
                    {process.env.NODE_ENV === "development" && (
                      <div>本地开发请检查 Redis 是否启动；服务恢复后可重新登录。</div>
                    )}
                  </>
                }
                showIcon
                type="warning"
              />
            )}
            {login.isError && (
              <Alert
                className="login-alert"
                title={errorMessage(login.error)}
                showIcon
                type="error"
              />
            )}
            <Form<LoginValues>
              layout="vertical"
              onFinish={(values) => login.mutate(values)}
              requiredMark={false}
            >
              <Form.Item name="username" rules={[{ required: true, message: "请输入用户名" }]}>
                <Input
                  allowClear
                  aria-label="用户名"
                  autoComplete="username"
                  placeholder="管理员用户名"
                  prefix={<UserOutlined className="login-prefix-icon" />}
                  size="large"
                  variant="filled"
                />
              </Form.Item>
              <Form.Item
                name="password"
                rules={[
                  { required: true, message: "请输入密码" },
                  { max: 64, message: "密码最多 64 个字符" },
                ]}
              >
                <Input.Password
                  aria-label="密码"
                  autoComplete="current-password"
                  maxLength={64}
                  placeholder="登录密码"
                  prefix={<LockOutlined className="login-prefix-icon" />}
                  size="large"
                  variant="filled"
                />
              </Form.Item>
              <div className="login-other-actions">
                <span className="login-session-note">
                  <SafetyCertificateOutlined />
                  安全会话自动保持
                </span>
                <Tooltip
                  placement="top"
                  title="请联系超级管理员为您重置密码"
                  trigger={["hover", "focus"]}
                >
                  <span className="login-forgot-hint" tabIndex={0}>
                    忘记密码？
                  </span>
                </Tooltip>
              </div>
              <Button
                block
                className="login-submit-btn"
                htmlType="submit"
                loading={login.isPending}
                size="large"
                type="primary"
              >
                登录
              </Button>
            </Form>
          </div>
        </div>
      </section>
      <footer className="login-footer">
        <div className="login-footer__copyright">品界网络科技 © 2026</div>
      </footer>
    </main>
  );
}

export default LoginPage;
