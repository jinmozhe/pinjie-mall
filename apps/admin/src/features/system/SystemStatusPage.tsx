import {
  AuditOutlined,
  CheckCircleFilled,
  CloseCircleFilled,
  DatabaseOutlined,
  ExclamationCircleFilled,
  FileProtectOutlined,
  FolderOpenOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  TeamOutlined,
  ThunderboltOutlined,
  UserOutlined,
} from "@ant-design/icons";
import { ProCard, ProDescriptions } from "@ant-design/pro-components";
import { useQuery } from "@tanstack/react-query";
import { Alert, Button, Col, Divider, Flex, Row, Select, Space, Spin, Statistic, Tag, Typography } from "antd";
import { useState } from "react";

import { PageFrame, formatTime } from "@/components/PageFrame";
import { errorMessage } from "@/lib/api/http";

import { fetchSystemOverview } from "./api";

function formatUptime(seconds: number): string {
  if (seconds < 60) return `${seconds} 秒`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)} 分钟 ${seconds % 60} 秒`;
  if (seconds < 86400) {
    const hours = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    return `${hours} 小时 ${mins} 分钟`;
  }
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  return `${days} 天 ${hours} 小时`;
}

function telemetryValue(value: number | null): number | string {
  return value ?? "--";
}

function telemetrySourceLabel(source: "database" | "redis_cache" | "unavailable"): string {
  if (source === "redis_cache") return "Redis 缓存";
  if (source === "database") return "数据库采样";
  return "暂不可用";
}

function securityStrategyLabel(value: string): string {
  const labels: Record<string, string> = {
    separate_cookie_profiles: "C/B Cookie 隔离",
    double_submit_hmac: "双提交 HMAC 校验",
    single_use_rotation: "单次消费轮换",
  };
  return labels[value] ?? value;
}

const GLOBAL_STATUS_MAP = {
  healthy: {
    bg: "linear-gradient(135deg, #f6ffed 0%, #e6f7ff 100%)",
    border: "#b7eb8f",
    icon: <CheckCircleFilled style={{ fontSize: 32, color: "#52c41a" }} />,
    title: "所有系统组件运行正常",
    tagColor: "success",
  },
  degraded: {
    bg: "linear-gradient(135deg, #fffbe6 0%, #fff7e6 100%)",
    border: "#ffe58f",
    icon: <ExclamationCircleFilled style={{ fontSize: 32, color: "#faad14" }} />,
    title: "部分系统组件处于降级状态",
    tagColor: "warning",
  },
  unhealthy: {
    bg: "linear-gradient(135deg, #fff2f0 0%, #fff1f0 100%)",
    border: "#ffa39e",
    icon: <CloseCircleFilled style={{ fontSize: 32, color: "#ff4d4f" }} />,
    title: "核心基础设施不可用",
    tagColor: "error",
  },
} as const;

const REDIS_STATUS_MAP: Record<string, { color: string; text: string }> = {
  ok: { color: "success", text: "就绪" },
  disabled: { color: "default", text: "未启用" },
  error: { color: "error", text: "异常" },
};

export function SystemStatusPage() {
  const [pollInterval, setPollInterval] = useState<number>(0);

  const query = useQuery({
    queryKey: ["system-overview"],
    queryFn: fetchSystemOverview,
    refetchInterval: pollInterval > 0 ? pollInterval : false,
  });

  const data = query.data;
  const globalStatusKey = data?.status === "healthy" ? "healthy" : data?.status === "degraded" ? "degraded" : "unhealthy";
  const globalStatus = GLOBAL_STATUS_MAP[globalStatusKey];

  return (
    <PageFrame
      title="系统状态"
      description="查看基础设施实时探针、公开运行配置摘要与业务资产规模遥测。"
      action={
        <Space size={12} wrap>
          <Space size={6} wrap>
            <Typography.Text type="secondary" style={{ fontSize: 13 }}>自动刷新：</Typography.Text>
            <Select
              aria-label="自动刷新频率"
              value={pollInterval}
              style={{ width: 110 }}
              onChange={(value) => setPollInterval(value)}
              options={[
                { value: 0, label: "关闭" },
                { value: 15_000, label: "每 15 秒" },
                { value: 30_000, label: "每 30 秒" },
                { value: 60_000, label: "每 60 秒" },
              ]}
            />
          </Space>
          <Button
            aria-label="重新检查状态"
            icon={<ReloadOutlined />}
            loading={query.isFetching}
            onClick={() => query.refetch()}
          >
            重新检查
          </Button>
        </Space>
      }
    >
      {query.isPending ? (
        <div className="center-state" role="status" aria-label="正在加载系统状态">
          <Spin />
        </div>
      ) : null}

      {query.isError && !data ? (
        <Alert
          type="error"
          showIcon
          title="后端服务不可用"
          description={errorMessage(query.error) || "无法获取系统状态概览，请在服务恢复后重试。"}
          action={
            <Button size="small" danger onClick={() => query.refetch()}>
              重试
            </Button>
          }
        />
      ) : null}

      {query.isError && data ? (
        <Alert
          type="warning"
          showIcon
          title="刷新失败，当前展示上次成功数据"
          description={errorMessage(query.error) || "系统概览刷新失败，页面数据可能已经过期。"}
          style={{ marginBottom: 16 }}
          action={
            <Button size="small" onClick={() => query.refetch()}>
              重试
            </Button>
          }
        />
      ) : null}

      {data ? (
        <Space direction="vertical" size={20} style={{ width: "100%" }}>
          {/* 板块 1：全局健康总览横幅 */}
          <div
            style={{
              padding: "20px 24px",
              borderRadius: 8,
              background: globalStatus.bg,
              border: `1px solid ${globalStatus.border}`,
            }}
          >
            <Row gutter={[24, 16]} align="middle">
              <Col xs={24} md={12}>
                <Space align="center" size={12}>
                  {globalStatus.icon}
                  <div>
                    <Space align="center" wrap size={8}>
                      <Typography.Title level={4} style={{ margin: 0, color: "#101828" }}>
                        {globalStatus.title}
                      </Typography.Title>
                      <Tag color={globalStatus.tagColor}>
                        {data.status.toUpperCase()}
                      </Tag>
                    </Space>
                    <Typography.Paragraph type="secondary" style={{ margin: "4px 0 0 0", fontSize: 13 }}>
                      系统发行版本: v{data.release_version} · 部署环境: {data.environment} · 时区: {data.timezone}
                    </Typography.Paragraph>
                  </div>
                </Space>
              </Col>

              <Col xs={24} md={12}>
                <Row gutter={16} justify="end">
                  <Col span={8} style={{ textAlign: "center" }}>
                    <Statistic
                      title={<span style={{ fontSize: 12 }}>数据库延迟</span>}
                      value={data.infrastructure.database.latency_ms}
                      suffix="ms"
                      valueStyle={{ fontSize: 18, color: "#1677ff", fontWeight: 600 }}
                    />
                  </Col>
                  <Col span={8} style={{ textAlign: "center" }}>
                    <Statistic
                      title={<span style={{ fontSize: 12 }}>Redis 延迟</span>}
                      value={data.infrastructure.redis.latency_ms}
                      suffix="ms"
                      valueStyle={{
                        fontSize: 18,
                        color: data.infrastructure.redis.status === "ok" ? "#52c41a" : "#ff4d4f",
                        fontWeight: 600,
                      }}
                    />
                  </Col>
                  <Col span={8} style={{ textAlign: "center" }}>
                    <Statistic
                      title={<span style={{ fontSize: 12 }}>稳定运行时长</span>}
                      value={formatUptime(data.uptime_seconds)}
                      valueStyle={{ fontSize: 16, color: "#722ed1", fontWeight: 600 }}
                    />
                  </Col>
                </Row>
              </Col>
            </Row>
          </div>

          {/* 板块 2：基础设施探针与配置摘要 */}
          <Typography.Title level={5} style={{ margin: "4px 0 0 0", color: "#101828" }}>
            核心基础设施与安全配置
          </Typography.Title>

          <Row gutter={[16, 16]}>
            {/* 1. 数据库 */}
            <Col xs={24} sm={12} lg={6}>
              <ProCard
                headerBordered
                title={
                  <Space>
                    <DatabaseOutlined style={{ color: "#1677ff" }} />
                    <Typography.Text strong>PostgreSQL 数据库</Typography.Text>
                  </Space>
                }
                extra={
                  <Tag color={data.infrastructure.database.status === "ok" ? "success" : "error"}>
                    {data.infrastructure.database.status === "ok" ? "连接正常" : "异常"}
                  </Tag>
                }
                style={{ height: "100%" }}
              >
                <Space direction="vertical" size={6} style={{ width: "100%" }}>
                  <Flex justify="space-between">
                    <Typography.Text type="secondary">探针耗时：</Typography.Text>
                    <Typography.Text strong>{data.infrastructure.database.latency_ms} ms</Typography.Text>
                  </Flex>
                  <Flex justify="space-between">
                    <Typography.Text type="secondary">迁移状态：</Typography.Text>
                    <Typography.Text ellipsis={{ tooltip: data.infrastructure.database.details }} style={{ maxWidth: 120 }}>
                      {data.infrastructure.database.details}
                    </Typography.Text>
                  </Flex>
                </Space>
              </ProCard>
            </Col>

            {/* 2. Redis */}
            <Col xs={24} sm={12} lg={6}>
              <ProCard
                headerBordered
                title={
                  <Space>
                    <ThunderboltOutlined style={{ color: "#52c41a" }} />
                    <Typography.Text strong>Redis 缓存中间件</Typography.Text>
                  </Space>
                }
                extra={
                  <Tag color={REDIS_STATUS_MAP[data.infrastructure.redis.status]?.color || "error"}>
                    {REDIS_STATUS_MAP[data.infrastructure.redis.status]?.text || "异常"}
                  </Tag>
                }
                style={{ height: "100%" }}
              >
                <Space direction="vertical" size={6} style={{ width: "100%" }}>
                  <Flex justify="space-between">
                    <Typography.Text type="secondary">探针耗时：</Typography.Text>
                    <Typography.Text strong>{data.infrastructure.redis.latency_ms} ms</Typography.Text>
                  </Flex>
                  <Flex justify="space-between">
                    <Typography.Text type="secondary">运行模式：</Typography.Text>
                    <Tag>{data.infrastructure.redis.mode}</Tag>
                  </Flex>
                </Space>
              </ProCard>
            </Col>

            {/* 3. 本地存储 */}
            <Col xs={24} sm={12} lg={6}>
              <ProCard
                headerBordered
                title={
                  <Space>
                    <FolderOpenOutlined style={{ color: "#fa8c16" }} />
                    <Typography.Text strong>文件资产存储</Typography.Text>
                  </Space>
                }
                extra={<Tag color="processing">已配置 ({data.infrastructure.storage.driver})</Tag>}
                style={{ height: "100%" }}
              >
                <Space direction="vertical" size={6} style={{ width: "100%" }}>
                  <Flex justify="space-between">
                    <Typography.Text type="secondary">公开访问路径：</Typography.Text>
                    <Typography.Text code copyable>{data.infrastructure.storage.public_base_url}</Typography.Text>
                  </Flex>
                </Space>
              </ProCard>
            </Col>

            {/* 4. 安全引擎 */}
            <Col xs={24} sm={12} lg={6}>
              <ProCard
                headerBordered
                title={
                  <Space>
                    <SafetyCertificateOutlined style={{ color: "#722ed1" }} />
                    <Typography.Text strong>认证与安全引擎</Typography.Text>
                  </Space>
                }
                extra={<Tag color="purple">配置摘要</Tag>}
                style={{ height: "100%" }}
              >
                <Space direction="vertical" size={6} style={{ width: "100%" }}>
                  <Flex justify="space-between">
                    <Typography.Text type="secondary">C/B 会话：</Typography.Text>
                    <Tag>{securityStrategyLabel(data.infrastructure.security.session_isolation)}</Tag>
                  </Flex>
                  <Flex justify="space-between">
                    <Typography.Text type="secondary">CSRF 防御：</Typography.Text>
                    <Tag>{securityStrategyLabel(data.infrastructure.security.csrf_strategy)}</Tag>
                  </Flex>
                  <Flex justify="space-between">
                    <Typography.Text type="secondary">Refresh：</Typography.Text>
                    <Tag>{securityStrategyLabel(data.infrastructure.security.refresh_rotation)}</Tag>
                  </Flex>
                </Space>
              </ProCard>
            </Col>
          </Row>

          <Divider style={{ margin: "4px 0" }} />

          {/* 板块 3：核心业务资产规模概览 */}
          <Flex justify="space-between" align="center" wrap gap={8}>
            <Typography.Title level={5} style={{ margin: "4px 0 0 0", color: "#101828" }}>
              系统资产与遥测概览
            </Typography.Title>
            <Space size={8} wrap>
              <Tag color={data.telemetry.status === "ok" ? "blue" : "error"}>
                {telemetrySourceLabel(data.telemetry.source)}
              </Tag>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                采样于 {formatTime(data.telemetry.sampled_at)}
              </Typography.Text>
            </Space>
          </Flex>

          <Row gutter={[16, 16]}>
            <Col xs={24} sm={12} lg={6}>
              <ProCard hoverable>
                <Flex align="center" gap={16}>
                  <div
                    style={{
                      width: 44,
                      height: 44,
                      borderRadius: 8,
                      background: "#e6f4ff",
                      color: "#1677ff",
                      display: "grid",
                      placeItems: "center",
                      fontSize: 22,
                    }}
                  >
                    <UserOutlined />
                  </div>
                  <div>
                    <Typography.Text type="secondary" style={{ fontSize: 13 }}>普通用户</Typography.Text>
                    <div><Typography.Title level={3} style={{ margin: 0 }}>{telemetryValue(data.telemetry.user_count)}</Typography.Title></div>
                  </div>
                </Flex>
              </ProCard>
            </Col>

            <Col xs={24} sm={12} lg={6}>
              <ProCard hoverable>
                <Flex align="center" gap={16}>
                  <div
                    style={{
                      width: 44,
                      height: 44,
                      borderRadius: 8,
                      background: "#f6ffed",
                      color: "#52c41a",
                      display: "grid",
                      placeItems: "center",
                      fontSize: 22,
                    }}
                  >
                    <TeamOutlined />
                  </div>
                  <div>
                    <Typography.Text type="secondary" style={{ fontSize: 13 }}>管理员与角色</Typography.Text>
                    <div>
                      <Typography.Title level={3} style={{ margin: 0 }}>
                        {telemetryValue(data.telemetry.admin_count)}
                        <span style={{ fontSize: 13, fontWeight: "normal", color: "#8c8c8c", marginLeft: 8 }}>
                          ({telemetryValue(data.telemetry.role_count)} 个启用角色)
                        </span>
                      </Typography.Title>
                    </div>
                  </div>
                </Flex>
              </ProCard>
            </Col>

            <Col xs={24} sm={12} lg={6}>
              <ProCard hoverable>
                <Flex align="center" gap={16}>
                  <div
                    style={{
                      width: 44,
                      height: 44,
                      borderRadius: 8,
                      background: "#fff7e6",
                      color: "#fa8c16",
                      display: "grid",
                      placeItems: "center",
                      fontSize: 22,
                    }}
                  >
                    <FileProtectOutlined />
                  </div>
                  <div>
                    <Typography.Text type="secondary" style={{ fontSize: 13 }}>文件资产</Typography.Text>
                    <div><Typography.Title level={3} style={{ margin: 0 }}>{telemetryValue(data.telemetry.asset_count)}</Typography.Title></div>
                  </div>
                </Flex>
              </ProCard>
            </Col>

            <Col xs={24} sm={12} lg={6}>
              <ProCard hoverable>
                <Flex align="center" gap={16}>
                  <div
                    style={{
                      width: 44,
                      height: 44,
                      borderRadius: 8,
                      background: "#f9f0ff",
                      color: "#722ed1",
                      display: "grid",
                      placeItems: "center",
                      fontSize: 22,
                    }}
                  >
                    <AuditOutlined />
                  </div>
                  <div>
                    <Typography.Text type="secondary" style={{ fontSize: 13 }}>保留期内审计事件</Typography.Text>
                    <div><Typography.Title level={3} style={{ margin: 0 }}>{telemetryValue(data.telemetry.audit_event_count)}</Typography.Title></div>
                  </div>
                </Flex>
              </ProCard>
            </Col>
          </Row>

          <Divider style={{ margin: "4px 0" }} />

          {/* 板块 4：运行环境与配置详情 */}
          <ProDescriptions
            title="运行环境与配置参数"
            bordered
            column={{ xs: 1, sm: 2, lg: 3 }}
            dataSource={{
              backend_stack: `FastAPI ${data.fastapi_version} + CPython ${data.python_version}`,
              admin_stack: "Umi Max + Ant Design 6 + TanStack Query",
              started_at: formatTime(data.started_at),
              environment: data.environment,
              timezone: data.timezone,
              cors_origin_count: data.cors_origin_count,
            }}
            columns={[
              { title: "后端运行时", dataIndex: "backend_stack" },
              { title: "管理端技术栈", dataIndex: "admin_stack" },
              { title: "服务启动时间", dataIndex: "started_at" },
              { title: "部署环境", dataIndex: "environment" },
              { title: "服务器基准时区", dataIndex: "timezone" },
              { title: "CORS 信任源数量", dataIndex: "cors_origin_count" },
            ]}
          />
        </Space>
      ) : null}
    </PageFrame>
  );
}

export default SystemStatusPage;
