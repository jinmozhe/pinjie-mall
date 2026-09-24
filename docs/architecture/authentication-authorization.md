# 认证、授权与审计边界

## 1. 目标

本文件定义当前 Browser Cookie Profile 的身份认证、会话、权限声明、资源授权和审计机制。重大取舍以 [ADR 0010](../adr/0010-浏览器认证会话RBAC与审计决策.md) 为准，完整端点与验收规格以当前源码、根 OpenAPI 和测试为准。阶段 C 历史计划文件未纳入当前仓库。

## 2. 分层职责

| 层 | 职责 |
| --- | --- |
| Middleware | 请求 ID、Trace 上下文、安全头、可信代理边界和日志上下文 |
| Dependency | Cookie 或 Token 解析、会话校验、当前身份加载和通用权限依赖 |
| Router | 声明端点需要的身份、角色或权限，不执行资源查询 |
| Service/Policy | 结合资源归属、资源状态、租户或业务数据执行授权 |
| Database | 唯一约束、外键和适合数据库保证的数据不变量 |

身份认证失败使用 `401`，身份有效但无权执行使用 `403`。资源是否存在本身敏感时，可以按统一策略返回 `404`，同类接口必须保持一致。

## 3. 默认拒绝

- 受保护端点必须显式声明认证要求。
- 没有匹配授权规则时拒绝。
- 管理端页面隐藏、按钮禁用和客户端路由保护只改善体验，不承担安全控制。
- 超级管理员仍需经过统一身份、授权和审计链，禁止绕过。
- 后台任务和内部调用使用独立服务身份或明确调用上下文，禁止伪装最终用户。

## 4. 客户端认证 Profile

阶段 C 只开放 Web 与 Admin 的 Browser Cookie Profile：

- Access 与 Refresh 使用 `HttpOnly`、`SameSite=Lax` Cookie，生产必须启用 `Secure`，不设置 `Domain`。
- C 端 Cookie 使用 `pinjie_web_*` 命名，B 端使用 `pinjie_admin_*` 命名。Access 路径为 `/`，Refresh 分别限制到 `/api/v1/auth` 与 `/api/v1/admin/auth`。
- CSRF Cookie 允许浏览器读取，但只保存 Session 绑定的随机值。服务端只保存 HMAC 摘要，并以常量时间比较。
- 登录响应只返回主体、Session 与过期时间，不返回 Access Token 或 Refresh Token。
- Token 不进入 Zustand、`localStorage`、`sessionStorage`、URL、页面源码、日志或其他客户端可读持久化存储。
- Web 与 Admin 分别配置 `WEB_ORIGINS` 和 `ADMIN_ORIGINS`，两组值必须是无路径的绝对 HTTP(S) Origin 且不得重叠。登录、注册、Refresh、Logout 与其他 Cookie 写请求按当前 Profile 精确校验，不能用统一 CORS 列表替代 Profile 隔离。
- Web BFF 只允许已登记的方法与用户端路径，只转发 `pinjie_web_*` Cookie；Admin 反向代理只开放管理端路径和公共系统状态。代理过滤用于缩小攻击面，Backend 的 Profile、认证与授权检查仍是最终边界。

小程序、原生 App 和其他无法可靠使用 Cookie 的客户端属于后续 Public Client Bearer Profile。该 Profile 必须独立定义端点、Session 类型、客户端证明、Token 存储、轮换、撤销和测试契约，禁止临时复用浏览器登录响应输出 JSON Token。

## 5. JWT、密码与 Session

