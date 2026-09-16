import {
  AuditOutlined,
  CloudServerOutlined,
  DashboardOutlined,
  HomeOutlined,
  RocketOutlined,
  SafetyCertificateOutlined,
  TeamOutlined,
  UserOutlined,
} from "@ant-design/icons";
import { ProCard } from "@ant-design/pro-components";
import { history } from "@umijs/max";
import { Button, Col, Divider, Flex, Row, Space, Tag, Typography } from "antd";

import { PageFrame } from "@/components/PageFrame";
import { useCurrentAdmin } from "@/features/auth";

export function WelcomePage() {
  const current = useCurrentAdmin();

  return (
    <PageFrame
      title="欢迎使用 Pinjie Mall 管理后台"
      description="独立商城的运营管理控制台，当前阶段聚焦后端领域模型与后台管理能力。"
    >
      <Space direction="vertical" size={24} style={{ width: "100%" }}>
        {/* 顶部主横幅 Hero Card */}
        <div
          style={{
            padding: "28px 32px",
            borderRadius: 8,
            background: "linear-gradient(135deg, #1677ff 0%, #0958d9 60%, #003eb3 100%)",
            color: "#ffffff",
            boxShadow: "0 8px 24px -4px rgba(22, 119, 255, 0.28)",
          }}
        >
          <Row gutter={[24, 24]} align="middle">
            <Col xs={24} md={16}>
              <Space direction="vertical" size={8}>
                <Space wrap>
                  <Tag style={{ background: "rgba(255,255,255,0.2)", color: "#ffffff", border: "none" }}>
                    独立商城基线
                  </Tag>
                  <Tag style={{ background: "rgba(255,255,255,0.2)", color: "#ffffff", border: "none" }}>
                    Ant Design 6 Pro V6
                  </Tag>
                </Space>
                <Typography.Title level={2} style={{ color: "#ffffff", margin: 0, fontWeight: 600 }}>
                  您好，{current?.display_name || current?.username || "管理员"}！
                </Typography.Title>
                <Typography.Paragraph style={{ color: "rgba(255, 255, 255, 0.88)", fontSize: 15, margin: 0, maxWidth: 640 }}>
                  本系统是 Pinjie Mall 的统一管理控制台。采用模块化单体架构，提供后台运营所需的权限管理、系统设置与安全审计能力；商品、订单和分销等商城业务将在后续计划中实施。
                </Typography.Paragraph>
              </Space>
            </Col>
            <Col xs={24} md={8} style={{ textAlign: "right" }}>
              <Button
                type="default"
                size="large"
                icon={<RocketOutlined />}
                style={{
                  background: "#ffffff",
                  color: "#0958d9",
                  border: "none",
                  fontWeight: 600,
                  boxShadow: "0 4px 12px rgba(0,0,0,0.15)",
                }}
                onClick={() => history.push("/users")}
              >
                开始管理工作区
              </Button>
            </Col>
          </Row>
        </div>

        {/* 核心特性与架构介绍 */}
        <Typography.Title level={4} style={{ margin: "8px 0 0 0", color: "#101828" }}>
          管理后台基础能力
        </Typography.Title>

        <Row gutter={[16, 16]}>
          <Col xs={24} sm={12} lg={6}>
            <ProCard
              headerBordered
              title={
                <Space>
                  <CloudServerOutlined style={{ color: "#1677ff" }} />
                  <Typography.Text strong>高性能后端</Typography.Text>
                </Space>
              }
              style={{ height: "100%" }}
            >
              <Typography.Paragraph type="secondary" style={{ fontSize: 13, marginBottom: 8 }}>
                基于 FastAPI + CPython 3.14 + uv 依赖体系，搭配异步 SQLAlchemy 2.0、PostgreSQL 18 及 Redis 8 缓存。
              </Typography.Paragraph>
              <Space wrap size={[4, 4]}>
                <Tag>FastAPI</Tag>
                <Tag>Python 3.14</Tag>
                <Tag>PostgreSQL</Tag>
                <Tag>Redis</Tag>
              </Space>
            </ProCard>
          </Col>

          <Col xs={24} sm={12} lg={6}>
            <ProCard
              headerBordered
              title={
                <Space>
                  <SafetyCertificateOutlined style={{ color: "#52c41a" }} />
                  <Typography.Text strong>安全与会话隔离</Typography.Text>
                </Space>
              }
              style={{ height: "100%" }}
            >
              <Typography.Paragraph type="secondary" style={{ fontSize: 13, marginBottom: 8 }}>
                双轨 Cookie Profile 隔离 C/B 端会话，单飞 Refresh Token 轮换，严格 CSRF 防护与敏感操作二次确认密码。
              </Typography.Paragraph>
              <Space wrap size={[4, 4]}>
                <Tag color="green">C/B 会话隔离</Tag>
                <Tag color="green">二次确认</Tag>
                <Tag color="green">RBAC</Tag>
              </Space>
            </ProCard>
          </Col>

          <Col xs={24} sm={12} lg={6}>
            <ProCard
              headerBordered
              title={
                <Space>
                  <TeamOutlined style={{ color: "#722ed1" }} />
                  <Typography.Text strong>现代化管理控制台</Typography.Text>
                </Space>
              }
              style={{ height: "100%" }}
            >
              <Typography.Paragraph type="secondary" style={{ fontSize: 13, marginBottom: 8 }}>
                Umi Max + Ant Design 6 + ProComponents，配合 TanStack Query 响应式数据流与官方浅色高质感视觉体系。
              </Typography.Paragraph>
              <Space wrap size={[4, 4]}>
                <Tag color="purple">Umi Max</Tag>
                <Tag color="purple">Ant Design 6</Tag>
                <Tag color="purple">ProTable</Tag>
              </Space>
            </ProCard>
          </Col>

          <Col xs={24} sm={12} lg={6}>
            <ProCard
              headerBordered
              title={
                <Space>
                  <HomeOutlined style={{ color: "#fa8c16" }} />
                  <Typography.Text strong>Next.js 用户端</Typography.Text>
                </Space>
              }
              style={{ height: "100%" }}
            >
              <Typography.Paragraph type="secondary" style={{ fontSize: 13, marginBottom: 8 }}>
                Next.js + React + Tailwind CSS，具备服务端 SSR 认证恢复、受限 BFF 管道及桌面移动端自适应。
              </Typography.Paragraph>
              <Space wrap size={[4, 4]}>
                <Tag color="orange">Next.js</Tag>
                <Tag color="orange">SSR</Tag>
                <Tag color="orange">Tailwind</Tag>
              </Space>
            </ProCard>
          </Col>
        </Row>

        <Divider style={{ margin: "12px 0" }} />

        {/* 快捷入口卡片 */}
        <Typography.Title level={4} style={{ margin: "0 0 0 0", color: "#101828" }}>
          管理快捷入口
        </Typography.Title>

        <Row gutter={[16, 16]}>
          <Col xs={24} sm={12} md={6}>
            <ProCard
              hoverable
              onClick={() => history.push("/users")}
            >
              <Flex align="center" gap={12}>
                <div
                  style={{
                    width: 42,
                    height: 42,
                    borderRadius: 8,
                    background: "#e6f4ff",
                    color: "#1677ff",
                    display: "grid",
                    placeItems: "center",
                    fontSize: 20,
                  }}
                >
                  <UserOutlined />
                </div>
                <div>
                  <Typography.Text strong style={{ fontSize: 15 }}>用户管理</Typography.Text>
                  <div><Typography.Text type="secondary" style={{ fontSize: 12 }}>查询账户、处理资料与会话</Typography.Text></div>
                </div>
              </Flex>
            </ProCard>
          </Col>

          <Col xs={24} sm={12} md={6}>
            <ProCard
              hoverable
              onClick={() => history.push("/admins")}
            >
              <Flex align="center" gap={12}>
                <div
                  style={{
                    width: 42,
                    height: 42,
                    borderRadius: 8,
                    background: "#f6ffed",
                    color: "#52c41a",
                    display: "grid",
                    placeItems: "center",
                    fontSize: 20,
                  }}
                >
                  <TeamOutlined />
                </div>
                <div>
                  <Typography.Text strong style={{ fontSize: 15 }}>管理员</Typography.Text>
                  <div><Typography.Text type="secondary" style={{ fontSize: 12 }}>管理身份、超管保护与分配角色</Typography.Text></div>
                </div>
              </Flex>
            </ProCard>
          </Col>

          <Col xs={24} sm={12} md={6}>
            <ProCard
              hoverable
              onClick={() => history.push("/security")}
            >
              <Flex align="center" gap={12}>
                <div
                  style={{
                    width: 42,
                    height: 42,
                    borderRadius: 8,
                    background: "#f9f0ff",
                    color: "#722ed1",
                    display: "grid",
                    placeItems: "center",
                    fontSize: 20,
                  }}
                >
                  <AuditOutlined />
                </div>
                <div>
                  <Typography.Text strong style={{ fontSize: 15 }}>安全日志</Typography.Text>
                  <div><Typography.Text type="secondary" style={{ fontSize: 12 }}>登录审计、操作事件与元数据</Typography.Text></div>
                </div>
              </Flex>
            </ProCard>
          </Col>

          <Col xs={24} sm={12} md={6}>
            <ProCard
              hoverable
              onClick={() => history.push("/system")}
            >
              <Flex align="center" gap={12}>
                <div
                  style={{
                    width: 42,
                    height: 42,
                    borderRadius: 8,
                    background: "#fff7e6",
                    color: "#fa8c16",
                    display: "grid",
                    placeItems: "center",
                    fontSize: 20,
                  }}
                >
                  <DashboardOutlined />
                </div>
                <div>
                  <Typography.Text strong style={{ fontSize: 15 }}>系统状态</Typography.Text>
                  <div><Typography.Text type="secondary" style={{ fontSize: 12 }}>健康检查、数据库与 Redis 探测</Typography.Text></div>
                </div>
              </Flex>
            </ProCard>
          </Col>
        </Row>
      </Space>
    </PageFrame>
  );
}

export default WelcomePage;
