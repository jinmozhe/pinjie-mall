# Backend 项目规则

## 作用范围与规则层级

- 本文件适用于 `apps/backend/**`，并继承仓库根 `AGENTS.md`。
- 本文件承担 Backend 宪法级约束、P0 禁令、读取路由和执行边界；具体实现方式以 [Backend 工程实施标准](../../docs/architecture/backend-engineering-standard.md) 为准。
- 本项目不另设 `constitution.md`。根和应用级 `AGENTS.md` 是长期规则正文，`docs/` 保存架构、工程和运维文档，`plans/` 保存单次实施及验证记录。
- 规则冲突按根 `AGENTS.md` 的优先级和权威入口处理。只有无法据此判断且会影响当前实现的冲突才暂停相关动作并提问；其余工作继续。范围内已授权的规则修正直接完成，只读评审仅报告。

## 任务读取路由

- 任何 Backend 任务先读取根 `AGENTS.md`、`PROJECT_INDEX.md` 和本文件。
- 详细技术设计、实施计划、代码实现和代码评审必须完整读取 [Backend 工程实施标准](../../docs/architecture/backend-engineering-standard.md)。同一任务首次进入上述阶段时完整读取一次；标准变化、任务跨越较长周期或上下文无法确认时重新读取。
- 涉及跨领域依赖、数据所有权、查询模型或共享包时读取 [模块与依赖边界](../../docs/architecture/module-boundaries.md)。
- 涉及 API 错误、异常、外部调用、重试或故障隔离时读取 [错误与失败模型](../../docs/architecture/error-model.md)。
- 涉及身份、权限、资源授权、会话或审计时读取 [认证、授权与审计边界](../../docs/architecture/authentication-authorization.md)。
- 涉及实施计划、实现、评审、测试或完成验收时读取 [测试与质量策略](../../docs/architecture/testing-strategy.md)。
- 涉及日志、Trace、健康探针、容量、可靠性或部署设计时读取 [可观测性与可靠性基线](../../docs/architecture/observability-reliability.md)。
- 涉及本地启动、部署、备份、恢复或事故操作时读取对应 `docs/operations/` 手册。仅讨论产品范围或高层原则时，按实际主题读取相关文档，不要求无差别读取全部 Backend 文档。

## 固定技术栈与目录

- 后端采用标准 CPython 3.14、FastAPI、Pydantic v2、Pydantic Settings、SQLAlchemy 2 async、asyncpg、Alembic、PostgreSQL、Redis、Loguru 和 uv。禁止使用 free-threaded `3.14t`；完整版本边界以 [Python 运行时基线决策](../../docs/adr/0009-Python运行时基线决策.md)为准。
- 当前依赖声明以 `apps/backend/pyproject.toml` 为准，精确安装版本以已生成的 `apps/backend/uv.lock` 为准。新增或改变运行依赖必须进入已确认计划，禁止把开发依赖当作生产运行能力。
- 新增实现遵守 `app/api`、`app/core`、`app/db`、`app/domains`、`app/services` 的规划边界；目录尚未落地时，按 `docs/architecture/project-structure.md` 和当前计划创建最小必要结构。
- `app/core` 和 `app/db` 不得反向依赖领域、应用编排或传输层。Python 包目录包含 `__init__.py`，禁止通过导入副作用启动数据库连接、后台任务或外部客户端。

## P0 强制边界

- Router 只处理 HTTP 协议、参数、依赖声明、权限入口和响应模型，禁止 SQL、Session 操作、事务、Repository 实例化、外部调用和业务编排。
- 最外层 Application Service 或跨领域用例拥有事务。Repository 只能查询、写入准备、`flush` 和必要的 `refresh`，禁止 `commit`、`rollback`、权限判断、业务决策和吞错。
- 领域禁止导入其他领域的 Repository、Model 和内部 Service；跨领域协作只经过公开 Application Service、Port、DTO、领域事件或 `app/services/` 中的明确用例。
- 领域只能写入自己拥有的数据表。普通写模型禁止绕过所有权跨领域 JOIN 后修改状态；报表、搜索、列表聚合和导出使用明确的只读 Query Service 或 Read Model。
- Model 表达数据库结构，Schema 表达边界契约。禁止直接把 ORM Model 作为公开请求或响应模型。
- 禁止捕获异常后返回 `None`、空集合、默认值、假成功或继续主流程；禁止弱默认密钥、默认管理员、静默切换依赖和把网络错误解释为业务结果。
- 禁止永久兼容、隐式兼容、自动猜测版本和无期限双读双写。临时兼容只允许遵守 ADR 0007 的受控迁移窗口，必须有负责人、删除日期、观测、回滚和删除测试。
- 外部写操作必须定义幂等、确认、补偿或结果未知状态。超时和连接中断不能证明失败，禁止无确认自动重发。
- 异步请求链禁止直接执行同步网络、文件、密码哈希和其他阻塞 I/O；确有同步依赖时显式隔离到线程池，并设置并发和超时上限。
- 配置通过统一 Settings 对象读取。生产缺少必需密钥、数据库、安全域名、代理信任或已启用关键能力的配置时拒绝启动，禁止使用模板值继续运行。
- 真实 `.env`、密钥、Token、Cookie、数据库密码、连接串、私钥、HAR、生产数据和未脱敏第三方载荷禁止入库、进入日志或测试 Fixture。

## 数据库、迁移与缓存

