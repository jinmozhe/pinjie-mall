# 小程序设计与现有后端能力映射

## 核对依据与适用范围

核对日期为 2026-10-09。本次只读根 [OpenAPI](../../../openapi.json)、Backend Router、Schema、Service 与数据库状态约束，不启动后端，不调用真实接口，不读取数据库或用户资料。接口存在代表有本地契约与实现，不代表微信调用、环境、渠道或业务验收已经通过。

页面、弹层与状态图片清单见[完整设计目录](catalog-v2.md)，离线图片浏览见[图集](gallery-v2.html)。图集和设计元数据中的方法与路径均从当前根契约核验；元数据只登记设计图片与证据，不定义第二套 API、DTO 或业务政策。

用户已确认 V1 视觉风格。V2 延续该风格并覆盖 PRD 的 R1/R2 页面及相关限制状态，扩展流程仍待评审。所有商品、金额、用户、地址、时间、编号和邀请码均为设计示例，状态图是互相独立的示例，不构成一套真实交易账本。

## 全局身份与资金边界

- 身份、基础交易、履约售后与评价已有独立 /api/v1/miniapp Bearer 源码及生成契约，默认微信登录关闭；本人订单履约组合分页、确认收货、整单售后记录与请求恢复、评价资格已接入。下表原领域路径保留为设计依据，小程序实际消费专用入口，详见[身份手册](../../operations/miniapp-identity-and-content.md)和[履约售后手册](../../operations/miniapp-fulfillment-and-aftersales.md)。设备、密码、注销及其他资金入口仍需专项适配，不要求无密码账户填不存在的密码。
- 真实微信支付调起参数、通知和查单尚未接通。`PaymentAttemptRead` 没有微信调起字段，当前创建意图明确返回 `unavailable`。成功与确认中的支付图是目标恢复流程，无法直接运行。
- 退款申请、审核、内部补偿有本地实现，真实退款渠道未接通。miniapp 安全投影已分开申请/执行/资金状态；`approved` 只代表审核通过，正额资金仅渠道 succeeded 且有确认时间才显示已确认；零金额 completed 明确无资金退回。动态渠道恢复未验收。
- 提现申请、审核和带凭证的人工完成已有实现，真实自动打款和收款目标接入未完成。小程序历史查询已有源码，`succeeded` 且有确认时间才显示人工或渠道确认；`approved` 不表示到账，新提现申请继续关闭。资料与资金专用入口见[接入手册](../../operations/miniapp-profile-and-finance.md)。

## 页面能力矩阵

