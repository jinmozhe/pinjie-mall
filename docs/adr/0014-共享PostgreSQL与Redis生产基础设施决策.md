# ADR 0014：共享 PostgreSQL 与 Redis 生产基础设施决策

- 状态：已确认
- 日期：2026-09-02
- 决策者：大仙
- 操作手册：[1Panel 单机生产运行手册](../operations/1panel-production-runbook.md)

## 背景

单台 1Panel 服务器运行多个网站时，每个项目分别创建 PostgreSQL 和 Redis 容器会重复维护版本、数据目录、备份、容量和升级窗口。服务器已经由 1Panel 托管 PostgreSQL 18.4 与 Redis 8.10.0，并通过外部网络 `1panel-network` 提供容器内访问。

共享实例会扩大基础设施故障影响范围，因此实例共享必须与项目级身份、数据、Key、备份和容量隔离同时落地。

## 决策

1. 生产服务器共享一套由 1Panel 管理的 PostgreSQL 实例和一套 Redis 实例。
2. 每个项目使用独立 PostgreSQL 数据库、独立登录角色和独立强密码。应用禁止使用实例管理员或其他项目角色。
3. 每个项目使用独立 Redis ACL 用户、独立密码和仅允许自身项目与环境前缀的 Key Pattern。Redis DB 编号只用于辅助分类，不作为安全隔离。
4. Redis 项目用户禁止执行 `FLUSHALL`、`FLUSHDB`、`SWAPDB`、`CONFIG`、`ACL`、`SHUTDOWN`、`DEBUG`、`MODULE`、`KEYS`、`SCAN` 和 `RANDOMKEY` 等管理、全局或越界命令。
5. Backend 和可选请求日志消费者同时加入项目默认网络与外部 `1panel-network`。Web 和 Admin 只加入项目默认网络，不能直接访问 PostgreSQL 或 Redis。
6. 根 `compose.prod.yml` 不创建 PostgreSQL、Redis 或其数据卷。数据库与 Redis 的版本、持久化、容量、健康和备份由 1Panel 基础设施层管理。
7. Backend 通过 `DATABASE_URL` 和 `REDIS_URL` 连接共享服务。依赖不可用时由 Readiness 明确失败，禁止回退到本地容器或禁用安全关键 Redis。
8. 根 `.env` 只保存三张不可变应用镜像引用和 Web 公开 Origin。数据库、Redis 和认证秘密保存在 `apps/backend/.env`。
9. 共享 PostgreSQL 的备份与恢复以单个项目数据库为最小操作范围，同时保留实例级灾难恢复能力。恢复演练必须使用隔离目标，禁止覆盖其他项目数据库。
10. 旧项目专属 PostgreSQL、Redis 容器和数据在切换观察期内保留。删除容器、卷、备份或旧数据库需要独立授权。
11. 当前部署等级继续是单机可恢复模式。共享实例不提供高可用、跨故障域容灾或资源硬隔离。

## 网络与身份边界

```text
项目默认网络
├── Backend
├── Web
└── Admin

1panel-network
├── Backend
├── request-log-consumer（启用时）
├── PostgreSQL：postgresql:5432
└── Redis：redis:6379
```

PostgreSQL 数据库所有权、角色连接数和授权按项目配置。Redis ACL 的 Key Pattern 必须与 Backend 真实 `PROJECT_NAME` 和 `ENVIRONMENT` 生成的命名空间一致。任何凭据都不得进入 Compose、镜像、仓库、日志或发布证据。

## 备选方案

### 每个项目独立运行 PostgreSQL 与 Redis

隔离更强，代价是单机上重复维护容器、存储、备份、升级和监控。资源节省不是本决策的主要收益，当前单机更重视统一运维。

### 多个项目共用数据库、Schema 或管理员账号

拒绝。权限边界、恢复范围和误操作影响无法保持项目隔离。

### 只通过 Redis DB 编号隔离

拒绝。DB 编号不提供 ACL 安全边界，全局命令仍可影响其他项目。

### 通过宿主机公网地址连接

拒绝。共享服务只通过用户自定义 Docker 网络提供，宿主机端口最多绑定环回地址，禁止暴露公网。

## 后果

- PostgreSQL 与 Redis 的版本、备份和升级窗口可以统一管理。
- 项目 Compose 只负责应用容器，部署和回滚不会隐式重建共享数据服务。
- 共享实例故障、内存耗尽或错误升级会同时影响多个项目，需要实例级监控、容量告警和恢复演练。
- 项目迁移需要一次性备份、恢复、ACL 配置、连接串切换和观察窗口。
- 单个项目的旧基础设施清理不能使用日常部署命令自动完成。
