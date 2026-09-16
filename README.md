# pinjie-mall

> 高可用标准电商与多级分销全栈商城平台 | FastAPI + Next.js + React + pnpm + Turborepo

本项目派生自 `pinjie-fullstack-base` 企业级全栈母版，核心服务于现代零售电商与多级分销裂变业务。

## 核心业务能力

- **标准电商交易闭环**：SPU / SKU 商品体系、运费模板、购物车、订单状态机流转、库存乐观锁防超卖、微信支付与支付宝支付对接。
- **多级分销与分润网络**：
  - 邀请码与关系链绑定（防窜链、防自环拓扑结构）。
  - 合规两级分销佣金引擎，支持按商品与用户等级自定义让利比例。
  - 双轨资金账本（冻结佣金与可用钱包隔离，退款逆向冲正，到期自动解冻）。
  - 提现申请、风控审核与打款流水审计。
- **高可用与生产就绪**：
  - 读多写少链路多级缓存，Redis 原子预扣减，数据库行级排他锁兜底。
  - 容器无状态化部署，集成健康探针（Liveness / Readiness）与优雅停机。
  - 前后端严格单一契约驱动，由后端自动导出 OpenAPI 契约并一键生成前端 TypeScript 强类型 SDK。

## 技术栈

- **后端**：FastAPI + SQLAlchemy 2.0 async + PostgreSQL + Redis + uv
- **管理端**：Ant Design Pro v6（Umi Max + React 19 + TypeScript + Ant Design 6 + ProComponents 3 + TanStack Query）
- **用户端**：Next.js App Router + React 19 + Tailwind CSS + TanStack Query + Zustand + Lucide
- **共享包**：OpenAPI 自动生成 TypeScript 类型安全请求客户端（`api-client`）、共享 ESLint 配置（`eslint-config`）、共享 TypeScript 配置（`typescript-config`）
- **部署**：Docker + 1Panel OpenResty + GitHub Actions CI/CD

## 快速开始

阅读 [本地开发环境手册](docs/operations/local-dev-environment.md)了解完整环境搭建方式；环境变量分层、VS Code 工作区和 Backend 启动顺序见[环境变量分层与 Backend 本地运行手册](docs/operations/environment-variables-and-backend-local-run.md)。

母版的目标用户、适用场景、目标能力、非目标和完成验收标准见 [产品需求基线](docs/PROJECT_REQUIREMENTS.md)。

## 项目结构

```text
apps/
  backend/              FastAPI 标准后端（领域驱动架构）
  web/                  C 端用户前端（Next.js）
  admin/                B 端管理前端（Ant Design Pro v6 / Umi Max）

packages/
  api-client/           自动生成的 TypeScript SDK（禁止手改）
  eslint-config/        共享 ESLint 配置
  typescript-config/    共享 TypeScript 配置

.agents/                Antigravity 规则桥接
docs/                   项目知识库（索引见 docs/README.md）
plans/                  全栈实施计划、计划规则和永久登记

PROJECT_INDEX.md        项目身份、当前阶段、活动计划和权威入口
openapi.json            后端导出的 OpenAPI 规范（根目录，前端 SDK 唯一来源）
compose.yml             本地开发用（仅 Redis 容器）
compose.prod.yml        生产部署用（三端应用、可选日志消费者和 1Panel 共享基础设施网络）
CHANGELOG.md            已交付能力和版本变化
SECURITY.md             漏洞报告和安全响应规则
```

## 项目索引

- 项目身份、当前阶段、活动计划和权威入口见 [PROJECT_INDEX.md](PROJECT_INDEX.md)。
- 全部实施计划的永久登记见 [plans/INDEX.md](plans/INDEX.md)。
- 母版做什么、服务谁和如何验收见 [docs/PROJECT_REQUIREMENTS.md](docs/PROJECT_REQUIREMENTS.md)。
- `docs/` 下的完整文档清单见 [docs/README.md](docs/README.md)。
- 全栈计划格式和生命周期规则见 [plans/README.md](plans/README.md)。
- 已交付变化见 [CHANGELOG.md](CHANGELOG.md)。

## 开发规范

- 所有任务先读取 `PROJECT_INDEX.md`，确认项目身份、当前阶段、活动计划和权威入口，再以实际文件确认详细实现状态
- 新增功能或模块前，在 `plans/` 创建面向整个 Monorepo 的全栈实施计划，并同步登记到 `plans/INDEX.md`
- 同一能力涉及 Backend、Admin 和 Web 时，在同一份计划中描述完整链路和联合验证
- 母版已经存在的计划文档永久保留；独立派生仓库的初始化例外见 `plans/README.md`，AI 始终不得删除、移动或重命名计划
- 新建、移动或修改专题项目文档后，同步更新 `docs/README.md` 中对应的登记；计划与根索引按各自规则单独同步
- 新建或修改 Markdown 后，运行 `pnpm lint:md` 检查全仓库文档格式
- 后端接口变更后，运行 `pnpm generate-api` 更新前端 SDK
- 提交前运行 `pnpm check:governance`，验证文本、文档索引、计划登记、三态完整性、模块边界和门禁正反例

## 工程治理基线

- 应用状态分为 `empty`、`partial` 和 `ready`。`partial` 必须失败，`empty` 只表示治理检查通过。
- Backend 领域和 Frontend Feature 只通过公开入口协作，禁止跨模块导入内部实现。
- 错误处理采用 Fail Closed，禁止吞错、假成功、弱默认值和静默降级。
- 临时兼容只允许用于有负责人、删除日期、观测和删除测试的受控迁移窗口。
- CI、镜像发布和生产部署相互分离。生产只接受完整镜像 digest，不使用可变标签。

架构边界见 [模块与依赖边界](docs/architecture/module-boundaries.md)，发布和回滚步骤见 [发布与回滚手册](docs/operations/release-and-rollback.md)。

## 母版边界

本仓库只包含通用能力，业务领域扩展通过派生仓库实现：

| 应用 | 母版包含 | 派生仓库扩展 |
| --- | --- | --- |
| `backend/domains/` | auth、users、admin、assets、settings、system | products、orders、payment 等 |
| `web/features/` | auth、account、site、system、user | products、cart、checkout 等 |
| `admin/features/` | auth、users、admins、roles、assets、security、settings、system、account、welcome | products、orders、promotions 等 |

业务扩展参考 `docs/blueprints/` 目录下的蓝图文档。

派生仓库应在 `PROJECT_INDEX.md` 中同时登记派生类型、母版不可变 Tag、完整 40 位 Commit SHA、当前阶段和业务范围。独立业务仓库可以在派生初始化阶段由用户人工一次性清理母版继承计划并重建 `plans/INDEX.md`；母版仓库中的计划永久保留，完整边界见 `plans/README.md` 和 ADR 0015。
