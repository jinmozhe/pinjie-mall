# 文件与多媒体资产存储架构

## 1. 适用范围

本文说明商城统一文件资产能力的领域边界、存储流程、安全策略和一致性语义。当前实现提供本地磁盘驱动；云对象存储在保持同一 `StorageProvider` 契约的前提下扩展。

## 2. 组件与职责

| 组件 | 职责 |
| --- | --- |
| `app/domains/assets/` | 声明上传、分页查询、删除的 HTTP 契约与资产 Schema |
| `app/services/assets.py` | 执行场景策略、主体授权、去重、元数据事务和删除补偿 |
| `app/services/storage/` | 定义存储端口并实现本地文件的暂存、提交、恢复和清理 |
| `app/db/models/asset.py` | 保存资产主体、存储键、真实 MIME、大小、哈希、URL 与场景 |
| Admin/Web 上传组件 | 选择文件、调用双域上传端点、回填站内资源路径并展示结果 |

Router 不处理文件系统或数据库事务。Repository 只读写资产元数据，文件副作用由 Service 通过存储端口编排。

## 3. 上传流程

1. `/api/v1/assets/upload` 根据精确 `Origin` 选择 Web 或 Admin Cookie Profile。
2. 依赖层验证访问 Cookie、权威会话、CSRF Cookie/Header 配对和 Session 中的 CSRF 摘要。
3. Service 校验受控 `scene`、扩展名、场景体积上限和上传主体可用场景。
4. 本地驱动以 64 KiB 分块在线程池读取，计算 SHA-256，并通过 Magic Number 与 OOXML ZIP 结构探测真实类型。
5. 文件先写入私有 staging，完成 `fsync` 后以 `os.replace` 原子提交到公开根目录。
6. 元数据写入 PostgreSQL；提交失败时对已经落盘的文件执行补偿删除。
7. 返回 `/static/uploads/{scene}/{YYYYMMDD}/{hash}_{uuid}.{ext}` 站内路径。

同一上传主体、场景和 SHA-256 哈希命中唯一约束时复用已有资产。去重不跨主体，避免共享物理对象导致授权和删除引用不明确。

## 4. 本地目录与持久卷

本地开发默认公开根为 `apps/backend/uploads`。生产容器使用以下布局：

```text
/app/storage/
├── uploads/
│   └── {scene}/{YYYYMMDD}/{hash}_{uuid}.{ext}
├── .uploads-staging/
└── .uploads-trash/
```

生产命名卷挂载 `/app/storage`，`UPLOAD_LOCAL_ROOT` 为 `/app/storage/uploads`。staging、trash 和公开文件因此位于同一文件系统，原子移动不会跨卷；FastAPI 只挂载 `uploads/`，两个私有目录不进入静态路由。

## 5. 场景与安全边界

- `avatar`：JPEG、PNG、WebP，最多 2 MB。
- `article`：JPEG、PNG、WebP、GIF，最多 5 MB。
- `product`：JPEG、PNG、WebP，最多 10 MB。
- `document`：PDF、DOC、DOCX、XLS、XLSX，最多 30 MB。
- `attachment` 与 `temp`：受全局扩展名和总大小上限控制。
- Web 用户只允许 `avatar`、`attachment` 和 `temp`；Admin 可以使用全部场景。
- SVG 始终不在默认白名单中，避免同源静态脚本执行风险。
- 客户端声明的 `Content-Type` 不作为信任来源，响应带 `X-Content-Type-Options: nosniff`。
- 文件名只保存为元数据；落盘键由场景、日期、哈希和 UUID 生成，禁止使用原始路径。

## 6. 删除一致性

管理员单条或批量删除资产必须具有 `assets:delete` 权限并写审计事件。两类物理硬删除在 Admin 统一使用标准警告弹窗确认操作者意图，Backend 校验管理员会话、权限和 CSRF，不提供或消费密码二次确认 Token。批量请求每次接受 1 至 100 个唯一资产 ID，Repository 按 UUID 固定顺序锁定全部目标；任一目标缺失时整批拒绝。

Service 使用同一套补偿编排处理单删和批量删除：

1. 在同一数据库事务中锁定并验证全部目标，建立批量审计意图。
2. 依次把每个公开文件原子移动到私有 trash，并记录恢复所需句柄。
3. 全部文件暂存成功后删除对应元数据并提交数据库与审计结果。
4. 文件暂存、数据库写入或提交前审计失败时，按相反顺序恢复已经暂存的文件并回滚数据库。
5. 数据库提交成功后逐个清理 trash；清理失败不翻转已提交结果，保留私有残留并记录可定位的 Critical 日志供运维核查。

恢复失败时返回需要人工核查的存储错误并记录目标资产，禁止返回假成功或静默重试整个删除请求。

## 7. 头像资产引用

用户头像通过 `PUT /api/v1/users/me/avatar` 绑定已上传的 `avatar` 场景资产。Backend 在事务内锁定用户和目标资产，并确认资产上传主体是当前用户、场景为 `avatar` 且 URL 属于受控上传路径；客户端不能直接写入任意头像 URL。`asset_id=null` 只解除绑定，不删除资产文件或元数据。

资产硬删除前会查询 `users.avatar` 和 `admins.avatar` 的引用。只要仍被任一用户或管理员引用，单条和批量删除均返回 `409`，不移动文件、不删除元数据。更换或移除头像产生的未引用旧资产由管理员按现有资产清理流程处理。

## 8. 扩展边界

站点 LOGO 等固定系统配置媒体不属于统一文件资产。它们没有上传主体、业务场景、资产列表和去重生命周期，使用独立 `settings-media` 目录、固定槽位、设置权限和操作清单恢复机制，详见[系统设置架构](system-settings.md)。禁止为复用上传页面而把配置媒体写入 `assets` 表。

新增 S3、OSS、COS 或 MinIO 驱动时必须实现同等的暂存/确认、存在检查、删除恢复或等价补偿语义，并通过专项计划说明幂等、结果未知、公开 URL、权限、加密、保留期和故障恢复。禁止在配置中声明未实现驱动后静默回退本地磁盘。
