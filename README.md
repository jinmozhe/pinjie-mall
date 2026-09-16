# pinjie-mall

> 标准电商与多级分销全栈商城平台 | FastAPI + Ant Design Pro + pnpm + Turborepo

`pinjie-mall` 是独立维护、独立发布的商城仓库。用户端形态确定为微信小程序；当前阶段建设 FastAPI 业务能力和 Ant Design Pro 管理后台，小程序端将通过后续专项计划实施。

## 当前边界

- `apps/web` 是冻结保留的历史骨架，禁止开发、启动、构建、测试、发布和部署。
- 本地服务只允许 Backend 使用 8000 端口、Admin 使用 3001 端口。禁止监听或暴露 3000 及其他 Web 端口。
- 商品、库存、购物车、订单、支付和分销是项目目标，当前尚未交付，后续按全栈计划实施。
- 当前已具备认证、用户、管理员、RBAC、文件资产、系统设置、审计、健康检查与 OpenAPI 契约等基础能力。

## 技术栈

- **Backend**：FastAPI、SQLAlchemy 2 async、PostgreSQL、Redis、Alembic、uv
- **Admin**：Ant Design Pro v6、Umi Max、React、TypeScript、ProComponents、TanStack Query
- **用户端**：微信小程序，当前阶段不创建小程序工程
- **共享包**：OpenAPI 生成的 TypeScript API Client、ESLint 配置、TypeScript 配置
- **部署**：Backend 与 Admin 独立容器、1Panel OpenResty、GitHub Actions、CNB、TCR

## 项目结构

```text
apps/
  backend/              FastAPI 后端
  admin/                Ant Design Pro 管理后台
  web/                  冻结保留的历史骨架

packages/
  api-client/           自动生成的 TypeScript SDK
  eslint-config/        共享 ESLint 配置
  typescript-config/    共享 TypeScript 配置

docs/                   项目文档
plans/                  全栈实施计划及永久登记
```

## 开发入口

先阅读 [项目索引](PROJECT_INDEX.md) 确认当前阶段和活动计划。环境搭建及 Backend 启动见[本地开发环境手册](docs/operations/local-dev-environment.md)，环境变量分层见[环境变量与 Backend 本地运行手册](docs/operations/environment-variables-and-backend-local-run.md)。

- 根 `pnpm dev` 仅启动 Admin。
- Backend 与 Admin 分别遵守其目录中的 `AGENTS.md`。
- 公开 API 变化依次执行 Backend 实现、导出 `openapi.json`、运行 `pnpm generate-api`、适配 Admin 和后续小程序消费者。
- 新增跨端能力需创建一份全栈计划，并登记到 [plans/INDEX.md](plans/INDEX.md)。

## 项目资料

- [产品需求基线](docs/PROJECT_REQUIREMENTS.md)：目标、范围、验收边界
- [文档索引](docs/README.md)：架构、运维、ADR 与业务设计入口
- [计划规范](plans/README.md)：计划创建、更新与保护规则
- [变更记录](CHANGELOG.md)：已交付能力与治理变化

## 工程原则

- Backend、Admin 和共享包只能通过明确公开入口协作。
- 失败必须明确传播，禁止假成功、弱默认值和静默降级。
- 根 `openapi.json` 是唯一机器契约，`packages/api-client/src/` 只能由生成链更新。
- 生产只使用完整镜像 digest；发布、部署和回滚需要单独授权。
