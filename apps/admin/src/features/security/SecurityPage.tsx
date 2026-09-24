import type { AuditEventRead, LoginEventRead, RequestLogRead } from "@pinjie/api-client";
import { ProTable } from "@ant-design/pro-components";
import { useQuery } from "@tanstack/react-query";
import { Alert, Button, Drawer, Tabs, Tag, Typography } from "antd";
import { useState } from "react";

import { PageFrame, QueryState, formatTime } from "@/components/PageFrame";
import { canAccess, useCurrentAdmin } from "@/features/auth";
import { adminApi } from "@/lib/api/admin";
import { ApiError, errorMessage } from "@/lib/api/http";

const principalLabels: Record<string, string> = { user: "用户", admin: "管理员" };
const loginEventLabels: Record<string, string> = {
  login: "登录",
  logout: "退出",
  refresh: "刷新会话",
  password_changed: "修改密码",
};
const loginReasonLabels: Record<string, string> = {
  success: "成功",
  invalid_credentials: "凭据无效",
  inactive: "账号停用",
  revoked: "会话已撤销",
  refresh_reuse: "Refresh Token 重放",
};
const auditResultLabels: Record<string, string> = {
  started: "处理中",
  succeeded: "成功",
  denied: "拒绝",
  failed: "失败",
};
const auditResultColorMap: Record<string, string> = {
  succeeded: "success",
  started: "processing",
};

function translatedLabel(labels: Record<string, string>, value: string) {
  return labels[value] ?? `其他（${value}）`;
}

function LoginEvents() {
  const [page, setPage] = useState(1);
  const query = useQuery({ queryKey: ["login-events", page], queryFn: () => adminApi.loginEvents(page) });
  return (
    <>
      <QueryState loading={query.isLoading} error={query.isError ? errorMessage(query.error) : undefined} onRetry={() => void query.refetch()} />
      {query.data && (
        <ProTable<LoginEventRead>
          className="controlled-table"
          rowKey="id"
          headerTitle="登录事件列表"
          dataSource={query.data.items}
          search={false}
          options={{ density: true, fullScreen: true, reload: () => void query.refetch(), setting: true }}
          cardProps={false}
          pagination={{ current: page, pageSize: query.data.page_size, total: query.data.total, showSizeChanger: false, onChange: setPage }}
          scroll={{ x: "max-content" }}
          columns={[
    { title: "时间", dataIndex: "occurred_at", width: 170, render: (_, row) => formatTime(row.occurred_at) },
    { title: "主体", dataIndex: "principal_type", width: 90, render: (_, row) => translatedLabel(principalLabels, row.principal_type) },
    { title: "事件", dataIndex: "event_type", width: 120, render: (_, row) => translatedLabel(loginEventLabels, row.event_type) },
    { title: "结果", dataIndex: "succeeded", width: 90, render: (_, row) => <Tag color={row.succeeded ? "success" : "error"}>{row.succeeded ? "成功" : "拒绝"}</Tag> },
    { title: "原因", dataIndex: "reason_code", render: (_, row) => translatedLabel(loginReasonLabels, row.reason_code) },
    { title: "来源", dataIndex: "ip_address", width: 140, render: (_, row) => row.ip_address || "-" },
            { title: "Request ID", dataIndex: "request_id", width: "1%", onHeaderCell: () => ({ style: { whiteSpace: "nowrap" } }), onCell: () => ({ style: { whiteSpace: "nowrap" } }), render: (_, row) => <Typography.Text code copyable>{row.request_id}</Typography.Text> },
          ]}
        />
      )}
    </>
  );
}

function AuditEvents() {
  const [page, setPage] = useState(1);
  const query = useQuery({ queryKey: ["audit-events", page], queryFn: () => adminApi.auditEvents(page) });
  return (
    <>
      <QueryState loading={query.isLoading} error={query.isError ? errorMessage(query.error) : undefined} onRetry={() => void query.refetch()} />
      {query.data && (
        <ProTable<AuditEventRead>
          className="controlled-table"
          rowKey="id"
          headerTitle="审计事件列表"
          dataSource={query.data.items}
          search={false}
          options={{ density: true, fullScreen: true, reload: () => void query.refetch(), setting: true }}
          cardProps={false}
          pagination={{ current: page, pageSize: query.data.page_size, total: query.data.total, showSizeChanger: false, onChange: setPage }}
          scroll={{ x: "max-content" }}
          columns={[
            { title: "时间", dataIndex: "occurred_at", width: 170, render: (_, row) => formatTime(row.occurred_at) },
            { title: "动作", dataIndex: "action" },
            { title: "主体", dataIndex: "actor_type", width: 90 },
            { title: "目标", key: "target", render: (_, row) => `${row.target_type}:${row.target_id || "-"}` },
            { title: "目标版本", dataIndex: "target_revision", width: 100, render: (_, row) => row.target_revision ?? "-" },
            { title: "结果", dataIndex: "result", width: 100, render: (_, row) => <Tag color={auditResultColorMap[row.result] ?? "error"}>{translatedLabel(auditResultLabels, row.result)}</Tag> },
            { title: "Request ID", dataIndex: "request_id", width: "1%", onHeaderCell: () => ({ style: { whiteSpace: "nowrap" } }), onCell: () => ({ style: { whiteSpace: "nowrap" } }), render: (_, row) => <Typography.Text code copyable>{row.request_id}</Typography.Text> },
          ]}
        />
      )}
    </>
  );
}

