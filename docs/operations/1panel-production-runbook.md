# 1Panel 单机生产运行手册

## 1. 适用范围

本手册适用于使用 1Panel、OpenResty 和 `compose.prod.yml` 运行 Pinjie Mall 的单机生产环境。操作人员从 GitHub Actions 开始执行完整发布时，先阅读[GitHub 到 1Panel 端到端人工发布手册](github-cnb-tcr-1panel-release-runbook.md)。本文继续负责 1Panel 基础设施、生产配置、迁移、OpenResty、备份和恢复细节。

生产部署、迁移、恢复、回滚、Tag 和 Release 分别需要明确授权。本项目在首次生产部署前必须补充域名、RPO、RTO、容量、告警和责任人。

## 2. 部署前提

- Linux x86_64 主机已安装并维护 Docker Engine、Compose v2 和 1Panel。
- 1Panel OpenResty 独占公网 80/443，应用端口只绑定 `127.0.0.1`。
- Backend 与 Admin 镜像已经过对应 Commit SHA 的质量门禁、SBOM 和安全扫描。
- 两张应用镜像使用完整 `@sha256:` digest，禁止使用 `latest`、分支标签或缺失版本回退。
- 按当前单维护者流程，人工核对 CNB 单镜像发布清单与 TCR digest，并确认服务器根 `.env` 和 1Panel 编排环境变量一致；不要求候选镜像验收工作流或自动预检清单。服务器保持纯拉镜像，不安装验证工具链，完整顺序见[端到端人工发布手册](github-cnb-tcr-1panel-release-runbook.md)。
- 生产服务器使用独立 `tcr-puller` CAM 子用户登录 TCR 个人版，只允许拉取本商城的 Backend 与 Admin 仓库；账号创建、只读 JSON、凭证初始化和权限验收见[腾讯云 CAM 子账号与 TCR 个人版最小权限操作手册](tencent-tcr-personal-cam-accounts.md)。
- 1Panel 已管理 PostgreSQL 18.4 与 Redis 8.10.0 共享实例，并把二者接入外部网络 `1panel-network`；宿主机端口只允许绑定环回地址。
- 共享 PostgreSQL 为每个项目配置独立数据库、登录角色和密码；共享 Redis 至少启用密码，并为各项目分配独立逻辑库编号。隔离要求更高时配置独立 ACL 用户或独立实例。
- 部署目录、真实 `.env`、备份和数据库凭据仅允许受控运维账号访问。

生产目录至少包含：

```text
<DEPLOY_PATH>/
├── compose.prod.yml
├── .env
└── apps/
    └── backend/
        └── .env
```

环境变量职责和最低配置见[环境变量分层与 Backend 本地运行手册](environment-variables-and-backend-local-run.md)。真实秘密不得写入仓库、命令日志、工单或聊天记录。

### 登录与发布结果的独立核验