- Access JWT 使用 PyJWT 与固定 `HS256` allowlist。Web 和 Admin 分别使用独立 Secret 与 `pinjie-web`、`pinjie-admin` audience。
- JWT 必需 Claims 为 `iss`、`aud`、`sub`、`sid`、`jti`、`iat`、`nbf`、`exp`、`token_type` 和 `credential_version`，允许最多 30 秒时钟偏差。JWT 不保存角色、权限和个人资料。
- Web Access 默认 15 分钟，Admin Access 默认 10 分钟。验签后继续校验 PostgreSQL Session、主体状态与凭据版本。
- 密码使用 Argon2id。Hash 和 Verify 通过线程池执行，并由进程内信号量限制并发。未知用户名执行固定虚拟密码校验，避免明显的账号枚举时序差异。
- 用户和管理员在注册、修改、重置及初始创建时，新密码统一要求 6 至 64 个字符。登录和修改本人密码时的当前密码最多接受 64 个字符；现存超过 64 个字符的密码需要先通过受控重置改为符合当前策略的密码。
- PostgreSQL 是 Session 和 Refresh Token 的权威来源。Refresh 原值只进入 `HttpOnly` Cookie，数据库保存 HMAC-SHA256 摘要。
- Refresh 闲置期限默认 7 天，Session 绝对期限默认 30 天。刷新通过行锁单次消费并旋转，已消费 Token 重放会撤销整个 Session Family。
- Web 与 Admin 初次登录创建 Session 时，使用锁定版本的 `ua-parser` 从已清理 User-Agent 生成“浏览器 · 操作系统”展示名称，并同时保留原始摘要。该名称不包含浏览器或系统小版本，不参与认证、授权或可信设备判断；空值和无法识别的输入继续显示为未知设备，Refresh 不重命名既有 Session。
- Session 列表统一使用 `items`、`total`、`page` 和 `page_size` 分页契约。超过绝对期限或撤销时间 30 天的 Session 由显式保留工具清理，关联 Refresh Token 通过外键级联删除。
- 用户或管理员修改自己的密码时递增 `credential_version`、保留并轮换当前 Session Cookie、撤销其他 Session。主体状态、管理员角色、超级管理员标记或管理员重置凭据变化时撤销受影响会话。

四个 JWT/HMAC Secret 必须至少包含 32 个 UTF-8 字节、彼此不同且不能使用模板值。认证启用后 Redis 必须为 `required`；生产缺少安全 Cookie、可信代理、明确 CORS 或 Release 配置时拒绝启动。

### 5.1 普通用户创建来源

普通用户有两种独立创建来源：

- Web 公开注册受数据库 `system_settings.registration.enabled` 控制。注册事务对配置行取得共享锁，配置缺失、无效或数据库不可用时明确失败并保持关闭；注册成功后创建 Web Session、Refresh Token 和登录安全事件。
- Admin 创建用户使用 `POST /api/v1/admin/users`，受 `users:create`、管理员会话和 CSRF 保护，不受公开注册开关影响。该流程只创建账户和 `users:create` 审计事件，不创建 Web Session、Refresh Token 或公开注册登录事件。

两种来源复用相同的用户名、邮箱唯一性和密码规则。软删除账户继续占用用户名与邮箱，管理员应恢复原账户，不能用同一标识创建新账户。Admin 创建审计只记录目标、启用状态和可选资料是否存在，不保存初始密码、密码摘要或邮箱明文。

登录后的用户资料通过 `GET/PATCH /api/v1/users/me` 读取和更新；头像使用独立的 `PUT /api/v1/users/me/avatar`，只接受当前用户自己上传的 `avatar` 资产 ID，传 `null` 解除绑定。头像更新受 Web 会话、精确 Origin 和 CSRF 保护，不改变凭据版本或会话。

管理员本人资料和管理员管理资料入口继续接受头像 URL。站内上传路径及已配置 Web/Admin Origin 下的上传地址先归一化为资产公开路径，移除查询参数和片段，再按唯一文件键校验并锁定资产；资产已删除时拒绝保存。绑定与资产删除共用资产行锁，事务结束前保持锁定，已提交头像引用阻止删除。其他外部 URL 和非资产静态路径保持原有行为，清空头像解除引用。

公共端点 `GET /api/v1/system/capabilities` 只返回 `registration_enabled`。Web 在能力关闭时隐藏注册入口并把 `/register` 重定向到登录页；查询失败时按未知且不开放处理，并显示服务不可用状态。Backend 的公开注册端点始终执行权威开关校验，前端隐藏不承担安全控制。