| 页面组 | 现有消费端方法与路径 | 设计采用的信息与操作 | 尚需补齐或限制 |
| --- | --- | --- | --- |
| 首页/分类 | `GET /api/v1/product-categories`、`GET /api/v1/products` | 分类名称、父子关系、图标、分页公开商品、基础 SKU 价格 | 已接入公开浏览；category_id 包含启用下级，分页和总数由服务端过滤；不借用 Admin 搜索/排序 |
| 商品详情/规格 | `GET /api/v1/products/{product_id}` | 主图、description、attributes、SKUs、detail_images；有效规格组合、图片原生预览 | 当前公开 SKU 无可用库存字段，不能给出库存承诺；HTML 净化与字段语义专项未完成 |
| 商品评价 | `GET /api/v1/products/{product_id}/reviews` | rating、content、published_at 与分页 | 不虚构头像、评价图片、回复或全量好评率 |
| 购物车 | `GET/POST /api/v1/cart-items`、`PATCH/DELETE /api/v1/cart-items/{item_id}` | sku_id、quantity、selected、revision；修改数量、选择和单条删除 | 名称、缩略图、不可售原因需明确读模型或有界查询；不伪造批量删除 |
| 统一报价/结算 | `POST /api/v1/commerce/quotes`、`POST /api/v1/checkout/preview` | 适用会员价格、商品金额、平台运费、总额、地址与等级快照、fingerprint | 修改地址/数量后重报；无有效报价不能提交；不同商品类型不能混单 |
| 下单 | `POST /api/v1/orders` | request_id、完整商品意图、quote_fingerprint；零应付内部成交 | 未知结果确认查询或安全同键恢复的前端契约需专项明确，不生成新号重复下单 |
| 我的订单列表 | 当前无本人分页列表方法 | 展示目标列表、状态标签与入口，不显示假统计角标 | 分页、全量状态筛选和统计均需 C 端查询；不调用 Admin 列表 |
| 订单详情/取消 | `GET /api/v1/orders/{order_id}`、`POST /api/v1/orders/{order_id}/cancel` | 订单与商品快照、金额、acceptance_status、待付款取消 | status 只有 pending_payment/paid/cancelled；待发货/待收货/已完成须联合履约事实，不另造订单枚举 |
| 支付结果 | `POST /api/v1/orders/{order_id}/payment-attempts`、既有订单查询 | 当前不可付款、目标支付结果查询与未知恢复 | 当前意图为 unavailable；平台弹窗返回不决定资金状态；真实渠道待接通 |
| 实物/虚拟履约 | `GET /api/v1/miniapp/trade-orders/{order_id}`、`POST /api/v1/miniapp/orders/{order_id}/receipt` | 本人履约事实、操作资格、carrier、tracking_number、delivery_reference、时间与 revision | 已有源码；无实时轨迹；交付信息只向本人展示；已发货/已交付不开放本期退款；动态验收未执行 |
| 退款申请/记录 | `POST /api/v1/miniapp/orders/{order_id}/refunds`、`GET /api/v1/miniapp/refunds` 及详情/原请求查询 | 整单商品与原运费、review_mode、审核意见、执行/资金分离、未知结果恢复 | 已有本人全量分页及按单筛选源码；未发货/未交付整单，无部分数量/金额；真实渠道与恢复未验收 |
| 提交评价 | `POST /api/v1/miniapp/order-items/{item_id}/review`、trade-orders 本人 item_reviews | 1 至 5 分、正文最多 1000 字、资格与已有本人评价 | 已有源码；仅本人已交付明细一次评价；无图片上传；重复及动态验收未执行 |
| 本人资料/头像 | `GET/PATCH /api/v1/miniapp/me`、`PUT /api/v1/miniapp/me/avatar`、`POST /api/v1/miniapp/me/avatar-assets` | 昵称编辑、主动选图上传、分别绑定/移除与查询当前事实 | 已有源码；固定本人 avatar 场景，不允许 email 扩权；无手机号绑定或实名认证；平台上传未验收 |
| 退出与恢复 | `POST /api/v1/auth/logout`、`POST /api/v1/auth/refresh` | 主动退出、会话恢复失败、保留公开浏览 | 当前为浏览器 Profile；微信退出、刷新轮换与账户隔离须专项实现 |
| 安全/设备/注销 | `GET /api/v1/users/me/sessions`、会话单条撤销及 revoke-others、`POST /api/v1/users/me/password`、`DELETE /api/v1/users/me` | 设备脱敏摘要、撤销确认、已有密码账户修改密码、注销说明 | 会话模型为 browser_cookie；密码和注销要求 current_password，微信无密码凭据证明未完成 |
| 收货地址 | `GET/POST /api/v1/addresses`、`PUT/DELETE /api/v1/addresses/{address_id}` | 收件人、联系号码、三级区域名称/编码、详细地址、默认值与 revision | 最多 20 条；删除默认地址由后端选替补；区域数据源需工程专项确定 |
| 分销档案 | `GET/POST /api/v1/miniapp/membership` | 主动开通、等级名称与有效状态、已有推荐关系及绑定时间 | 已有源码；开通不等于获得等级；不输出推荐人 ID/邀请码，不绑定推荐人；无有效邀请统计 |
| 推荐关系 | `GET/POST /api/v1/miniapp/referral` | 本人码、主动确认首次绑定、已绑定事实及指定原码匹配查询 | 已有安全投影与页面源码；服务端拒绝自邀/循环/换绑；平台及数据库动态验证未执行，不输出推荐人身份 |
| 微信分享 | 本人推荐查询与页面原生分享，无独立发码接口 | 固定落地路径、本人邀请码、登录后主动确认、非法参数反馈 | 已有页面钩子、按钮与固定 5:4 封面源码；AppID 预留、平台未验收；有效邀请政策未定义，不做收益承诺 |
| 双钱包/流水 | `GET /api/v1/miniapp/wallets`、`GET /api/v1/miniapp/wallets/{wallet_type}/ledgers` | 两轨可用/冻结/欠款、本人分页流水、三类变化与历史余额快照 | 已有源码；无充值、互转或抵扣；读取失败不伪造余额；不输出幂等键或关联订单 |
| 佣金 | `GET /api/v1/miniapp/commissions` | amount、level、base_amount、rate、recovered_amount、状态与时间 | 已有本人分页源码；无状态筛选或收益汇总，不输出买家、订单或完整规则快照；动态验收未执行 |
| 提现 | `GET /api/v1/miniapp/withdrawals` | 金额、审核/执行状态、人工或渠道确认事实、时间与分页 | 已有历史查询源码；不输出收款目标、运营身份、自由文本或渠道引用；新申请关闭，真实自动渠道未接通 |
| 积分 | `GET /api/v1/miniapp/points`、`GET /api/v1/miniapp/points/ledgers` | 本人账户状态、可用/冻结/追回欠款、分页三类变动 | 已有安全查询与页面源码，大整数使用精确字符串；平台和动态验证未执行；不开放兑换/抵扣/到期功能 |
| 关于/帮助/隐私 | `GET /api/v1/miniapp/help`；原 system/site-profile 仅资料参考 | 公开帮助、问题展开、电话/邮箱操作或未配置提示、隐私说明 | 已有帮助源码；联系方式由 Backend Settings 配置，未配置明确 null；正式协议与主体需运营确认，无聊天客服 |

