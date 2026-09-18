# Backend 工程实施标准

## 1. 作用范围与使用方式

本文规定 `apps/backend` 在详细技术设计、实施、代码评审和验证阶段的具体工程标准，适用于 FastAPI、Pydantic、SQLAlchemy、Alembic、PostgreSQL、Redis、日志、外部调用和测试基础设施。

阶段 B 已提供运行与测试基础设施，阶段 C 已提供认证、用户、管理员、RBAC、安全事件、审计和请求元数据能力。本文描述当前已落地的工程标准；当前验证事实和命令记录在对应阶段计划。

本文使用以下规范词：

- “必须”和“禁止”表示违反即阻断实施或交付。
- “应当”表示默认做法，偏离时必须在计划中说明依据和验证。
- “可以”表示满足前置条件后的允许选项，不表示默认启用。

## 2. 权威来源与职责

| 主题 | 唯一架构契约 | 本文职责 |
| --- | --- | --- |
| 全栈模块依赖、领域所有权和共享包 | [模块与依赖边界](module-boundaries.md) | 说明 Backend 分层和技术落地方式 |
| 错误语义、HTTP 映射、结果未知和故障隔离 | [错误与失败模型](error-model.md) | 说明 FastAPI 异常、响应和外部调用实现方式 |
| 认证、端点权限、资源授权和审计 | [认证、授权与审计边界](authentication-authorization.md) | 说明 Dependency、Policy、事务内授权和审计落地方式 |
| 测试层级、依赖策略和完成条件 | [测试与质量策略](testing-strategy.md) | 说明 Backend Fixture、数据库隔离和命令门禁 |
| 部署等级、探针、信号、容量和恢复 | [可观测性与可靠性基线](observability-reliability.md) | 说明 Backend 生命周期、日志、探针和资源上限 |

发生冲突时，先遵守根和 Backend `AGENTS.md`，再以本表中的专题文档确定架构语义，本文只解释 Backend 如何落实。完整规则正文只维护一份，其他位置保留可独立执行的摘要和链接。

重大技术选型及其取舍进入 `docs/adr/`，本地启动、部署、备份、恢复和事故步骤进入 `docs/operations/`，单次范围与验证进入原 `plans/*.md`。

## 3. 技术基线与依赖

当前已声明的 Backend 技术基线：

- 标准 CPython 3.14、FastAPI、Pydantic v2 和 Pydantic Settings；禁止使用 free-threaded `3.14t`，版本和运行环境边界以 [Python 运行时基线决策](../adr/0009-Python运行时基线决策.md)为准。
- PostgreSQL、SQLAlchemy 2 async、asyncpg 和 Alembic。
- Redis、Loguru 和 uv；认证使用 PyJWT，密码哈希使用 pwdlib 的 Argon2id 实现。
- UUID v7 已确认由应用层统一生成；Python 3.14 使用标准库 `uuid.uuid7()`，阶段 B 不引入 `uuid-utils` 或其他 UUID v7 第三方运行依赖。
- Ruff、Mypy、pytest、pytest-asyncio 和 httpx 当前作为开发依赖。

依赖管理要求：

1. 直接依赖写入 `apps/backend/pyproject.toml`，精确解析结果写入 `apps/backend/uv.lock`。
2. 使用 `uv add <package>` 或 `uv add --dev <package>`，禁止手工制造与锁文件不一致的安装状态。
3. 生产代码导入的包必须是运行依赖。当前 `httpx` 只在开发依赖中，未来生产外部 HTTP 能力必须先通过计划将其加入运行依赖：执行 `uv add httpx`（不带 `--dev`）使其出现在 `[project].dependencies`，重新生成 `uv.lock`，并同步更新 Backend Dockerfile 的依赖安装层和相关测试。真实生产外部调用成立后再做此升级；当前 `httpx` 保留开发依赖以支持 pytest `httpx.AsyncClient` 测试入口。
4. import-linter 已纳入 Backend 开发依赖和门禁。引入 Psycopg 3 或其他尚未声明的工具时必须经过计划、锁定依赖并补充相应验证。
5. 外部参考项目只作为设计证据，禁止绝对路径导入、符号链接、Git 子模块或运行时读取参考项目文件。