系统设置使用八项独立权限：`settings:site:read`、`settings:site:update`、`settings:registration:read`、`settings:registration:update`、`settings:order-shipping:read`、`settings:order-shipping:update`，以及分佣总开关对应的 `settings:commission-control:read` 和 `settings:commission-control:update`。Admin 设置写接口同时要求管理员会话、准确权限、CSRF、revision 校验和审计；LOGO 上传与删除归站点更新权限，不复用文件资产权限。平台运费和分佣总开关分别由商品运费页、分佣政策页的独立受控区域维护。

站点 LOGO 使用每次操作独立且不可变的 UUID 文件键。数据库提交失败时只补偿本次操作创建的临时对象，不覆盖或删除已有目标文件；并发更新依靠修订号和进程内串行化保护，避免旧操作回滚新提交的媒体。

## 6. CSRF 与来源校验

- Cookie 身份的 `POST`、`PUT`、`PATCH` 和 `DELETE` 请求必须同时通过精确 Origin allowlist 与 `X-CSRF-Token` 校验。
- Refresh 与 Logout 使用 Refresh Cookie 和同一 Session 的 CSRF 对，普通受保护写请求使用 Access Cookie 对应的当前 Session。
- 登录和注册尚无 Session，仍执行 Origin 校验，并结合 `SameSite=Lax` Cookie 与 Redis 原子限流。
- Backend 仅在认证校验明确标记失效时清理对应 Profile 的认证 Cookie。前端仅将 HTTP 401 且错误码为 `AUTH_REQUIRED`、`AUTH_TOKEN_INVALID`、`AUTH_SESSION_REVOKED`、`AUTH_SESSION_EXPIRED` 或 `AUTH_REFRESH_REUSE_DETECTED` 的响应视为会话错误；最多执行一次 Refresh 和一次原请求重放，Refresh 端点本身不得递归重试。
- `AUTH_INVALID_CREDENTIALS` 等业务失败和未知错误码原样返回，不触发刷新、请求重放或登录失效。刷新接口的错误状态、错误码、请求标识与 `Retry-After` 继续向上传播；429、503 和网络失败不清理客户端会话状态。Web SSR 恢复遇到非会话故障时显示错误并提供手动重试，仅在明确会话失效时跳转登录。
- Logout 只有在服务端明确成功后才进入未认证页面；失败必须保留当前页面并展示可重试错误，不能把失败伪装为本地退出成功。

Admin 运行期间的受保护请求在 Refresh 失败或重放请求再次返回终止性会话错误时，通过 HTTP 管道通知运行时统一处理。运行时清理 Query 缓存、当前身份和受保护页面状态，并带原站内地址返回登录页；业务 401、网络失败、429 和 503 继续留在当前页面并按原错误反馈。

Admin 收到上述明确的会话 401 时，若 `pinjie_admin_csrf` Cookie 缺失或为空，HTTP 管道直接传播原始会话错误并通知运行时，不发起缺少必要 CSRF 条件的 Refresh。首次访问由启动流程带原站内地址跳转登录页，避免将未登录误报为刷新 CSRF 403；存在该 Cookie 时继续执行原有单飞刷新及错误传播。此判断不替代服务端认证、CSRF 和来源校验。

Admin 打开或整页刷新时，启动恢复通过 `/api/v1/admin/auth/me` 加载身份。若该请求触发 Refresh，且 Refresh 返回 `503 / SERVICE_UNAVAILABLE`，启动流程带原站内地址跳转登录页，展示安全错误消息、HTTP 状态、错误码及可用的请求编号；开发环境额外提示检查 Redis。HTTP 管道标记 Refresh 错误来源，普通身份请求或刷新成功后的重放请求返回 503 不触发此跳转。此行为只提供故障恢复入口，不将 503 归类为会话失效，也不撤销服务端会话或清理认证 Cookie。登录页跳过自动身份恢复，防止跳转循环；诊断信息通过路由状态传递，不进入 URL。新的登录失败优先展示最新错误，底层依赖恢复前重新登录仍可能失败。

## 7. 权限模型边界