本机 Docker 或 CNB 的登录成功不会为生产服务器提供凭据。1Panel 的 Registry 配置与服务器命令行实际使用的 Docker 配置分别确认，不能假定 SSH 用户、root 和面板自动共享登录态。先用目标只读身份按完整 digest 拉取，再验证编排、实际运行 digest、健康端点和业务访问；镜像存在、拉取成功、部署健康是不同检查点。先前有效凭据可以继续使用，无需每次发布退出重登；鉴权错误按[TCR 账号手册](tencent-tcr-personal-cam-accounts.md#12-常见问题和处理顺序)分流。

## 3. 配置检查

在发布候选代码上先运行：

```powershell
pnpm check:production-config
pnpm check:governance
```

在生产部署目录检查 Compose 展开结果：

```bash
docker compose --env-file .env -f compose.prod.yml config --quiet
```

通过 1Panel Web 编辑器维护系统创建的编排时，把根 `.env` 中的 `BACKEND_IMAGE` 与 `ADMIN_IMAGE` 同步到编排的“环境变量”页。应用镜像字段使用基础插值 `${BACKEND_IMAGE}` 与 `${ADMIN_IMAGE}`，避免 1Panel 镜像预拉取把带 `:?` 提示的 Compose 必填表达式误判为镜像名称。镜像变量缺失或不是完整 `@sha256:` 引用时必须停止更新，不得改用 `latest`、分支标签或其他可变引用。命令行部署继续显式传入 `--env-file .env`。

1Panel 显示更新失败但容器已经创建时，先以 `docker compose ps`、各应用健康端点、脱敏后的容器环境目标和实际镜像 digest 判断运行状态。禁止只根据面板任务状态宣称部署成功，也不得在未核对存储卷前删除整个编排。

检查项：

- `BACKEND_IMAGE` 与 `ADMIN_IMAGE` 均为批准的完整 digest。
- Backend `backend_uploads` 命名卷挂载到 `/app/storage`，统一资产根为 `/app/storage/uploads`，配置媒体根为 `/app/storage/settings-media`。
- Backend 和 request-log-consumer 显式设置 `LOG_FILE_ENABLED=false`。
- Backend 和 request-log-consumer 同时接入项目默认网络与外部 `1panel-network`；Admin 不接入基础设施网络。
- `DATABASE_URL` 使用共享服务名 `postgresql`、项目数据库和项目角色。当前 `REDIS_URL` 使用共享服务名 `redis`、`default` 用户和独立逻辑库 `/1`；逻辑库编号不能当作权限隔离。
- `ENVIRONMENT=production`，Cookie、Trusted Host、CORS、代理 CIDR 和四个认证密钥满足生产约束。

CNB 每个应用会生成独立的 `pinjie-cnb-tcr-image-v1` 附件。部署单端更新时，只把根 `.env` 中该端镜像变量替换为附件中的完整 digest，保留另一端的现有 digest。1Panel 点击“更新编排”可能重算全部服务配置；需要严格只重建目标端时，在同一 Compose 目录执行 `docker compose --env-file .env -f compose.prod.yml up -d --no-deps --wait <backend|admin>`。更新后记录两个运行端各自的 Commit、digest、CNB Build ID、证据附件和部署时间。

项目 Compose 不创建、停止或重建 PostgreSQL 和 Redis。共享实例的镜像版本、数据目录、持久化、容量、健康检查和备份由 1Panel 基础设施层管理；项目日常部署禁止使用 `--remove-orphans` 清理旧基础设施容器。

## 4. 备份与迁移

发布前记录当前完整 Commit SHA、三张运行镜像 digest、Alembic revision 和备份标识。目标 PostgreSQL 数据库必须由项目角色拥有，该角色禁止拥有超级用户、创建数据库和创建角色权限，并设置与实例容量相符的连接上限。当前 Redis `default` 用户加逻辑库 `/1` 只提供 Key 命名空间隔离，应用本身不会根据 `PROJECT_NAME` 或 `ENVIRONMENT` 自动增加统一 Key 前缀。多个可信项目共用该模式时必须登记唯一库编号并禁止 `FLUSHALL` 等全局操作；需要命令和 Key 权限隔离时使用独立 ACL 用户或独立 Redis 实例。

从项目专属 PostgreSQL 与 Redis 迁移到共享实例时，按以下顺序操作：

1. 核对源、目标数据库身份，确认目标为空或已取得覆盖恢复专项授权。
2. 分别验证共享实例备份和源项目数据库一致性备份，记录文件大小与 SHA-256。
3. 创建项目 PostgreSQL 角色，将目标数据库所有权和恢复对象归属设置为该角色。
4. 为目标项目登记独立 Redis 逻辑库编号并验证密码连接；采用 ACL 方案时还要持久化独立用户，并验证项目 Key 可访问且管理命令被拒绝。
5. 停止 Backend、Admin 和请求日志消费者，冻结写入后制作最终数据库备份。
6. 恢复到共享 PostgreSQL，核对 Alembic revision、表清单、权限目录、管理员和不泄露数据的业务摘要。
7. 更新 `apps/backend/.env` 中的两个连接串，启动应用并执行完整健康与登录检查。
8. 在观察期内保留旧 PostgreSQL、Redis 容器和数据。删除旧容器、卷、备份或数据库需要独立授权。

数据库结构变化时，先完成可恢复备份，再执行一次性迁移：

```bash
docker compose --env-file .env -f compose.prod.yml pull
docker compose --env-file .env -f compose.prod.yml run --rm backend alembic upgrade head
docker compose --env-file .env -f compose.prod.yml run --rm backend python -m scripts.sync_permissions --apply --confirm-database <生产数据库名>
docker compose --env-file .env -f compose.prod.yml run --rm backend python -m scripts.sync_permissions --check --confirm-database <生产数据库名>
```

应用启动不自动执行 Alembic。迁移失败时停止发布，保全原数据库和备份，不继续启动不兼容的新应用镜像。

用户回收站记录长期保留，不配置到期时间，也不运行匿名化脚本。具备 `users:restore` 权限的管理员可以随时恢复，恢复后账户仍保持停用。

## 5. 启动与健康检查

```bash
docker compose --env-file .env -f compose.prod.yml up -d --wait
docker compose --env-file .env -f compose.prod.yml ps
```

仅在 `REQUEST_LOG_MODE=metadata` 时启动请求日志消费者：

```bash
docker compose --env-file .env -f compose.prod.yml --profile request-logs up -d --wait
```

逐项确认：

- 1Panel 中的共享 PostgreSQL 和 Redis 状态正常，使用项目凭据执行的连接检查成功。
- Backend `/health/live` 返回存活，`/health/ready` 返回就绪。
- Admin `/healthz` 返回 `ok`。
- 运行容器使用批准的完整镜像 digest，进程用户为非 Root。
- Admin 经同域 `/api/v1` 访问 Backend，认证 Cookie 包含 `HttpOnly`、`Secure` 和预期的 `SameSite`。
- 权限目录无漂移；启用请求日志时消费者能处理 Redis Stream 并写入 PostgreSQL。

## 6. OpenResty 接线

在 1Panel 中为批准域名启用 TLS，并分别代理到：

| 入口 | 上游 |
| --- | --- |
| Admin | `http://127.0.0.1:3001` |
| 独立 Backend 域名需要时 | `http://127.0.0.1:8000` |

转发时保留 `Host`、`X-Real-IP`、`X-Forwarded-For` 和 `X-Forwarded-Proto`。Backend 只信任 `TRUSTED_PROXY_CIDRS` 中明确登记的代理地址，禁止用全网段或通配值绕过来源校验。

## 7. 日志与观测

生产 Compose 默认关闭 Backend 文件日志，Backend 和请求日志消费者只写标准错误流，由 Docker 与 1Panel 收集。这样可以保持应用容器只读并避免未挂载的 `/app/logs` 写入失败。

确需文件日志时，必须同时完成：

1. 为 Backend 和请求日志消费者设置明确、独立且可写的持久挂载。
2. 把 `LOG_FILE_PATH` 指向挂载目录并显式设置 `LOG_FILE_ENABLED=true`。
3. 验证非 Root UID 具有最小写权限。
4. 配置轮转、保留、容量告警和清理责任人。

应用日志、审计日志和请求元数据承担不同职责。任何日志都不得记录 Cookie、Token、密码、完整连接串或未脱敏请求体。

## 8. 备份、恢复与回滚

1Panel 可以调度共享 PostgreSQL 备份和异地复制，但面板成功状态不能代替隔离恢复演练。备份、恢复和演练必须明确目标项目数据库，禁止影响同一实例中的其他项目。详细校验见[数据库备份与恢复手册](database-backup-restore.md)。

统一文件资产或系统配置媒体启用后，必须备份完整 `backend_uploads` 命名卷。数据库与文件卷使用同一备份窗口并共同记录标识；恢复时先停止写入，恢复 PostgreSQL 与文件卷，再抽样核对 `assets.file_key`，并校验 `system_settings.site.logo` 的路径、大小、MIME 和哈希。只恢复数据库或只恢复文件卷会产生悬空元数据或孤儿文件，不能视为完整恢复。

应用回滚只能选择已经批准的旧镜像 digest，并先确认旧应用与当前数据库 revision 兼容。数据库回滚或覆盖恢复必须停止或隔离写入、保全当前数据库、确认恢复点与数据损失窗口，并取得专项授权。

回滚后重新执行健康检查、关键认证流程、权限检查和只读数据摘要校验。记录实际 Commit SHA、镜像 digest、数据库 revision、恢复点、RTO、RPO 和异常。

## 9. 停止边界

生产环境禁止把 `docker compose down -v` 作为日常停止命令。项目 Compose 不拥有共享 PostgreSQL 和 Redis，禁止从项目目录对其执行停止、删除、重建或清理。卷删除、数据库清理和备份删除都属于独立破坏性操作。仅停止应用时应先确认影响窗口，再使用明确服务名执行受控停止；恢复服务后重新运行健康检查。