## 4. 配置与启动失败

### 4.1 配置入口

1. 配置集中在规划的 `app/core/config.py`，由 Pydantic Settings 生成单一、经过校验的 Settings 对象。
2. Router、Service、Repository 和 Domain 禁止散落调用 `os.getenv()` 或自行解析 `.env`。
3. 配置字段使用明确类型、约束和安全默认值。密钥、数据库密码和生产地址不得提供可继续运行的弱默认值。
4. 模块导入阶段禁止连接数据库、Redis、外部 HTTP、启动 Worker 或执行迁移；资源初始化和关闭进入 FastAPI lifespan。
5. 环境名称的允许值、大小写和语义必须在阶段 B 与 `apps/backend/.env.example` 一次性统一，禁止通过别名和自动归一化兼容多个拼写。

### 4.2 环境变量边界

环境变量分层和 1Panel 注入方式以[环境变量分层与 Backend 本地运行手册](../operations/environment-variables-and-backend-local-run.md)为准：

- 根 `.env` 只选择三个容器的不可变镜像引用。
- `apps/backend/.env` 只保存 Backend 运行配置和秘密。
- 根 `.env` 中的值不会自动进入 Backend 容器。
- `.env.example` 只保存公开模板值，真实 `.env` 禁止入库、记录到日志或复制到文档。

### 4.3 Fail Fast

1. 生产启动必须校验环境标识、密钥强度、数据库、允许域名、CORS、可信代理、安全 Cookie、HTTPS/TLS 边界及已启用关键能力所需配置。
2. 缺少必需配置、仍使用模板值、值之间矛盾或安全边界无法确认时，以非零状态拒绝启动。
3. 配置错误不能通过关闭校验、使用开发值或切换到内存实现继续运行。
4. 短时外部依赖故障由 Startup 与 Readiness 契约决定是否退出或保持未就绪，不能伪造就绪。配置无效始终拒绝启动。

## 5. 应用入口、Router 与依赖注入

实现必须遵守[模块与依赖边界](module-boundaries.md)和[认证、授权与审计边界](authentication-authorization.md)。

### 5.1 应用入口

1. `app/main.py` 提供稳定的 FastAPI 应用导入入口；应用创建、异常处理器、中间件、Router 和 lifespan 的注册集中且可测试。
2. `app/api_router.py` 统一注册领域 Router 的 `prefix`、`tags` 和版本路径。领域 `router.py` 只声明 `APIRouter` 和端点。
3. 导入 `app.main` 不得产生数据库连接、网络请求、文件写入、迁移或后台任务副作用。
4. 中间件、异常处理器和 Router 的注册顺序必须有测试固定，避免重复注册和依赖导入顺序的行为。

### 5.2 Router

Router 只允许：

- 接收路径、查询、Header、Cookie 和 Body 参数。
- 声明认证、权限和其他 FastAPI Dependency。
- 调用一个明确的 Application Service 或用例入口。
- 设置协议要求的状态码、Header 和 Cookie。
- 返回与 `response_model` 一致的 Schema。

Router 禁止：

- SQL、`session.execute()`、`commit()`、`rollback()` 和 Repository 实例化。
- 跨多个 Repository 或外部系统编排业务流程。
- 捕获业务异常后返回 HTTP 200、空数据或自定义失败字典。
- 根据数据库状态完成资源级最终授权。
- 返回 ORM Model 或依赖序列化阶段隐式加载关系。

Service、Domain 和 Repository 禁止依赖 FastAPI `Request`、`Response`、`Depends` 和 `HTTPException`。需要的身份、请求标识和协议数据通过明确 DTO 或调用参数传入。

### 5.3 依赖注入

1. 请求级 Session、当前身份和 Application Service 通过集中 Dependency 创建，生命周期由框架上下文管理。
2. 领域内部依赖装配可以放入该领域的 `dependencies.py`；跨领域用例装配放入应用服务依赖模块，禁止把 `app/api/deps.py` 变成包含业务规则的杂物文件。
3. Router 声明身份和通用权限，Service 或 Policy 在事务内读取权威资源状态并完成最终授权。
4. 测试通过 FastAPI dependency overrides 或明确 Port 替身替换外部依赖，禁止修改被测对象内部方法来制造通过。