本商城提供规范化 RBAC 基础，尚未预设复杂 ABAC、组织树和多租户数据权限。`PermissionCode` 与 `PERMISSION_CATALOG` 是权限目录源码，数据库通过显式 `scripts.sync_permissions --check/--apply` 同步；应用启动不自动修改权限表。

管理员、角色、权限及关联关系使用规范化表和外键。Admin 导航由前端代码维护，并按服务端返回的权限过滤，不建立动态菜单表。Dependency 校验端点权限，Service 在事务内读取权威资源状态并执行最终授权。超级管理员仍经过 Session、CSRF、最后超级管理员保护和审计链；会减少有效超级管理员数量的写操作在同一 PostgreSQL 事务内取得固定 advisory lock，串行执行计数和修改。

最终授权使用的单个管理员锁定读取显式设置 `populate_existing=True`，刷新同一 AsyncSession 中在认证阶段已加载的属性和关联。数据库行锁与 ORM 状态刷新共同保证事务内校验读取最新状态，避免并发停用或降权后复用旧身份。

管理端写用例由 `ManagementAuditCoordinator` 在同一事务内重新读取操作者、锁定并校验管理员会话和精确动作权限，再执行资源变更与审计。会话失效、降权或停用在事务提交前都会使本次操作拒绝，路由层的权限依赖不能替代这次权威复核。

`admins:update` 只负责管理员资料与状态修改，不接受 `is_superuser`。超级管理员身份统一通过 `PATCH /api/v1/admin/admins/{admin_id}/superuser` 和系统权限 `admins:superuser:change` 变更；该权限在权限目录中可见，但标记为不可分配给角色，角色权限写接口拒绝保存。独立端点同时校验管理员会话、CSRF、准确权限和当前超级管理员身份，Service 在事务内重新读取操作者权威状态；创建管理员时提交 `is_superuser=true` 也执行同一权威校验，防止从创建入口绕过。Admin 只向当前超级管理员提供身份切换入口，界面控制不替代服务端授权。

管理员资源权限只授权动作类型，不自动授权超级管理员目标。资料编辑、单条与批量状态变更、角色分配、密码重置、会话查看和会话撤销在 Service 中读取并锁定目标管理员；目标为超级管理员时，操作者的数据库权威状态也必须是启用的超级管理员，否则统一拒绝。批量目标只要包含一名超级管理员就整体拒绝普通管理员，禁止通过混合目标绕过。Admin 同步禁用超级管理员行的对应按钮、状态 Tag 和批量复选框，但该界面限制只承担体验职责。

角色权限配置继续消费 `GET /api/v1/admin/permissions` 返回的扁平源码权限目录，并向角色权限写接口提交 `permission_codes: string[]`。Admin 在弹窗内按权限码资源前缀直接展示 Ant Design Tree，支持父子联动、名称和代码搜索、全选、反选、清空及展开控制；搜索只过滤显示，全选、反选和清空始终基于完整启用权限目录，已分配的停用权限保持锁定。未知前缀进入“其他权限”，分组节点只使用前端内部 key，提交前按当前权限目录过滤，因此后端契约、权限码权威来源和服务端授权边界不依赖前端树结构。

Admin 不提供管理操作的密码二次确认 Token 或确认请求头。所有单条和批量管理端点必须通过管理员会话、准确资源权限、CSRF、事务内资源校验和审计；前端隐藏路由或按钮只改善体验，不承担授权控制。Admin 的所有删除、移入回收站和移除操作，无论软硬删除、单条或批量，均先通过统一标准警告弹窗确认操作者意图，并防止重复提交、明确反馈失败；具体入口和交互约束见 [Admin 工程实施标准](admin-engineering-standard.md)。启停、凭据重置、身份与权限变更、会话撤销等非删除操作保持原交互。