function RequestLogs() {
  const [page, setPage] = useState(1);
  const [selectedBody, setSelectedBody] = useState<{ requestId: string; body: string } | null>(null);
  const query = useQuery({ queryKey: ["request-logs", page], queryFn: () => adminApi.requestLogs(page), retry: false });
  if (query.error instanceof ApiError && query.error.status === 409) {
    return <Alert showIcon type="info" title="请求元数据日志当前未启用" description="生产需要时将 REQUEST_LOG_MODE 设置为 metadata，并运行独立消费者。" />;
  }
  return (
    <>
      <QueryState
        loading={query.isLoading}
        error={query.isError ? errorMessage(query.error) : undefined}
        onRetry={() => void query.refetch()}
      />
      {query.data && (
        <ProTable<RequestLogRead>
          className="controlled-table"
          rowKey="id"
          headerTitle="请求元数据列表"
          dataSource={query.data.items}
          search={false}
          options={{ density: true, fullScreen: true, reload: () => void query.refetch(), setting: true }}
          cardProps={false}
          pagination={{ current: page, pageSize: query.data.page_size, total: query.data.total, showSizeChanger: false, onChange: setPage }}
          scroll={{ x: "max-content" }}
          columns={[
            { title: "时间", dataIndex: "occurred_at", width: 170, render: (_, row) => formatTime(row.occurred_at) },
            { title: "方法", dataIndex: "method", width: 80 },
            { title: "路由模板", dataIndex: "route_template" },
            {
              title: "状态",
              dataIndex: "status_code",
              width: 90,
              render: (_, row) => <Tag color={row.status_code < 400 ? "success" : "error"}>{row.status_code}</Tag>,
            },
            { title: "耗时", dataIndex: "duration_ms", width: 100, render: (_, row) => `${row.duration_ms} ms` },
            {
              title: "错误入参",
              key: "request_body",
              width: 110,
              render: (_, row) =>
                row.request_body ? (
                  <Button
                    type="link"
                    onClick={() => setSelectedBody({ requestId: row.request_id, body: row.request_body ?? "" })}
                  >
                    查看入参
                  </Button>
                ) : (
                  "-"
                ),
            },
            {
              title: "Request ID",
              dataIndex: "request_id",
              width: "1%",
              onHeaderCell: () => ({ style: { whiteSpace: "nowrap" } }),
              onCell: () => ({ style: { whiteSpace: "nowrap" } }),
              render: (_, row) => <Typography.Text code copyable>{row.request_id}</Typography.Text>,
            },
          ]}
        />
      )}
      <Drawer title="错误请求入参" open={selectedBody !== null} onClose={() => setSelectedBody(null)} size={560}>
        <Typography.Paragraph>
          Request ID：<Typography.Text code copyable>{selectedBody?.requestId}</Typography.Text>
        </Typography.Paragraph>
        <pre style={{ maxHeight: "60vh", overflow: "auto", whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>
          {selectedBody?.body}
        </pre>
      </Drawer>
    </>
  );
}

export function SecurityPage() {
  const current = useCurrentAdmin();
  const items = [
    canAccess(current, "security:login-events:read")
      ? { key: "login", label: "登录事件", children: <LoginEvents /> }
      : null,
    canAccess(current, "security:audit-events:read")
      ? { key: "audit", label: "审计事件", children: <AuditEvents /> }
      : null,
    canAccess(current, "system:request-logs:read")
      ? { key: "request", label: "请求元数据", children: <RequestLogs /> }
      : null,
  ].filter((item) => item !== null);
  return <PageFrame title="安全日志" description="登录事件与审计事件是安全事实，请求元数据仅用于可选观测。"><Tabs items={items} /></PageFrame>;
}

export default SecurityPage;