## 6. Schema、响应与 OpenAPI

错误语义和 HTTP 状态码以[错误与失败模型](error-model.md)为准。

### 6.1 Schema

1. 请求、响应、内部命令 DTO 和 ORM Model 分离，禁止为了减少文件而复用 ORM Model 作为公开契约。
2. 输入字段使用 `Field` 声明长度、范围、格式和业务含义。局部字段规则由 Pydantic 校验，依赖当前状态或多实体数据的规则由 Service 或 Domain 校验。
3. ORM 输出 Schema 使用 Pydantic v2 `ConfigDict(from_attributes=True)`，但序列化前必须显式加载所需关系。
4. 敏感字段采用专用输出 Schema 或明确脱敏转换，禁止依赖“调用方不会读取”保护密码哈希、Token、密钥和内部状态。
5. 手动导出 Pydantic 数据时使用 `.model_dump(mode="json")`；普通端点优先由 FastAPI 按声明的响应模型完成序列化。

### 6.2 响应和分页

1. 普通 JSON 成功响应统一使用 `ResponseModel[T]`，至少表达稳定业务码、消息、数据和 `request_id`。
2. 失败响应只由全局异常处理器构造，至少表达稳定错误码、安全消息、`request_id` 和允许公开的字段错误。
3. 列表分页统一表达 `items`、`total`、`page` 和 `page_size`；`page` 从 1 开始，`page_size` 设置显式上下限。
4. 文件下载、流式响应、重定向、健康探针和第三方协议回调可以偏离公共包装，但必须在计划和 OpenAPI 中明确原因，并增加专用测试。
5. API 不返回无法区分“空结果”“无权限”“失败”和“不适用”的模糊数据。

### 6.3 OpenAPI

1. 端点声明准确的返回类型或 `response_model`、状态码、`summary`、`description`、`tags` 和已知错误语义。
2. 根 `openapi.json` 只从可导入应用导出，禁止手工修改；`packages/api-client/src/` 只由根契约生成。
3. 删除字段、改变类型或空值、修改路径方法、认证要求、校验和错误契约均按 Breaking Change 评估。
4. 契约变化遵循“Backend 实现、导出根契约、生成 API Client、适配 Admin 与 Web、联合验证”的固定顺序。
5. 受控兼容必须符合 ADR 0007；没有登记的字段别名、双字段、双路由和自动格式猜测禁止进入实现。

## 7. Service、事务与外部副作用

### 7.1 Service 职责

1. 单领域 Application Service 承载用例、业务规则、资源授权和事务边界。
2. 跨领域用例放入 `app/services/`，命名为明确的 Use Case 或 Workflow；该目录禁止容纳无归属 helper。
3. Domain 维护纯业务不变量，不依赖 FastAPI、SQLAlchemy Adapter 和外部协议。
4. Service 不拼接 HTTP 响应，不抛 `HTTPException`，也不把数据库异常原样暴露给调用方。

### 7.2 事务所有权

1. 一个业务动作只有一个最外层事务所有者，即公开写 Application Service 或跨领域用例。
2. 同一 `AsyncSession` 的内部 Service 和 Repository 只执行操作及 `flush`，不得提交或回滚。事务上下文必须绑定实际 `AsyncSession` 身份；同一 Session 的未定义嵌套写事务明确失败，不同 Session 各自拥有独立提交与回滚边界。
3. 事务范围必须覆盖需要原子一致的业务写入、状态转换和审计意图。只读用例不为统一形式强行开启写事务。
4. 禁止通过隐式嵌套事务掩盖所有权。Savepoint 只用于已经定义局部回滚语义的场景，并具有针对性测试。
5. 提交失败后必须回滚并使用 `raise ... from exc` 或裸 `raise` 保留异常链，禁止记录后继续返回成功。

### 7.3 外部副作用

数据库回滚不能撤销文件、Redis、消息和第三方写操作。外部副作用必须选用并验证以下一种或多种机制：