旧版 `POST /api/v1/admin/auth/confirm` 仅在 2026-08-27 至 2026-09-26 按 ADR 0007 保留为受控契约兼容端点。它继续校验当前管理员密码并返回历史响应结构，但确认回执不写入 Redis、不参与后续操作授权，仓库当前 Admin 不调用该端点。每次使用记录 `admin_confirmation_compatibility_used` 结构化警告；到期必须核对调用量并删除端点、兼容 Schema、Service 方法和对应弃用契约测试，延期需要重新确认。

每个新增 Admin 管理端点必须在 Router 显式声明准确 `PermissionCode`。管理员登录态、超级管理员客户端显示、Admin Access 和通用权限均不能替代端点资源权限；权限目录缺少代码时先更新 `PermissionCode` 与 `PERMISSION_CATALOG`，通过目录检查后再按受控 `scripts.sync_permissions --check/--apply` 流程同步目标环境。应用启动不自动修改权限表。

Admin 数据列表的批量写操作使用显式 UUID 集合和专用 Backend 端点，每次限制 1 至 100 个且拒绝重复 ID。目标集合按固定顺序锁定并在一个事务中完成，任一目标缺失、生命周期冲突、仍被引用或会话撤销失败时整批回滚。用户批量删除使用 `users:delete` 权限，把账户移入回收站、停用账户、提升凭据版本并撤销会话，同时记录通用软删除主体 ID、主体类型和可选删除原因；软删除记录长期保留并占用用户名和邮箱，避免恢复冲突。用户单条和批量恢复使用独立 `users:restore` 权限，恢复后保持停用且历史会话继续失效，不受时间期限或匿名化状态限制。用户自助注销使用同一软删除流程，保留资料并记录用户本人作为删除主体。角色与文件资产批量硬删除分别使用 `roles:delete`、`assets:delete` 权限，并在 Admin 使用统一标准警告弹窗。角色只允许删除未分配给管理员的记录，文件资产删除还必须完成存储暂存和失败恢复。角色批量停用使用 `roles:update` 权限，并撤销关联管理员会话。管理员账户继续使用启用和停用表达生命周期，不提供删除接口。

登录安全事件、审计事件和请求元数据属于保留策略管理的安全事实，Admin 不提供人工选择或批量删除入口。

## 8. 审计与请求元数据

以下事件默认属于高风险审计范围：

- 管理员登录成功、失败和会话失效。
- 角色、权限和管理员状态变化。
- 用户账号禁用、解锁、凭据重置和高风险资料变化。
- 数据导出、批量修改、删除和不可逆操作。
- 安全配置、部署和迁移等生产变更。

审计记录至少关联操作者、动作、目标、结果、时间和 `request_id`。高风险业务通过 `AuditCoordinator` 建立审计意图，成功变更与审计结果在同一事务提交；拒绝和异常由独立终结器记录。登录安全事件属于认证结果，写入失败时认证失败关闭。

普通访问日志使用结构化输出。可选请求持久化只支持 `REQUEST_LOG_MODE=metadata`，由 Redis Stream、Consumer Group、pending reclaim、DLQ 和 PostgreSQL `request_id` 唯一约束组成。正常请求不保存请求体；错误 JSON 请求只在非敏感路由捕获，递归脱敏敏感字段并限制为 4096 字符。登录和改密等敏感路由、响应体、Cookie、Authorization 和 Token 永不进入请求日志。

登录安全事件和审计事件默认保留 180 天，请求元数据默认保留 30 天，已过期或已撤销 Session 默认额外保留 30 天。清理由显式 dry-run/`--apply` 脚本执行，不在请求进程内自动删除。应用日志、审计日志、指标和 Trace 各自承担独立职责。

## 9. 必测场景

- 未认证、凭据过期、凭据撤销和会话注销。
- 有身份但缺少权限。
- 资源属于其他主体或处于禁止操作状态。
- 权限在请求期间发生变化。
- 超级管理员和服务身份的审计链完整。
- 错误响应不泄露资源存在性或敏感上下文。
- C/B Secret、audience、Cookie、Session 和权限交叉使用均被拒绝。
- CSRF 缺失、错误 Origin、Refresh 并发与重放均失败关闭。
- 响应、浏览器存储、页面源码、日志和测试产物中没有 Token 泄露。
