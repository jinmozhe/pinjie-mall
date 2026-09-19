# 容器构建与运行手册

## 1. 范围

生产只构建和运行 Backend 与 Admin。`apps/web` 永久冻结，禁止构建 Web 镜像、运行 Web 容器或暴露 Web 端口。

## 2. 本地构建

从仓库根目录执行以下命令。构建属于用户明确授权的重型验证，不作为日常门禁。

```powershell
docker build -f apps/backend/Dockerfile -t pinjie-mall-backend:local .
docker build -f apps/admin/Dockerfile -t pinjie-mall-admin:local .
```

检查镜像架构和运行用户：

```powershell
docker image inspect pinjie-mall-backend:local --format '{{.Architecture}} {{.Config.User}}'
docker image inspect pinjie-mall-admin:local --format '{{.Architecture}} {{.Config.User}}'
```

## 3. CNB 与 TCR

`.cnb.yml` 只定义 `backend-image` 和 `admin-image`。两条 Pipeline 使用商城独立资源：

```text
CNB 仓库：pjwl/pinjie-mall
密钥文件：https://cnb.cool/pjwl/pinjie-mall-secrets/-/blob/main/tcr-publish.yml
TCR 命名空间：pinjie-mall
镜像：pinjie-mall-backend、pinjie-mall-admin
```

密钥文件由商城维护者在 CNB 创建，不进入 Git。它必须只允许 `pjwl/pinjie-mall` 的 `main` Push 和受控全量构建事件，包含 TCR Registry、命名空间、发布用户名及密码。缺失、来源不匹配或 digest 不可验证时，发布必须失败。

每个镜像发布流程依次构建候选标签、扫描、生成 SBOM 与 provenance、核对 digest，然后发布 `sha-<完整 Commit SHA>` 标签及单镜像证据。候选标签和构建缓存不能用于部署。

## 4. 生产 Compose

生产目录需要 `compose.prod.yml`、根 `.env` 和 `apps/backend/.env`。根 `.env` 只包含两张完整镜像 digest。执行前运行：

```powershell
docker compose --env-file .env -f compose.prod.yml config --quiet
docker compose --env-file .env -f compose.prod.yml pull
docker compose --env-file .env -f compose.prod.yml up -d --wait
docker compose --env-file .env -f compose.prod.yml ps
```

Backend 仅绑定 `127.0.0.1:18168`，Admin 仅绑定 `127.0.0.1:3001`，由 1Panel OpenResty 处理公网入口。PostgreSQL 和 Redis 使用外部 `1panel-network`；Backend 和请求日志消费者可以接入该网络，Admin 不得直接接入。

生产迁移、权限同步、镜像发布、部署和回滚均需单独授权。部署后核对 Backend 健康端点、Admin `/healthz`、运行镜像完整 digest 和 OpenResty 路由。
