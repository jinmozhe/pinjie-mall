# 小程序身份与商品内容接入

## 当前交付边界

已有小程序登录、内存会话、个人中心基础信息、本人地址、购物车、服务端报价、幂等创建订单、本人订单分页筛选、详情、取消及受限商品说明源码。默认微信登录关闭；游客模式可以公开浏览。2026-10-13 本机开发库已迁移至 20261013_01 并核对数据保留及新增结构，分类索引模型对齐后开发库全库漂移检查通过；测试库、真实微信平台和业务渠道验收未执行。

本人履约、整单售后、评价及公开帮助已补充源码，入口与恢复步骤见[履约售后接入手册](miniapp-fulfillment-and-aftersales.md)。

本地日常运行以[本地开发手册](local-dev-environment.md#终端三小程序-watch-与微信开发者工具)为准：Codex/VS Code 编辑源码，Backend 18168、Admin 3001 独立运行，根目录 pnpm --filter @pinjie/miniapp dev:weapp 持续编译到 dist，微信工具加载 apps/miniapp。依赖和配置改变后重启 watch；不启动 H5 或 3000。

## 统一消费者入口

登录、刷新、退出和能力查询使用 `/api/v1/auth`，资料与会话使用 `/api/v1/users/me`；交易调用原地址、购物车、结算、订单与退款路径。所有私有端点使用 ConsumerBearer 并拒绝 Cookie，旧密码登录与注册已退役。Backend 与小程序必须配套更新，不存在旧路径别名。完整边界见 [ADR 0019](../adr/0019-消费者接口统一与浏览器认证退役决策.md)。

## 联调前置条件

1. 准备真实公开 AppID，配置小程序 project.config.json；AppSecret 只进入服务端安全配置，不发送到聊天或前端。
2. 按目标库备份与迁移流程审查并升级至 Alembic 20261013_01。除前序会话/内容字段外，当前模型需要手机号验证三字段及外部身份 union_scope_id，旧环境不可直接使用新模型。本机开发库已升级；其他环境单独核验，权限同步本轮未执行。
3. 在服务端配置 MINIAPP_LOGIN_ENABLED=true、WECHAT_APP_ID、WECHAT_APP_SECRET、MINIAPP_JWT_SECRET、MINIAPP_TOKEN_HMAC_KEY。JWT/HMAC 至少各 32 UTF-8 字节，彼此不同且与既有四个 Browser 密钥不同；AppSecret 不使用模板值。缺失配置拒绝启用。默认 .env.example 为空秘密模板与关闭开关。
4. 保持服务端 Redis 为 required。按权限目录同步流程核对 settings:miniapp-registration:read/update，再在 Admin“系统设置、小程序建号”开放首次建号。现有身份登录不受该建号开关影响。
5. 配置微信 request 合法 HTTPS 域名和平台服务隐私保护指引、必要联系渠道。游客 AppID 与本地不校验域名设置只适用于公开浏览模拟器；真机需要真实可达环境。

小程序总开关控制微信换码与私有接口；Admin 建号开关仅控制新身份首次开户。关闭总开关时所有私有能力返回不可用，公开商品继续可浏览。不会提供模拟登录、公共默认密码或自动绑定旧账户。

## 会话与下单恢复

首次无绑定的可信微信身份在建号开关允许时自动创建独立 wx_ 用户名、空密码账户和绑定。前端无独立注册步骤。首次没有必要同意时只展示公开页面，用户主动认证时阅读说明并通过官方隐私流程；已有应用同意且微信侧无待授权状态、未主动退出时后台恢复，不打断公开浏览。

GET /users/me 返回 phone_bound 与 phone_masked。未绑定时通过统一认证页主动触发 getPhoneNumber，POST /users/me/phone 只绑定当前账户；后端使用 stable_token、可信 OpenID 归属校验、水印和号码校验。相同号码绑定他人或请求更换本账号号码返回冲突，不合并身份。换码或请求结果未知时先查询本人手机号状态，再决定是否取得新 code；旧 code 不重放。

个人中心外壳公开；购物、地址、订单、会员、推荐、积分和资金入口同时检查已验证手机号，PHONE_BINDING_REQUIRED 不触发 Token 刷新。本人资料、手机号绑定、退出、会话管理与注销说明保留基础身份入口。成功后按白名单返回原页；商品恢复原 SKU、数量及意图后由用户再次确认。无目标进入个人中心，取消回来源，返回意图仅在内存保留 15 分钟。昵称头像引导可跳过。

开放前核实已认证非个人主体的手机号资格、额度、服务端出口 IP、隐私声明和触发用途。可选 WECHAT_UNION_SCOPE_ID 仅在核实开放平台归属后配置，未知时不配置；旧记录不自动回填。当前只开放已登记的单 AppID 设计，第二应用和 UnionID 自动识别未接通。

会话只在 lib/session.ts 私有内存。冷启动在已有隐私确认且未主动退出时重新取得微信 code；退出取消私有请求、递增身份代次并清除私有 Query。凭据不进入平台 storage、URL、日志或业务 Store。刷新超时可能已经轮换，客户端清除会话并要求重新登录，不重发旧 Refresh。

结算草稿以 schemaVersion=1 按本人用户 ID 隔离，仅含请求号、商品类型、规格 ID、数量、地址 ID、报价指纹和提交标记。提交前先保存恢复记录，存储失败时不发送订单写请求。实物和虚拟商品分开结算，虚拟商品不读取或索取地址。

下单超时、取消或登录失效时保留原内容。GET /api/v1/orders/by-request/{request_id} 只查本人，404 表示当前尚未确认，不能证明原请求永远失败；只有显式原请求恢复可以再次提交同键同内容。报价明确被拒绝后需重新预览确认。购物车原条目保持，订单页提示用户自行移除。

加购没有业务幂等号，失败后先重新读取购物车核对数量；地址新增失败先读取地址列表；更新使用 revision，冲突时保留输入并明确重新读取。取消订单后读取最新服务端状态，不根据客户端计时器释放库存。真实微信支付尚未接入，待付款订单不提供假支付入口。

## 商品内容迁移

新说明允许的标签和颜色见[工程标准](../architecture/miniapp-engineering-standard.md#6-商品富文本与图片)。非法输入拒绝，不静默清洗。description_version=0 的旧内容不进入公开 HTML，Admin 可以读取并明确编辑保存为 v1。

在 apps/backend 中，指定已审计来源及目标数据库名称执行只读校验：

```powershell
uv run python -m scripts.migrate_product_content --confirm-database pinjie_mall_dev --product-id <商品UUID> --source-format html
```

普通文本必须明确用 --source-format text，工具先转义再规范化。通过校验后，经该目标数据迁移授权增加 --apply；每批 1 至 100 个唯一商品 ID，所有内容验证成功后才整批写入并递增商品 revision。不要混合未知来源，不输出原始说明。迁移窗口、负责人、观测和删除测试见[ADR 0018](../adr/0018-小程序独立身份会话与内容边界决策.md#历史内容迁移窗口)。

## 验证范围

日常仅 Backend 轻量门禁、生成契约及 Miniapp/Admin typecheck、lint。新测试源码包含内容边界、外部秘密保护、会话代次、冷启动退出、并发首次建号与 Refresh 重放；执行需明确点名 pytest/Vitest 和隔离环境。watch、production build、微信自动化、真机、数据库升级和发布不能由静态通过推断。
