# 系统设置架构

## 1. 范围

系统设置提供跨业务可复用的运行时配置。第一阶段包含：

本页描述现行实现。目标新增 miniapp_registration、order_shipping 与 commission_control 固定分组，字段、初始化及失败语义见[全域数据库字典](database-schema-guide.md)。当前尚无这些分组的迁移/接口；不得由运行时自动补行。下述 Web 消费机制仅保留历史说明，Web 已永久冻结，不得恢复运行。

- `site`：Web 站点名称、LOGO、标题、关键词和描述。
- `registration`：Web 是否允许公开注册。

Admin 的 `Pinjie Console` 名称、登录页与控制台 LOGO 不读取站点设置。

## 2. 数据模型

`system_settings` 每个固定分组一行：

| 字段 | 规则 | 用途 |
| --- | --- | --- |
| `id` | UUID v7 主键 | 稳定记录标识 |
| `setting_group` | 唯一、最长 50 | 源码声明的固定分组 |
| `setting_value` | JSONB Object | 分组完整值，由固定 Pydantic Schema 校验 |
| `revision` | 正整数 | 乐观并发版本，每次写入加一 |
| `updated_by` | 可空管理员外键，删除后置空 | 最后修改者摘要 |
| `created_at` | 带时区 | 创建时间 |
| `updated_at` | 带时区 | 最近更新时间 |

迁移固定创建 `site` 和 `registration` 两行。注册初始值为关闭。缺行、JSON 类型错误或 Schema 校验失败统一视为服务不可用，不在运行时补行或猜测默认值。

## 3. 强类型值

`site` 值固定包含 `name`、`logo`、`title`、`keywords`、`description`。关键词按 NFC 归一、去空、保持顺序去重，最多 20 项，每项最多 64 个字符。LOGO 元数据只保存相对路径、服务端确认 MIME、大小和 SHA-256。

`registration` 值只包含严格布尔值 `enabled`。公开注册 POST 在创建用户的同一数据库事务中对该行取得共享锁并检查开关；Admin 写入取得排他锁，因此关闭操作与并发注册具有明确顺序。

## 4. 接口

公共接口：

```text
GET /api/v1/system/site-profile
GET /api/v1/system/capabilities
```

SiteProfile 一次返回公开站点完整资料，不暴露内部路径、哈希、revision 或修改者。两个公共配置响应使用 `Cache-Control: no-store`。读取失败返回 503；Web 对品牌展示使用内置回退，对注册状态按不可用且关闭处理。

Admin 接口：

```text
GET/PATCH /api/v1/admin/settings/site
PUT/DELETE /api/v1/admin/settings/site/logo
GET/PATCH /api/v1/admin/settings/registration
```

每个端点分别声明 `settings:site:*` 或 `settings:registration:*` 权限。写操作还要求 Admin Session、准确 Origin、CSRF 和审计。PATCH 为局部合并，未提交字段保持不变；请求必须携带读取时获得的 revision。

## 5. 配置媒体

本地默认目录为 `settings-media`，公开前缀为 `/static/settings`。生产使用 `/app/storage/settings-media`，与 `/app/storage/uploads` 分离但位于同一持久卷。

站点 LOGO 约束：

- 最大 2 MiB、最长边 4096、最多 1600 万像素。
- 只允许单帧 PNG、JPEG、WebP；JPEG 统一使用 `.jpg`。
- 禁止 SVG、GIF、动画、损坏、截断和仅靠文件名伪装的内容。
- 正式槽位固定为 `site/logo.png`、`site/logo.jpg` 或 `site/logo.webp`，任一时刻只保留一个。

写入顺序为：完整接收并 fsync staging、解码校验、写入操作清单、旧文件进入 trash、新文件原子替换、数据库事务提交、清理 trash 与清单。事务失败执行反向补偿。应用启动先扫描清单：数据库仍为旧 revision 时回滚，已经为预期新 revision 且媒体匹配时完成清理，其他组合记录 Critical 并拒绝就绪。

孤立 staging、trash 和数据库/文件漂移不会按时间静默清理。重新上传或删除可以修复已知 LOGO 漂移；未知恢复状态需要人工核查数据库 revision、清单与文件哈希。

## 6. Admin 与 Web

Admin `/settings` 固定显示“站点设置”和“注册设置”两个 Tab。至少拥有一项读取权限才显示菜单；Tab、只读状态和写按钮按精确权限控制。revision 冲突保留当前草稿，由管理员明确加载最新配置。

移除站点 LOGO 必须先显示统一标准警告弹窗，说明移除影响和重新上传的恢复方式，取消不请求接口。确认固定打开弹窗时的 revision，提交期间禁止重复确认及关闭，并阻止同组保存或上传。失败保留 LOGO、站点草稿和确认框并显示错误；发生 revision 冲突后必须取消、加载最新配置并重新确认，不自动用新 revision 重试删除。成功后才更新预览并关闭弹窗，完整交互约束见 [Admin 工程实施标准](admin-engineering-standard.md)。

Web 的 server-only `fetchSiteProfile()` 在同一次服务端渲染中去重。首页、登录、注册和用户中心使用站点名称与 LOGO，根 Metadata 使用标题、关键词和描述。`/static/settings` 同源代理只允许固定 LOGO 路径和正整数 revision，并返回长期 immutable 缓存。

## 7. 部署、备份与扩展

- 本地文件驱动只支持单实例，或所有实例共享同一可靠文件系统并具备跨实例写入协调。
- PostgreSQL 与完整 `/app/storage` 卷必须在同一备份窗口备份和恢复。
- 数据库回滚不会删除配置媒体。回滚到旧应用版本时必须恢复该版本所需环境和契约，不能只降数据库。
- 新配置域先定义分组 Schema、权限、专用接口和固定 UI。只有经过独立 ADR 才能引入密钥存储、支付凭据、远程对象存储或动态表单。