## 源码证据入口

| 范围 | 实际文件 |
| --- | --- |
| 小程序消费者 Router 与安全投影 | [miniapp_router.py](../../../apps/backend/app/api/miniapp_router.py)、[miniapp_trade.py](../../../apps/backend/app/services/miniapp_trade.py)、[专用展示契约](../../../apps/backend/app/services/miniapp_trade_schemas.py) |
| 消费端商品、地址 Router | [commerce_router.py](../../../apps/backend/app/api/commerce_router.py) |
| 购物车、结算与订单 Router | [transaction_router.py](../../../apps/backend/app/api/transaction_router.py) |
| 支付、履约、退款与评价 Router | [lifecycle_router.py](../../../apps/backend/app/api/lifecycle_router.py) |
| 分销、推荐、双钱包与提现 Router | [distribution_router.py](../../../apps/backend/app/api/distribution_router.py) |
| 小程序资料与资金安全投影 | [miniapp_finance.py](../../../apps/backend/app/services/miniapp_finance.py)、[专用展示契约](../../../apps/backend/app/services/miniapp_finance_schemas.py)、[共享资料用例](../../../apps/backend/app/services/accounts.py) |
| 统一报价、管理端积分等 Router | [membership_router.py](../../../apps/backend/app/api/membership_router.py) |
| 用户与设备安全 Router | [users/router.py](../../../apps/backend/app/domains/users/router.py) |
| 订单/报价字段 | [orders/schemas.py](../../../apps/backend/app/domains/orders/schemas.py) |
| 履约/支付/退款/评价字段 | [lifecycle/schemas.py](../../../apps/backend/app/domains/lifecycle/schemas.py) |
| 会员/双钱包/佣金/提现字段 | [distribution/schemas.py](../../../apps/backend/app/domains/distribution/schemas.py) |
| 支付 unavailable、退款资格与审核、收货/评价校验 | [payment_lifecycle.py](../../../apps/backend/app/services/payment_lifecycle.py) |
| 购物车版本与数量校验 | [cart.py](../../../apps/backend/app/services/cart.py) |
| 地址数量、版本与默认替补 | [addresses/service.py](../../../apps/backend/app/domains/addresses/service.py) |
| 提现冻结、欠款约束与人工确认 | [distribution/service.py](../../../apps/backend/app/domains/distribution/service.py) |
| 状态硬约束 | [订单模型](../../../apps/backend/app/db/models/order.py)、[生命周期模型](../../../apps/backend/app/db/models/commerce_lifecycle.py)、[分销模型](../../../apps/backend/app/db/models/distribution.py) |

## 交互表现与验证边界

图片覆盖页面首屏、弹层打开、已选/禁用规格、删除确认、数量与版本冲突、报价变化、提交中、结果未知、失败后保留输入及适用的初次加载/空态/未登录。每张图的具体限制见图片图集的“接口与设计边界”。

图片只能呈现一个状态，不能演示动画、点击、键盘、滚动、手势、请求结果或账户隔离。生成前检查画布布局，生成后核对图片解码与尺寸、每个引用方法/路径存在于根契约，并人工检查分组总览；这些辅助检查不等于应用测试、浏览器验证或微信真机验收。

设计图交付时未初始化工程；随后用户授权直接实现公开浏览，工程和分类筛选已落地，见[工程与公开浏览计划](../../../plans/2026-10-09_小程序工程与公开浏览接入计划.md)。静态图中的其他目标入口不授权新增产品能力，私有流程继续按 PRD、需求基线和专项计划实施。
