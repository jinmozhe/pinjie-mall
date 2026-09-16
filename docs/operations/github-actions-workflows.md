# GitHub Actions 工作流说明

## 1. 适用范围

本文说明 Pinjie Mall 当前 GitHub Actions 配置。执行事实以 `.github/workflows/` 中的 YAML 为准。商城前阶段只运行 Backend 与 Admin；`apps/web` 已永久冻结，不允许构建、启动、发布或部署。

镜像发布和生产部署必须分别取得明确授权。日常 Push、Pull Request 与本地交付不包含这些操作。

## 2. 工作流

| 工作流 | 配置文件 | 触发方式 | 当前职责 |
| --- | --- | --- | --- |
| CI - Governance | [ci-governance.yml](../../.github/workflows/ci-governance.yml) | `main` Push、目标为 `main` 的 Pull Request | 文档、工作区、依赖与治理门禁 |
| CI - Backend | [ci-backend.yml](../../.github/workflows/ci-backend.yml) | `main` Push、目标为 `main` 的 Pull Request | Backend 静态、导入边界、应用导入与 OpenAPI 契约检查 |
| CI - Frontend | [ci-frontend.yml](../../.github/workflows/ci-frontend.yml) | `main` Push、目标为 `main` 的 Pull Request | Admin lint、typecheck 与冻结 Web 的静态检查 |
| CI - Full Validation | [ci-e2e.yml](../../.github/workflows/ci-e2e.yml) | 人工触发 | Backend pytest、Admin Vitest 和 production build、Admin 浏览器验证 |
| Security | [security.yml](../../.github/workflows/security.yml) | `main` Push、目标为 `main` 的 Pull Request、定时 | 密钥、依赖和静态安全检查 |
| Handoff Source to CNB | [publish-images.yml](../../.github/workflows/publish-images.yml) | 人工触发 | 以固定 Commit SHA 交接商城源码到 CNB |
| Deploy Production | [deploy-production.yml](../../.github/workflows/deploy-production.yml) | 人工触发 | 用固定 Backend 与 Admin digest 更新生产环境 |

`validate-candidate-images.yml` 保留为候选镜像验证工具，不由日常交付自动触发。

## 3. 日常门禁

目标为 `main` 的 Pull Request 和 `main` Push 会独立运行 Governance、Backend、Frontend 和 Security。它们只运行轻量检查，不运行 pytest、Vitest、production build、Playwright、数据库迁移或镜像发布。

Frontend 工作流会读取工作区状态。Admin 为 `ready` 时运行 lint 与 typecheck。冻结 Web 只允许静态检查，任何 Web 运行时命令均由 `scripts/disabled-web.mjs` 明确失败。

Backend 工作流根据工作区状态运行 Ruff、格式、Mypy、导入边界、编译、应用导入及 OpenAPI 契约检查。公开 API 变化还会导出 `openapi.json`、生成 `packages/api-client/src/` 并检查漂移。

## 4. 人工完整验证

`CI - Full Validation` 只能从默认分支人工触发，并要求属于默认分支历史的完整 40 位 Commit SHA。

| 模式 | Backend | Admin | 浏览器 |
| --- | --- | --- | --- |
| `full` | pytest 与隔离 PostgreSQL、Redis | Vitest、production build、Nginx dist | Chromium Playwright，Admin 桌面和移动入口 |
| `smoke` | pytest 与隔离 PostgreSQL、Redis | production build、Nginx dist，Vitest 记录为未执行 | Chromium Playwright，质量页与桌面 Stage C |

两种模式均只启动 Backend 和 Admin。测试环境中的 `WEB_ORIGINS` 使用 `https://miniapp.invalid` 占位，不会启动或暴露 3000 端口。成功后分别生成 `pinjie-mall-full-validation-v1` 或 `pinjie-mall-smoke-validation-v1` 证据；smoke 不能代替 strict 模式所需的 full 证据。

## 5. 源码交接与 CNB

`Handoff Source to CNB` 要求完整 40 位 Commit SHA，并在 `strict` 与 `fast` 之间选择：

- `strict` 要求同一 SHA 的四项自动门禁和完整验证证据。
- `fast` 仍要求四项自动门禁，并记录未使用完整验证证据的原因。

交接使用受保护环境中的最小权限 Token，以非强制快进方式更新 CNB `main`。当前商城 CNB 仓库为 `pjwl/pinjie-mall`，密钥仓库为 `pjwl/pinjie-mall-secrets`。CNB 只构建并发布以下两张镜像：

| 应用 | Dockerfile | TCR 仓库 |
| --- | --- | --- |
| Backend | `apps/backend/Dockerfile` | `pinjie-mall-backend` |
| Admin | `apps/admin/Dockerfile` | `pinjie-mall-admin` |

CNB 对每个应用独立构建候选镜像、执行扫描、生成 SBOM、provenance 与 `pinjie-cnb-tcr-image-v1` 证据，然后发布固定 `sha-<Commit SHA>` 标签。首次运行、变更超过 300 个文件或影响范围存疑时，人工使用 CNB 的 Backend 与 Admin 全量构建入口。远端 CNB、TCR 仓库和 Secret 是否已经创建不由本仓库配置证明。

## 6. 生产部署

`Deploy Production` 需要完整 Commit SHA、Backend digest 和 Admin digest，并受 `production` Environment 保护。工作流会验证 SHA 属于默认分支、输入 digest 格式、Compose 哈希和镜像引用；部署前仍需确认生产变量与实际 TCR 资源可用。

生产编排只接受根 `.env` 中的 `BACKEND_IMAGE` 与 `ADMIN_IMAGE`，且都必须是完整 `@sha256:` 引用。`compose.prod.yml` 只启动 Backend、可选 request-log-consumer 和 Admin；不包含 Web 服务或 3000 端口。

工作流启动、CNB 构建成功或镜像推送成功都不等于生产部署成功。部署后需要核对实际运行 digest、Backend 健康端点、Admin `/healthz` 与观察窗口内的错误和延迟。

## 7. 故障定位

- Governance 失败：根据具体脚本输出处理文档、工作区、依赖或 Compose 配置漂移。
- Backend 失败：处理静态、导入、应用导入或契约问题；不要用跳过检查或手工修改 `openapi.json` 绕过。
- Frontend 失败：先区分 Admin lint/typecheck 与冻结 Web 静态检查。Web 运行时失败属于预期阻断。
- Handoff 失败：检查 Commit SHA、自动门禁、full 证据、CNB 仓库地址及受保护环境权限。
- CNB 或部署失败：核对商城专属 TCR 命名空间、固定 digest、Secret 和生产变量；不得回退到母版仓库、镜像或凭据。