- 幂等键和本地唯一约束。
- 事务内持久化操作意图或 Outbox，事务外执行副作用。
- 远端事实查询和结果确认。
- 明确补偿动作。
- 可恢复状态机和人工核验队列。

第三方写操作不得包在长期数据库事务中。推荐流程为：

```text
事务 A：校验权威状态，记录操作意图并提交
-> 无长期数据库事务地执行外部写入
-> 查询或接收外部确认
事务 B：保存结果摘要和最终状态并提交
```

超时或连接中断表示结果未知时，必须保存可查询状态，禁止直接重发并把结果记录为失败或成功。

## 8. Repository 与 SQLAlchemy Async

1. 每个请求或独立用例使用有界生命周期的 `AsyncSession`，禁止使用跨请求全局 Session。
2. Session 应当使用 `expire_on_commit=False`，避免提交后通过隐式 I/O 读取已过期属性。
3. Engine 使用 `pool_pre_ping`；池大小、溢出、等待超时和回收时间必须由配置控制并结合容器副本数计算连接预算。
4. 查询采用 SQLAlchemy 2.x `select()`、`insert()`、`update()` 和 `delete()` 风格。唯一结果使用 `scalar_one()`、`scalar_one_or_none()` 或同等明确语义。
5. 异步关联显式使用 `selectinload`、`joinedload` 或专用查询投影，禁止在响应序列化阶段触发懒加载。
6. 大列表必须分页；排序字段使用白名单映射，禁止将用户输入直接作为列名或 SQL 片段。
7. **列表排序规范**：项目主键采用 UUID v7（时间戳单调递增），`id` 字段本身已承载创建时间语义，列表查询禁止将 `created_at` 与 `id` 冗余组合排序，统一按以下规则执行：
   - **分页列表（倒序）**：使用 `order_by(Model.id.desc())`，等价于按创建时间倒序，直接利用主键索引，不得额外添加 `.created_at.desc()` 兜底；
   - **从属子列表（正序）**：如订单明细、SKU、购物车、地址，使用 `order_by(Model.id)`，不得额外添加 `.created_at`；
   - **含人工排序的列表**：如分类，使用 `order_by(Model.sort_order.asc().nulls_last(), Model.id.desc())`；
   - **业务时间字段**：按 `auto_confirm_at`、`expires_at`、`published_at` 等业务含义字段排序的查询，该字段语义不同于创建时间，可按实际需要排序，不受此规范约束；
   - **加锁防死锁查询**：`with_for_update()` 场景的排序用于固定锁顺序（如按 `user_id`、`sku_id` 排），不强制改为 `id` 排序；
   - 所有排序字段变更必须评估现有索引是否能覆盖，无法覆盖时必须新增相应索引。
8. 禁止使用 `text()`、字符串格式化或拼接把用户输入写入 SQL。确需原生 SQL 时使用绑定参数、限定在 Repository，并增加安全与数据库集成测试。
9. 高频过滤、排序、状态扫描、外键和唯一性必须结合真实查询评估索引；禁止无证据为所有字段建索引。
10. 并发写入根据业务不变量选择数据库唯一约束、原子条件更新、乐观版本或悲观锁。只在确有竞争证据时使用 `FOR UPDATE`，并规定锁顺序和超时。
11. Repository 返回领域需要的实体或 DTO，不返回 HTTP 响应，也不隐藏“无结果”和数据库故障之间的区别。

## 9. Model 与 PostgreSQL