- 使用 `AsyncSession` 和 SQLAlchemy 2.x 查询风格。异步关联显式加载，避免隐式懒加载、`MissingGreenlet` 和 N+1。
- 表结构变化必须新增 Alembic revision；已进入共享环境的 revision 禁止改写。生产和应用启动禁止使用 `create_all()` 建表或修复结构。
- 自动生成迁移必须人工审查类型、默认值、约束、索引、注释、数据回填和锁表风险。不可逆迁移必须先验证备份、恢复和数据校验，并取得相应授权。
- 业务主键默认 UUID v7，统一通过 `app/core/identifiers.py` 在应用层调用标准库 `uuid.uuid7()` 并返回 `uuid.UUID`；Model 使用 `sqlalchemy.Uuid(as_uuid=True)` 和 `default=new_uuid7`。禁止引入 UUID v7 第三方运行依赖、由调用方绕过统一入口或依赖 PostgreSQL 18 `uuidv7()` 服务端默认值。时间字段使用带时区时间并统一存储 UTC；结构化扩展数据优先 PostgreSQL JSONB；金额使用 `Decimal` 和明确精度，禁止 Float。
- Redis 只承载缓存、限流、会话、锁、队列或短期状态，不得成为核心业务数据的唯一权威来源。Key 必须有项目、环境、领域、用途和版本命名空间，临时数据必须有 TTL。

## API、安全与可观测性

- Router 集中注册并声明准确 `response_model`、状态码和错误语义。成功响应使用公共 `ResponseModel[T]`；业务失败抛出公共 `AppException`，禁止领域自创不兼容响应结构。
- 微信支付及退款通知 `/payments/wechat/notify`、`/refunds/wechat/notify` 是第三方协议入口：验签且可靠接收后返回空体 204，失败按微信协议返回 4xx/5xx 与 `code=FAIL`，不套用业务响应模型；其他端点继续使用统一响应和既有认证。
- 每个新增 Admin 管理端点必须在 Router 显式声明准确 `PermissionCode`；管理员登录态、客户端 Access 或通用权限不能替代资源权限。新增权限先更新源码权限目录和检查，再通过受控 `scripts.sync_permissions --check/--apply` 流程同步目标环境，应用启动不得自动改权限表。
- Admin 批量写端点使用专用批量 API，每次接受 1 至 100 个唯一目标 ID，按固定顺序锁定并在单一事务中全有或全无完成。删除语义遵守实体既有软删除或硬删除生命周期；所有单条和批量管理端点保留管理员会话、准确权限、CSRF、资源状态校验和审计，不接入管理员密码二次确认。物理硬删除的标准警告仅由 Admin 负责明确操作者意图，不能替代服务端保护；禁止依赖前端循环单条接口提供批量语义。
- Pydantic 负责结构、类型和局部字段校验，Service 或 Domain 负责依赖当前状态及多实体语义的业务校验，两层不得用不一致规则重复判断。
- Middleware 承载请求上下文等横切能力，Dependency 解析身份和通用权限，Router 声明端点权限，Service 或 Policy 在事务内依据权威资源状态执行最终授权。没有匹配规则时默认拒绝。
- 外部 HTTP 调用使用由应用生命周期管理的共享异步客户端，设置连接、读取、写入、连接池等待和总时间预算；重试必须有限、分类并且不会放大副作用。
- 日志使用结构化白名单字段，并携带 `request_id`；关键跨组件流程同时携带 `trace_id` 和必要的脱敏业务标识。应用日志、审计日志、指标和 Trace 各自承担独立职责。
- Liveness 不访问易波动外部依赖；Readiness 只检查当前实例服务关键请求所需且已启用的依赖，并使用严格超时。失败返回 `503`，不得泄露内部配置或路径。

## 测试、契约与交付

- 测试分层、依赖策略和完成条件以 `docs/architecture/testing-strategy.md` 为准。单元测试禁止访问真实数据库和未声明外部网络，也禁止 Mock 被测对象自己的内部方法。
- Backend 的默认自动门禁为 `uv run ruff check .`、`uv run ruff format --check .`、`uv run mypy app`、`uv run lint-imports`、源码编译、应用导入和 OpenAPI 契约检查。日常开发、普通提交、`$git-sync`、Push 和 Pull Request 均遵守这一范围。
- 未经用户在当前任务中明确点名，禁止运行任何定向或全量 pytest、测试数据库迁移、测试 PostgreSQL/Redis 服务及其他依赖真实测试环境的自动验证。`$git-sync` 不提供隐式授权，GitHub Actions 的 Push、Pull Request 和定时触发也不得执行这些命令。
- 用户明确授权时只执行被点名的命令和范围，授权不延续到后续任务；测试失败必须如实报告。未获授权的项目记录为“按项目策略未执行”，不能表述为通过或待 GitSync 执行。
- PostgreSQL 集成测试使用名称以 `_test` 结尾的独立数据库，并在任何迁移、建表或清理前校验环境、主机、数据库名和应用数据库隔离。禁止用 SQLite 替代 PostgreSQL 语义测试。
- 修改 Model 或迁移时必须同步 Alembic 文件并人工复读；实际数据库升级、重复升级和漂移验证只在用户明确授权后执行。修改公开 Schema 或 Router 时按“Backend 实现、导出根 `openapi.json`、运行 `pnpm generate-api`、适配消费者”的顺序同步。
- Backend 准备通过 `$git-sync` 交付时只要求上述轻量门禁和受影响契约检查通过。pytest、Alembic 真实数据库验证和覆盖率门禁继续保留为显式授权后的专项能力，未执行时必须如实记录。
- AI 生成的迁移必须人工审查后才能执行到共享环境。生产迁移、数据修复、部署、回滚、密钥调整和破坏性操作分别需要明确授权。
- 每次交付列出实际通过、失败、跳过、未适用和未执行项；当前空骨架不得表述为应用质量、运行能力或高可用已经实现。
