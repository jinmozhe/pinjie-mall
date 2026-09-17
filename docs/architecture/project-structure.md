# 仓库文件结构说明

> 文档归属：`docs/architecture/project-structure.md`
> 适用仓库：`pinjie-mall`
> 最后更新：2026-09-17

## 1. 当前结构

Pinjie Mall 是独立维护的 pnpm Monorepo。商城面向用户的唯一 C 端形态是微信小程序，当前仓库前阶段只建设 Backend 和 Admin。小程序工程会在后续专项计划中引入。

```text
.
├── apps/
│   ├── backend/       FastAPI 模块化单体、Alembic、uv.lock
│   ├── admin/         Umi Max 与 Ant Design Pro 管理后台
│   └── web/           冻结的历史骨架，禁止启动、构建、测试、发布与部署
├── packages/
│   ├── api-client/    由根 openapi.json 自动生成的客户端
│   ├── eslint-config/ 共享 ESLint 配置
│   └── typescript-config/ 共享 TypeScript 配置
├── docs/
│   ├── adr/           架构决策
│   ├── architecture/  当前架构机制
│   ├── blueprints/    后续商城业务蓝图
│   └── operations/    本地开发、发布和恢复步骤
├── plans/             永久保留的实施计划及索引
├── scripts/
│   ├── ci/            本地与 CI 治理门禁
│   ├── e2e/           Admin 验证启动器
│   └── release/       Backend、Admin 镜像组合校验
├── compose.prod.yml   Backend、可选日志消费者和 Admin 的生产编排
├── openapi.json       Backend 导出的唯一 OpenAPI 契约
├── PROJECT_INDEX.md   项目身份、阶段和活动计划导航
└── AGENTS.md          全仓库长期规则
```

`.git`、`.venv`、`node_modules`、缓存、构建产物、真实 `.env`、日志、上传和运行数据不属于版本化项目结构。

## 2. 应用边界

| 范围 | 职责 | 当前状态 |
| --- | --- | --- |
| `apps/backend` | FastAPI API、领域模型、认证授权、数据访问、迁移和 OpenAPI 导出 | 当前开发重点 |
| `apps/admin` | 运营管理、权限、系统设置与安全审计 | 当前开发重点 |
| `apps/web` | 历史 Next.js 用户端代码 | 永久冻结 |
| `apps/miniapp` | 面向消费者的微信商城交互 | 本地目录存在，尚未初始化工程 |

Backend 与 Admin 不得相互直接引用。跨应用共享只能经由 `packages/` 中的公共包，详细依赖规则以[模块边界](module-boundaries.md)为准。

小程序的目标目录与执行链路见[小程序目录与应用架构](miniapp-architecture.md)，产品范围见[微信小程序 PRD](../MINIAPP_PRD.md)。本地空目录不属于已交付应用结构；初始化时按实际功能创建文件，不为目录示例增加空占位工程，也不使用另一套 `apps/miniprogram` 命名。

冻结 Web 的规则由根 [AGENTS.md](../../AGENTS.md)、`apps/web/AGENTS.md` 与 [ADR 0016](../adr/0016-独立商城基线与Web停用决策.md)共同定义：

- `apps/web` 保留用于历史追溯和静态治理。
- `scripts/disabled-web.mjs` 阻断开发、构建、启动和测试命令。
- `compose.prod.yml`、CNB、GitHub Actions 完整验证与镜像发布均不包含 Web 服务或 3000 端口。
- 恢复任何 Web 运行能力需要新的全栈计划和明确产品决策。

## 3. 配置分层

| 层级 | 文件位置 | 职责 |
| --- | --- | --- |
| 部署层 | 根 `.env.example` | `BACKEND_IMAGE`、`ADMIN_IMAGE` 的完整 TCR digest 引用 |
| 后端层 | `apps/backend/.env.example` | 数据库、Redis、运行环境、微信小程序与 Admin Origin、认证密钥 |
| Admin 层 | `apps/admin/.env.example` | 可选 API 地址，默认经同域 `/api/v1` 代理 |
| 冻结 Web 层 | `apps/web/.env.example` | 历史参考，禁止作为运行时配置 |

真实 `.env`、密钥、密码和生产数据不进入版本控制。生产 Compose 只读取根镜像变量和 `apps/backend/.env` 中的运行配置，具体步骤见[环境变量分层与 Backend 本地运行手册](../operations/environment-variables-and-backend-local-run.md)。

## 4. 契约与共享包

```text
apps/backend 源码
        ↓
scripts/export_openapi.py
        ↓
根 openapi.json（禁止手工修改）
        ↓
pnpm generate-api
        ↓
packages/api-client/src/（禁止手工修改）
        ↓
apps/admin 与后续小程序消费者
```

公开 API 变更必须按“后端实现、导出 OpenAPI、生成客户端、适配消费者”的顺序完成。生成链路及边界门禁禁止维护另一份 DTO 或手工客户端副本。

## 5. 文档与计划

| 文件或目录 | 权威职责 |
| --- | --- |
| `PROJECT_INDEX.md` | 项目身份、阶段、活动计划和权威入口 |
| `docs/PROJECT_REQUIREMENTS.md` | 商城目标用户、能力、非目标和验收边界 |
| `docs/adr/` | 长期架构决策 |
| `docs/architecture/` | 当前架构机制和边界 |
| `docs/operations/` | 开发、发布、部署、恢复步骤 |
| `plans/README.md` | 计划创建、状态和保护规则 |
| `plans/INDEX.md` | 全部计划的永久登记 |
| `CHANGELOG.md` | 已交付变化 |

计划按完整业务能力或工程目标组织，不按应用建立互不关联的计划目录。计划文件和登记都是商城项目资产，AI 不得删除、移动、重命名或替换。

## 6. 运行与交付

本地开发使用 `uv` 管理 Backend Python 依赖，使用根 `pnpm-lock.yaml` 管理 Admin 及公共包 Node 依赖。生产容器只允许 Backend 与 Admin 两张不可变镜像；发布配置使用商城专属的 `pjwl/pinjie-mall`、`pjwl/pinjie-mall-secrets` 与 `ccr.ccs.tencentyun.com/pinjie-mall` 命名。

这些本地模板不证明远端仓库、命名空间、Secret 或部署环境已经创建。实际发布与部署必须按[GitHub Actions 工作流说明](../operations/github-actions-workflows.md)和[发布与回滚手册](../operations/release-and-rollback.md)获取独立授权并完成远端核验。