1. 默认内部主键使用 UUID v7。所有调用方必须经过 `app/core/identifiers.py` 的 `new_uuid7()`；该入口调用标准库 `uuid.uuid7()` 并返回 `uuid.UUID`。禁止在不同领域分散调用标准库生成函数或引入第三方 UUID v7 包。
2. UUID 列使用 `sqlalchemy.Uuid(as_uuid=True)` 和 PostgreSQL 原生 `uuid` 类型，主键使用 Python 侧 `default=new_uuid7`；禁止依赖 PostgreSQL 18 `uuidv7()` 服务端默认值。实现必须验证类型、唯一性、排序、序列化和真实数据库往返。
3. 时间使用带时区类型，对应 PostgreSQL `TIMESTAMPTZ`；程序和数据库统一保存 UTC，展示层负责时区转换。
4. 结构化数据使用 PostgreSQL JSONB。字段语义确定为对象或数组时增加相应检查约束，只在真实查询需要时增加 GIN 或表达式索引。
5. 金额、比率和其他精确数值使用 `Decimal` 与按领域确认的 `Numeric(precision, scale)`，禁止 Float。单位和舍入规则属于公开业务契约。
6. 有限状态使用命名稳定的 `CheckConstraint` 或经过迁移评审的 PostgreSQL Enum，选择时优先考虑变更成本和数据完整性。
7. 唯一性、外键、非空、检查约束和级联行为必须由业务不变量驱动并显式声明。数据库外键不授予跨领域写权限。
8. 新表和关键字段提供准确中文 comment；命名使用 snake_case，并为约束和索引使用稳定、可诊断的名称。
9. 软删除、归档和物理删除表达不同语义，按领域明确选择。所有相关查询必须明确是否包含已删除或已归档数据。
10. 禁止未经设计的级联物理删除核心可追溯数据；高风险记录优先状态化保留并受保留期与隐私要求约束。
11. 新增 Model 必须进入 Alembic metadata 的明确导入链，并验证 Schema、ORM、数据库类型和 OpenAPI 语义一致。
12. **人工排序字段（sort_order）规范**：需要人工控制显示顺序的实体才允许定义 `sort_order` 字段，统一遵守以下规则：
    - 列类型使用 `Integer`，**必须**设置 `nullable=True, default=None`；禁止 `NOT NULL DEFAULT 0`。
    - Python 类型标注使用 `Mapped[int | None]`，Pydantic Schema 使用 `int | None = Field(default=None, ge=0)`，不支持负值。
    - 字段语义：`NULL` 表示未人工设置，自动排最后；正整数越小越靠前（相同值时以 `id.desc()` 兜底）。
    - 查询排序固定使用 `Model.sort_order.asc().nulls_last(), Model.id.desc()`，禁止将 0 作为"未设置"标记。
    - 字段 comment 使用"排序权重，值越小越靠前，NULL 表示未人工设置自动排最后"。
    - 新增时必须同步新增 Alembic 迁移，明确去掉 `NOT NULL` 约束和 DEFAULT 值，并提供 downgrade 回滚路径（将 NULL 回填为 0）。

## 10. Alembic 与数据库演进

数据库迁移授权、备份和恢复步骤以[数据库备份与恢复手册](../operations/database-backup-restore.md)为准。

1. 生产和应用启动禁止使用 `Base.metadata.create_all()` 创建、修补或重建 Schema。
2. Model 变化必须新增 Alembic revision，空 revision 不提交，已部署或已进入共享环境的 revision 永远不得改写。
3. 自动生成 revision 后人工审查类型、服务端默认值、约束、索引、注释、数据回填、锁表时间和降级语义。
4. 危险类型转换、非空字段增加和大表索引采用分步迁移，必要时使用显式 PostgreSQL `USING`、并发索引或维护窗口；方案必须按实际版本验证。
5. 数据迁移验证行数、约束和关键摘要，不能只检查退出码。
6. 每项迁移按适用范围验证空库升级、已有库增量升级、重复升级、当前 Model 一致性和 `alembic check`。
7. 会丢数据或无法可靠逆转时禁止提供虚假的 `downgrade()`；计划必须明确使用前一镜像、前向修复或数据库恢复的条件。
8. 应用启动可以检查数据库 revision 是否满足服务条件，但禁止启动时静默执行迁移。部署通过受控步骤运行 `alembic upgrade head`。
9. 自动生成或 AI 生成的迁移必须经人工审查后才能执行到共享开发、预发布或生产环境。

## 11. Redis 与短期状态

