# pinjie-mall

> 标准电商与多级分销全栈商城平台 | FastAPI + Ant Design Pro + pnpm + Turborepo

`pinjie-mall` 是独立维护、独立发布的商城仓库。用户端形态确定为微信小程序；Backend 的 M1 至 M4 商城领域及 Admin 电商运营页面已完成本地实现，小程序工程留待后续专项。

## 当前边界

- `apps/web` 是冻结保留的历史骨架，禁止开发、启动、构建、测试、发布和部署。
- 本地服务只允许 Backend 使用 8000 端口、Admin 使用 3001 端口。禁止监听或暴露 3000 及其他 Web 端口。
- Backend 已完成商品、库存、购物车、订单、支付售后和会员分销的 M1 至 M4 本地实现；本地迁移、权限目录与真实 PostgreSQL/Redis pytest 已验证，真实渠道支付、退款、提现和生产环境仍需专项验证。
- Admin 在既有通用管理功能上增加商品中心、订单履约、退款审核、支付对账、会员推荐、佣金、钱包与提现查询审核；前端动态交互尚未执行浏览器或 Vitest 验收。
- 小程序工程尚未初始化，目标目录为 `apps/miniapp`；产品范围见 [小程序 PRD](docs/MINIAPP_PRD.md)，目录与分层见[小程序架构文档](docs/architecture/miniapp-architecture.md)。
- 当前已具备认证、用户、管理员、RBAC、文件资产、系统设置、审计、健康检查与 OpenAPI 契约等基础能力。

## 技术栈

- **Backend**：FastAPI、SQLAlchemy 2 async、PostgreSQL、Redis、Alembic、uv
- **Admin**：Ant Design Pro v6、Umi Max、React、TypeScript、ProComponents、TanStack Query
- **用户端**：微信小程序，工程目录预留为 `apps/miniapp`，当前尚未初始化
- **共享包**：OpenAPI 生成的 TypeScript API Client、ESLint 配置、TypeScript 配置
- **部署**：Backend 与 Admin 独立容器、1Panel OpenResty、GitHub Actions、CNB、TCR

## 项目结构

```text
apps/
  backend/              FastAPI 后端
  admin/                Ant Design Pro 管理后台
  miniapp/              微信小程序目标目录，尚未初始化工程
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
- 小程序当前没有可运行的开发脚本；初始化时沿用根 pnpm workspace 和唯一锁文件，不创建子应用锁文件。
- 新增跨端能力需创建一份全栈计划，并登记到 [plans/INDEX.md](plans/INDEX.md)。

## 项目资料

- [产品需求基线](docs/PROJECT_REQUIREMENTS.md)：目标、范围、验收边界
- [微信小程序 PRD](docs/MINIAPP_PRD.md)：小程序用户流程、需求编号、交付分组和验收条件
- [小程序架构文档](docs/architecture/miniapp-architecture.md)：目标目录、Feature 分层、请求链路和状态归属
- [文档索引](docs/README.md)：架构、运维、ADR 与业务设计入口
- [计划规范](plans/README.md)：计划创建、更新与保护规则
- [变更记录](CHANGELOG.md)：已交付能力与治理变化

## 工程原则

- Backend、Admin 和共享包只能通过明确公开入口协作。
- 失败必须明确传播，禁止假成功、弱默认值和静默降级。
- 根 `openapi.json` 是唯一机器契约，`packages/api-client/src/` 只能由生成链更新。
- 生产只使用完整镜像 digest；发布、部署和回滚需要单独授权。
