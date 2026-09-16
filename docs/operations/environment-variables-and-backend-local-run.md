# 环境变量与 Backend 本地运行手册

## 1. 适用范围

本文适用于 `pinjie-mall` 的 Backend 与 Admin。本项目没有可运行的 Web 端，禁止创建或启动 Web 服务，禁止监听 3000 或其他 Web 端口。

## 2. 配置分层

| 层级 | 模板 | 真实文件 | 使用者 | 职责 |
| --- | --- | --- | --- | --- |
| 部署层 | 根 `.env.example` | 根 `.env` | `compose.prod.yml` | 选择 Backend、Admin 的不可变镜像 |
| Backend | `apps/backend/.env.example` | `apps/backend/.env` | FastAPI 与运维脚本 | 数据库、Redis、认证、安全和文件存储 |
| Admin | `apps/admin/.env.example` | `apps/admin/.env.local` | Umi Max | 本地代理配置 |

真实 `.env`、`.env.local`、Token、密码、证书、生产域名和镜像 digest 不得提交。根 `.env` 只包含 `BACKEND_IMAGE` 与 `ADMIN_IMAGE`，不会自动进入 Backend 容器。

## 3. Backend 本地配置

从模板创建 `apps/backend/.env` 后，至少设置本机 PostgreSQL、Redis 和四个相互不同的认证密钥。`WEB_ORIGINS` 保留为后续小程序网关或浏览器调试来源的显式白名单，不启动 Web 服务，也不填写 3000 端口。

```dotenv
PROJECT_NAME="Pinjie Mall Backend"
ENVIRONMENT=local
DATABASE_URL=postgresql+asyncpg://pinjie_mall:your_password@localhost:5432/pinjie_mall_dev
TEST_DATABASE_URL=postgresql+asyncpg://pinjie_mall_test:your_password@localhost:5432/pinjie_mall_test
REDIS_MODE=required
REDIS_URL=redis://localhost:6379/0
WEB_ORIGINS=["https://miniapp.example.com"]
ADMIN_ORIGINS=["http://localhost:3001"]
WEB_JWT_SECRET=<至少32字节且独立的密钥>
ADMIN_JWT_SECRET=<至少32字节且独立的密钥>
WEB_TOKEN_HMAC_KEY=<至少32字节且独立的密钥>
ADMIN_TOKEN_HMAC_KEY=<至少32字节且独立的密钥>
```

`WEB_*` 认证变量是既有消费者会话配置名称，不表示允许 Web 服务或 Web 端口。后续小程序认证适配需要单独计划，不在本手册范围内。

## 4. 启动顺序

在仓库根目录启动 Redis：

```powershell
docker compose -f compose.yml up -d redis
```

在 `apps/backend` 执行：

```powershell
uv sync --locked
uv run alembic upgrade head
uv run python -m scripts.sync_permissions --check
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

在仓库根目录启动 Admin：

```powershell
pnpm --filter @pinjie/admin dev
```

Admin 默认使用 3001。启动后检查 `http://127.0.0.1:8000/health/live` 与 `http://127.0.0.1:8000/health/ready`。实际数据库升级和权限写入会改变本地数据库，只在确认目标环境后执行。

## 5. 生产配置

生产根 `.env` 使用来自商城独立 CNB/TCR 发布清单的完整 digest：

```dotenv
BACKEND_IMAGE=ccr.ccs.tencentyun.com/pinjie-mall/pinjie-mall-backend@sha256:<64位十六进制摘要>
ADMIN_IMAGE=ccr.ccs.tencentyun.com/pinjie-mall/pinjie-mall-admin@sha256:<64位十六进制摘要>
```

`apps/backend/.env` 保存生产数据库、Redis、可信主机、Admin 来源和密钥。生产 Compose 通过 `env_file` 注入 Backend 配置，并固定 `LOG_FILE_ENABLED=false`。数据库和 Redis 由 1Panel 的共享基础设施提供，不在项目 Compose 中声明。