1. Redis 只保存缓存、验证码、限流、会话、锁、幂等记录、队列或其他短期状态，不能成为核心业务数据的唯一权威来源。
2. Key 由规划的公共 Key 工厂统一生成，结构至少包含项目、环境、领域、用途、版本和资源标识，例如 `<project>:<environment>:<domain>:<purpose>:v1:<id>`。
3. 所有临时 Key 必须设置与业务一致的 TTL。锁、幂等键和队列分别定义持有期、续期、确认、过期与孤儿恢复规则。
4. 禁止在生产主路径使用无边界 `KEYS` 和全库扫描；清理使用命名空间、SCAN、有界批次和可追溯脚本。
5. Redis 只作为性能缓存时，故障后绕过缓存必须仍能返回正确权威结果，并且这种行为需要显式设计、指标和测试。
6. Redis 承载身份、权限、验证码、限流、锁或其他安全一致性状态时，故障默认拒绝相关操作。禁止自动退回进程内状态或放行请求。
7. 缓存写失败、删除失败和旧值使用的可见语义必须在用例中定义；禁止因缓存异常返回假成功或过期权威数据。
8. Key 格式变化属于数据契约迁移，必须定义版本、旧 Key 处理、TTL 保留、冲突和删除时间，禁止静默覆盖。
9. 认证限流、Refresh 锁和其他参与当前安全判断的 Redis 操作失败时默认拒绝请求。数据库认证事务已经提交后，清理历史登录限流键属于非权威派生操作；失败不得翻转已提交结果，但必须携带 Profile 与 `request_id` 记录可观测告警并具有专项测试。

## 12. 外部 HTTP 与异步 I/O

失败分类、重试和结果未知语义以[错误与失败模型](error-model.md)为准。

1. 生产外部 HTTP 使用由 FastAPI lifespan 管理的共享 `httpx.AsyncClient` 或经 ADR 确认的等价异步客户端，禁止每次请求创建新的连接池。
2. 客户端分别配置连接、读取、写入和连接池等待超时，并为完整业务动作设置总时间预算。
3. 重试只允许经过分类的瞬时错误，必须限制次数、退避、抖动和总预算。调用方取消、输入错误、鉴权失败和确定的业务拒绝不得重试。
4. GET 等幂等读取可以有限重试；具有副作用的写请求只有在远端幂等键、协议保证或结果确认机制成立时才允许自动重试。
5. HTTP 200 不等于业务成功。适配器必须验证允许的状态码、业务码、内容类型和响应 Schema，未知结构按上游响应无效处理。
6. 外部协议只存在于 Integration Adapter，Service 只依赖 Port 和项目 DTO，禁止第三方响应结构穿透到 Domain 与公开 API。
7. 允许用户提供 URL 的抓取能力必须使用结构化解析，校验协议、DNS 结果、每次重定向、目标地址范围、响应体大小和内容类型，阻止 SSRF。
8. 同步 SDK、密码哈希、压缩、图片处理和阻塞文件 I/O 必须显式隔离到线程池或任务系统，并设置并发、超时和资源上限。
9. 普通测试默认拦截未声明的外部网络。真实第三方验证使用独立受控流程、脱敏数据和明确授权，不进入普通 pytest 套件。

## 13. 错误、日志与审计

错误分类遵守[错误与失败模型](error-model.md)，权限与审计职责遵守[认证、授权与审计边界](authentication-authorization.md)，信号职责遵守[可观测性与可靠性基线](observability-reliability.md)。

### 13.1 异常实现

1. 领域业务错误使用稳定错误码和 `AppException` 或经项目统一定义的子类，错误码按领域集中维护，禁止散落魔法字符串。
2. Repository 不抛 `HTTPException`。持久化异常向事务所有者传播，并在统一边界分类；唯一约束冲突只有在确认具体约束语义后才能映射为业务冲突。
3. 全局异常处理器是未知异常的最后安全边界，只负责记录脱敏异常并返回 `500`，不能承担业务降级。
4. 转换异常时保留原始异常链，禁止记录后抛出无关联的新异常，也禁止在多层重复记录同一异常堆栈。
5. 客户端响应不得包含异常类、堆栈、SQL、文件路径、DSN、凭据、内部服务地址和完整第三方响应。

### 13.2 运行日志

1. 使用项目统一的 Loguru 入口，业务代码禁止 `print()` 和自行配置独立日志 Sink。
2. 请求日志至少关联 `request_id`；跨组件调用同时关联 `trace_id`，部署后关联 `release.version`，业务标识只记录必要的脱敏形式。
3. 日志采用字段白名单。密码、Token、Cookie、Authorization、密钥、DSN、Webhook URL、请求头、完整请求体、完整第三方响应、HAR 和敏感个人信息默认禁止记录。
4. 写入成功和重要状态变化使用 INFO，可预期拒绝和保护触发使用 WARNING，未知异常在最外层统一记录 ERROR。高频成功读取不记录低价值日志。
5. 日志失败不能改变已经确定的业务结果，但必须具备本地可见性、容量限制和运维告警；禁止因日志异常递归记录造成请求雪崩。

### 13.3 审计

1. 审计日志与运行日志分离，记录操作者、动作、目标、结果、时间、关联 ID 和运行版本，不记录秘密和完整敏感载荷。
2. 高权限、批量、导出、删除、凭据、安全配置和其他高风险写操作必须先建立审计意图。无法建立审计意图时拒绝操作。
3. 外部副作用已发生但审计完成状态更新失败时，保留待核查意图并触发告警，禁止伪装为完整成功或盲目重做副作用。
4. 审计保留、访问控制、查询和删除规则由本商城依据合规与业务风险确认。

## 14. 生命周期、健康检查与可靠性

健康语义和部署等级以[可观测性与可靠性基线](observability-reliability.md)为准。

1. FastAPI lifespan 统一创建和关闭数据库 Engine、Redis Client、HTTP Client 及其他进程级资源，禁止依赖模块导入和进程退出碰巧清理。
2. Startup 验证配置和必要初始化。不可恢复的配置错误直接退出；短时依赖故障按明确契约选择退出或保持 Readiness 失败，禁止报告可服务。
3. Liveness 只证明进程事件循环仍能响应，不访问 PostgreSQL、Redis和外部 API，避免依赖抖动引发重启风暴。
4. Readiness 检查 PostgreSQL、Alembic revision、必要配置和当前启用且服务关键请求必需的依赖。每项检查使用严格超时，失败返回 HTTP 503 和安全摘要。
5. Redis 只有在当前服务的关键安全或一致性能力依赖它时才进入 Readiness；仅作为可绕过性能缓存时应通过独立降级指标表达。
6. 探针响应禁止泄露 DSN、SQL、凭据、内部路径、堆栈和第三方响应。
7. 优雅停机先停止接收新流量，再在有界时间内完成或取消进行中的工作，最后关闭客户端和连接池。超时后的未完成副作用必须具有恢复状态。
8. 数据库池、HTTP 池、Redis、线程池、后台任务、队列和批处理都必须设置硬上限；无界并发、无界队列和无限重试禁止进入生产。
9. 当前 1Panel 单机部署只能称为单机可恢复模式，多实例高可用必须由本商城另行设计并验证数据层、流量、任务和故障转移。

## 15. 测试落地与隔离

测试层级和完成条件以[测试与质量策略](testing-strategy.md)为准。

### 15.1 环境隔离

1. 测试环境变量在导入 `app` 前设置，禁止依赖已经缓存的开发 Settings。
2. 数据库测试只连接名称以 `_test` 结尾的独立 PostgreSQL 数据库，并在迁移、建表、清理前同时校验环境标识、主机允许范围、数据库名和连接身份与开发、生产隔离。
3. 任一数据库身份条件无法确认时立即终止。禁止自动切换到开发库、SQLite 或内存数据库继续执行。
4. 测试只清理本次测试创建且可准确定位的数据或 Schema，禁止对未知数据库执行 `drop_all()`、全表清空或无条件删除。
5. 普通测试默认禁止未声明外部网络；真实 PostgreSQL 与 Redis 集成测试属于 Backend 全量门禁，第三方服务验证使用独立标记、环境和授权。

### 15.2 分层要求

1. Domain 单元测试无数据库和网络，覆盖边界值、不变量和非法状态转换。
2. Application Service 测试通过 Port、Fake 或 Stub 验证成功、拒绝、回滚、幂等和结果未知，禁止 Mock 被测对象内部方法。
3. Repository 集成测试使用真实 PostgreSQL，覆盖约束、加载、时区、JSONB、锁和并发语义，禁止用 SQLite 替代。
4. API 测试从真实 FastAPI 应用入口发起请求，覆盖结构校验、身份、权限、错误映射和响应契约；外部依赖使用受控 Adapter 替身。
5. 每个受保护端点至少覆盖成功、未认证、无权限和与其风险相关的关键失败路径。公开端点按实际权限边界调整。
6. 迁移测试覆盖空库升级、已有库增量升级、重复升级、Model 一致性及适用的恢复路径。
7. `skip` 和 `xfail` 必须写明原因、负责人和清理条件；关键门禁不得因缺少依赖静默跳过。

## 16. 质量门禁

Backend 当前 `ready`，以下默认轻量门禁从 `apps/backend` 执行：

```powershell
uv sync --locked
uv run python -m compileall -q app alembic scripts
uv run python -c "from app.main import app; print('APP_IMPORT_OK')"
uv run python -c "from app.main import app; schema = app.openapi(); print('OPENAPI_OK', len(schema.get('paths', {})))"
uv run ruff check .
uv run ruff format --check .
uv run mypy app
uv run lint-imports
```

从仓库根目录继续执行：

```powershell
pnpm check:governance
pnpm generate-api
git diff --exit-code -- openapi.json packages/api-client/src
```

适用规则：

1. 日常开发、普通提交、`$git-sync`、Push 和 Pull Request 只自动运行上述轻量门禁，不运行 pytest、测试数据库迁移或测试 Redis。
2. 用户明确授权 Backend 测试时，才运行 `uv run alembic check` 和被点名的 pytest 范围；授权只对当前任务生效。
3. `pyproject.toml` 对 `app` 同时统计行与分支覆盖率。经授权运行全量 pytest 时低于 90% 必须失败，禁止通过 marker、单测子集或关闭 coverage 伪装全量通过。
4. 经授权的全量 pytest 必须显式提供隔离的 `TEST_DATABASE_URL` 与 `TEST_REDIS_URL`，数据库名必须以 `_test` 结尾；依赖不可用时按 fail closed 规则失败。
5. 数据库不可用、测试跳过、工具未安装、未获授权和替代验证必须分别报告，不能汇总为“测试通过”。
6. 修改公开 API 时必须重新导出 OpenAPI 并生成客户端；生成后工作区存在差异表示契约尚未同步完成。

## 17. 代码评审清单

Backend 详细设计、实现和评审至少核对：

- 依赖方向、领域所有权和跨领域协作是否符合专题架构文档。
- Router 是否只处理协议，最外层事务是否只有一个所有者。
- Repository 是否只进行持久化操作并且没有提交、回滚、权限和业务判断。
- Schema、ORM、数据库类型和 OpenAPI 是否一致，敏感字段是否可能泄露。
- 异常是否明确失败并保留异常链，有无空值、默认值、假成功或隐式兼容。
- 并发、幂等、外部副作用和超时后结果未知是否具有可恢复设计。
- 配置、日志、审计、测试 Fixture 和错误响应是否泄露秘密或个人信息。
- 迁移是否不可变、可审查、经过真实 PostgreSQL 验证并具有恢复条件。
- Redis 和缓存是否仍以 PostgreSQL 或明确外部系统作为权威来源。
- 是否存在同步 I/O 阻塞事件循环、无界并发、无限重试和无总预算调用。
- Liveness、Readiness 和 Startup 是否各自回答正确问题。
- 实际门禁、跳过项、未执行项和剩余风险是否如实记录。
- 列表查询排序是否遵守第 8 节第 7 条规范：分页列表用 `id.desc()`，禁止冗余添加 `created_at.desc()`；从属子列表用 `id` 正序；含 `sort_order` 的列表用 `sort_order.asc().nulls_last(), id.desc()`。
- 新增 `sort_order` 字段是否符合第 9 节第 12 条规范：`nullable=True, default=None`，`ge=0`，禁止 `NOT NULL DEFAULT 0`，并同步 Alembic 迁移。

发现标准无法覆盖的新型高风险边界时，先更新当前计划；涉及长期技术取舍时新增 ADR；确认后的稳定规则再进入对应权威文档。禁止在单个实现中私自创造例外。
