# 小程序全页面设计目录 V2

共 188 张独立页面、弹层和状态图；所有内容为设计示例，扩展流程待评审。

离线浏览全部图片：[图片图集](gallery-v2.html)。能力分层与源码证据见[接口映射说明](api-coverage.md)。本目录是图片索引，不定义 API/DTO。

## 浏览与商品

| 编号 | 页面/状态 | 图片 | 能力边界 |
| --- | --- | --- | --- |
| 001 | 首页 | [查看图片](screenshots/v2/01-browse/001-home.png) | 已有消费端接口，仍需微信会话适配 |
| 002 | 分类 | [查看图片](screenshots/v2/01-browse/002-category.png) | 已有领域能力，页面展示或查询契约待补齐 |
| 003 | 分类商品列表 | [查看图片](screenshots/v2/01-browse/003-subcategory.png) | 已有领域能力，页面展示或查询契约待补齐 |
| 004 | 商品详情 | [查看图片](screenshots/v2/01-browse/004-product.png) | 已有消费端接口，仍需微信会话适配 |
| 005 | 详情说明与图集 | [查看图片](screenshots/v2/01-browse/005-product-content.png) | 已有领域能力，页面展示或查询契约待补齐 |
| 006 | 选择规格：加入购物车 | [查看图片](screenshots/v2/01-browse/006-sku-add.png) | 已有消费端接口，仍需微信会话适配 |
| 007 | 选择规格：立即购买 | [查看图片](screenshots/v2/01-browse/007-sku-buy.png) | 已有消费端接口，仍需微信会话适配 |
| 008 | 规格无库存反馈 | [查看图片](screenshots/v2/01-browse/008-sku-unavailable.png) | 已有领域能力，页面展示或查询契约待补齐 |
| 009 | 商品图片预览 | [查看图片](screenshots/v2/01-browse/009-image-preview.png) | 本地交互或静态说明，无独立业务 API |
| 010 | 虚拟商品详情 | [查看图片](screenshots/v2/01-browse/010-product-virtual.png) | 已有消费端接口，仍需微信会话适配 |
| 011 | 商品已下架或不存在 | [查看图片](screenshots/v2/01-browse/011-product-unavailable.png) | 已有消费端接口，仍需微信会话适配 |
| 012 | 会员报价说明 | [查看图片](screenshots/v2/01-browse/012-product-price.png) | 已有消费端接口，仍需微信会话适配 |

分组总览：

- [总览 01-browse-board-01](screenshots/v2/01-browse-board-01.png)
- [总览 01-browse-board-02](screenshots/v2/01-browse-board-02.png)

## 购物车与结算

| 编号 | 页面/状态 | 图片 | 能力边界 |
| --- | --- | --- | --- |
| 013 | 购物车 | [查看图片](screenshots/v2/02-purchase/013-cart.png) | 已有领域能力，页面展示或查询契约待补齐 |
| 014 | 购物车管理 | [查看图片](screenshots/v2/02-purchase/014-cart-edit.png) | 已有领域能力，页面展示或查询契约待补齐 |
| 015 | 购物车失效商品 | [查看图片](screenshots/v2/02-purchase/015-cart-invalid.png) | 已有领域能力，页面展示或查询契约待补齐 |
| 016 | 购物车版本冲突 | [查看图片](screenshots/v2/02-purchase/016-cart-conflict.png) | 已有消费端接口，仍需微信会话适配 |
| 017 | 删除购物车条目 | [查看图片](screenshots/v2/02-purchase/017-cart-remove.png) | 已有消费端接口，仍需微信会话适配 |
| 018 | 加购成功但刷新失败 | [查看图片](screenshots/v2/02-purchase/018-cart-added-refresh-error.png) | 已有消费端接口，仍需微信会话适配 |
| 019 | 实物商品结算 | [查看图片](screenshots/v2/02-purchase/019-checkout-physical.png) | 已有消费端接口，仍需微信会话适配 |
| 020 | 虚拟商品结算 | [查看图片](screenshots/v2/02-purchase/020-checkout-virtual.png) | 已有消费端接口，仍需微信会话适配 |
| 021 | 零应付结算 | [查看图片](screenshots/v2/02-purchase/021-checkout-zero.png) | 已有消费端接口，仍需微信会话适配 |
| 022 | 结算缺少地址 | [查看图片](screenshots/v2/02-purchase/022-checkout-no-address.png) | 已有消费端接口，仍需微信会话适配 |
| 023 | 配送地区不支持 | [查看图片](screenshots/v2/02-purchase/023-checkout-region.png) | 已有消费端接口，仍需微信会话适配 |
| 024 | 混合商品类型拒绝 | [查看图片](screenshots/v2/02-purchase/024-checkout-mixed.png) | 已有消费端接口，仍需微信会话适配 |
| 025 | 报价变化重新确认 | [查看图片](screenshots/v2/02-purchase/025-quote-changed.png) | 已有消费端接口，仍需微信会话适配 |
| 026 | 下单提交中 | [查看图片](screenshots/v2/02-purchase/026-checkout-submitting.png) | 已有消费端接口，仍需微信会话适配 |
| 027 | 下单结果确认中 | [查看图片](screenshots/v2/02-purchase/027-order-create-unknown.png) | 已有领域能力，页面展示或查询契约待补齐 |

分组总览：

- [总览 02-purchase-board-01](screenshots/v2/02-purchase-board-01.png)
- [总览 02-purchase-board-02](screenshots/v2/02-purchase-board-02.png)
- [总览 02-purchase-board-03](screenshots/v2/02-purchase-board-03.png)

## 订单、支付与履约

| 编号 | 页面/状态 | 图片 | 能力边界 |
| --- | --- | --- | --- |
| 028 | 我的订单 | [查看图片](screenshots/v2/03-orders/028-orders-list.png) | PRD 目标流程，当前消费端能力未接通 |
| 029 | 待付款订单 | [查看图片](screenshots/v2/03-orders/029-order-pending.png) | 已有消费端接口，仍需微信会话适配 |
| 030 | 已付款待发货 | [查看图片](screenshots/v2/03-orders/030-order-paid.png) | 已有消费端接口，仍需微信会话适配 |
| 031 | 待收货订单 | [查看图片](screenshots/v2/03-orders/031-order-shipped.png) | 已有消费端接口，仍需微信会话适配 |
| 032 | 已完成订单 | [查看图片](screenshots/v2/03-orders/032-order-delivered.png) | 已有消费端接口，仍需微信会话适配 |
| 033 | 已取消订单 | [查看图片](screenshots/v2/03-orders/033-order-cancelled.png) | 已有消费端接口，仍需微信会话适配 |
| 034 | 零元内部成交订单 | [查看图片](screenshots/v2/03-orders/034-order-zero.png) | 已有消费端接口，仍需微信会话适配 |
| 035 | 虚拟订单已交付 | [查看图片](screenshots/v2/03-orders/035-order-virtual.png) | 已有消费端接口，仍需微信会话适配 |
| 036 | 订单快照与收货信息 | [查看图片](screenshots/v2/03-orders/036-order-snapshot.png) | 已有消费端接口，仍需微信会话适配 |
| 037 | 取消订单确认 | [查看图片](screenshots/v2/03-orders/037-order-cancel.png) | 已有消费端接口，仍需微信会话适配 |
| 038 | 订单支付时限提示 | [查看图片](screenshots/v2/03-orders/038-order-expiry.png) | 已有消费端接口，仍需微信会话适配 |
| 039 | 支付渠道未开放 | [查看图片](screenshots/v2/03-orders/039-payment-unavailable.png) | 当前不可用状态或渠道接入前的限制 |
| 040 | 付款结果确认中 | [查看图片](screenshots/v2/03-orders/040-payment-confirming.png) | PRD 目标流程，当前消费端能力未接通 |
| 041 | 已确认付款成功 | [查看图片](screenshots/v2/03-orders/041-payment-success.png) | PRD 目标流程，当前消费端能力未接通 |
| 042 | 支付弹窗已关闭 | [查看图片](screenshots/v2/03-orders/042-payment-cancelled.png) | PRD 目标流程，当前消费端能力未接通 |
| 043 | 取消后收到付款异常 | [查看图片](screenshots/v2/03-orders/043-payment-late.png) | PRD 目标流程，当前消费端能力未接通 |
| 044 | 发货信息 | [查看图片](screenshots/v2/03-orders/044-fulfillment-physical.png) | 已有消费端接口，仍需微信会话适配 |
| 045 | 虚拟交付信息 | [查看图片](screenshots/v2/03-orders/045-fulfillment-virtual.png) | 已有消费端接口，仍需微信会话适配 |
| 046 | 确认收货弹窗 | [查看图片](screenshots/v2/03-orders/046-confirm-receipt.png) | 已有消费端接口，仍需微信会话适配 |
| 047 | 确认收货状态冲突 | [查看图片](screenshots/v2/03-orders/047-receipt-conflict.png) | 已有消费端接口，仍需微信会话适配 |

分组总览：

- [总览 03-orders-board-01](screenshots/v2/03-orders-board-01.png)
- [总览 03-orders-board-02](screenshots/v2/03-orders-board-02.png)
- [总览 03-orders-board-03](screenshots/v2/03-orders-board-03.png)
- [总览 03-orders-board-04](screenshots/v2/03-orders-board-04.png)

## 售后与评价

| 编号 | 页面/状态 | 图片 | 能力边界 |
| --- | --- | --- | --- |
| 048 | 整单退款申请 | [查看图片](screenshots/v2/04-aftercare/048-refund-form.png) | 已有消费端接口，仍需微信会话适配 |
| 049 | 未接单退款自动审核 | [查看图片](screenshots/v2/04-aftercare/049-refund-automatic.png) | 已有消费端接口，仍需微信会话适配 |
| 050 | 退款申请校验失败 | [查看图片](screenshots/v2/04-aftercare/050-refund-form-rejected.png) | 已有消费端接口，仍需微信会话适配 |
| 051 | 退款待审核 | [查看图片](screenshots/v2/04-aftercare/051-refund-review.png) | 已有消费端接口，仍需微信会话适配 |
| 052 | 审核通过退款处理中 | [查看图片](screenshots/v2/04-aftercare/052-refund-approved.png) | 已有消费端接口，仍需微信会话适配 |
| 053 | 退款审核未通过 | [查看图片](screenshots/v2/04-aftercare/053-refund-rejected.png) | 已有消费端接口，仍需微信会话适配 |
| 054 | 退款已完成 | [查看图片](screenshots/v2/04-aftercare/054-refund-completed.png) | 已有消费端接口，仍需微信会话适配 |
| 055 | 退款资金结果未知 | [查看图片](screenshots/v2/04-aftercare/055-refund-unknown.png) | PRD 目标流程，当前消费端能力未接通 |
| 056 | 已发货不可申请退款 | [查看图片](screenshots/v2/04-aftercare/056-refund-ineligible.png) | 已有消费端接口，仍需微信会话适配 |
| 057 | 本单售后记录 | [查看图片](screenshots/v2/04-aftercare/057-refund-history.png) | 已有消费端接口，仍需微信会话适配 |
| 058 | 商品评价列表 | [查看图片](screenshots/v2/04-aftercare/058-reviews.png) | 已有消费端接口，仍需微信会话适配 |
| 059 | 评价已交付商品 | [查看图片](screenshots/v2/04-aftercare/059-review-form.png) | 已有消费端接口，仍需微信会话适配 |
| 060 | 评价提交成功 | [查看图片](screenshots/v2/04-aftercare/060-review-success.png) | 已有消费端接口，仍需微信会话适配 |
| 061 | 评价资格不满足 | [查看图片](screenshots/v2/04-aftercare/061-review-denied.png) | 已有消费端接口，仍需微信会话适配 |

分组总览：

- [总览 04-aftercare-board-01](screenshots/v2/04-aftercare-board-01.png)
- [总览 04-aftercare-board-02](screenshots/v2/04-aftercare-board-02.png)
- [总览 04-aftercare-board-03](screenshots/v2/04-aftercare-board-03.png)

## 个人中心、身份与设置

| 编号 | 页面/状态 | 图片 | 能力边界 |
| --- | --- | --- | --- |
| 062 | 个人中心 | [查看图片](screenshots/v2/05-account/062-mine.png) | 已有领域能力，页面展示或查询契约待补齐 |
| 063 | 未登录个人中心 | [查看图片](screenshots/v2/05-account/063-mine-guest.png) | 已有消费端接口，仍需微信会话适配 |
| 064 | 微信登录与协议确认 | [查看图片](screenshots/v2/05-account/064-wechat-login.png) | PRD 目标流程，当前消费端能力未接通 |
| 065 | 登录取消保留浏览 | [查看图片](screenshots/v2/05-account/065-login-cancelled.png) | 本地交互或静态说明，无独立业务 API |
| 066 | 个人资料 | [查看图片](screenshots/v2/05-account/066-profile.png) | 已有消费端接口，仍需微信会话适配 |
| 067 | 修改昵称与邮箱 | [查看图片](screenshots/v2/05-account/067-profile-edit.png) | 已有消费端接口，仍需微信会话适配 |
| 068 | 头像操作弹层 | [查看图片](screenshots/v2/05-account/068-avatar-actions.png) | 已有消费端接口，仍需微信会话适配 |
| 069 | 头像上传保存中 | [查看图片](screenshots/v2/05-account/069-avatar-submitting.png) | 已有消费端接口，仍需微信会话适配 |
| 070 | 设置 | [查看图片](screenshots/v2/05-account/070-settings.png) | 已有消费端接口，仍需微信会话适配 |
| 071 | 账号安全 | [查看图片](screenshots/v2/05-account/071-security.png) | 已有领域能力，页面展示或查询契约待补齐 |
| 072 | 登录设备 | [查看图片](screenshots/v2/05-account/072-sessions.png) | 已有领域能力，页面展示或查询契约待补齐 |
| 073 | 退出其他设备确认 | [查看图片](screenshots/v2/05-account/073-session-revoke.png) | 已有消费端接口，仍需微信会话适配 |
| 074 | 已有密码账户修改密码 | [查看图片](screenshots/v2/05-account/074-password.png) | 已有领域能力，页面展示或查询契约待补齐 |
| 075 | 退出登录确认 | [查看图片](screenshots/v2/05-account/075-logout.png) | 已有消费端接口，仍需微信会话适配 |
| 076 | 注销账户说明 | [查看图片](screenshots/v2/05-account/076-account-delete.png) | 已有领域能力，页面展示或查询契约待补齐 |
| 077 | 账户停用反馈 | [查看图片](screenshots/v2/05-account/077-account-disabled.png) | 已有消费端接口，仍需微信会话适配 |

分组总览：

- [总览 05-account-board-01](screenshots/v2/05-account-board-01.png)
- [总览 05-account-board-02](screenshots/v2/05-account-board-02.png)
- [总览 05-account-board-03](screenshots/v2/05-account-board-03.png)

## 收货地址

| 编号 | 页面/状态 | 图片 | 能力边界 |
| --- | --- | --- | --- |
| 078 | 收货地址管理 | [查看图片](screenshots/v2/06-address/078-addresses.png) | 已有消费端接口，仍需微信会话适配 |
| 079 | 选择收货地址 | [查看图片](screenshots/v2/06-address/079-address-select.png) | 已有消费端接口，仍需微信会话适配 |
| 080 | 新增收货地址 | [查看图片](screenshots/v2/06-address/080-address-add.png) | 已有消费端接口，仍需微信会话适配 |
| 081 | 编辑收货地址 | [查看图片](screenshots/v2/06-address/081-address-edit.png) | 已有消费端接口，仍需微信会话适配 |
| 082 | 省市区选择 | [查看图片](screenshots/v2/06-address/082-address-region.png) | 已有领域能力，页面展示或查询契约待补齐 |
| 083 | 删除地址确认 | [查看图片](screenshots/v2/06-address/083-address-delete.png) | 已有消费端接口，仍需微信会话适配 |
| 084 | 地址版本冲突 | [查看图片](screenshots/v2/06-address/084-address-conflict.png) | 已有消费端接口，仍需微信会话适配 |
| 085 | 收货地址数量上限 | [查看图片](screenshots/v2/06-address/085-address-limit.png) | 已有消费端接口，仍需微信会话适配 |
| 086 | 地址表单校验 | [查看图片](screenshots/v2/06-address/086-address-validation.png) | 已有消费端接口，仍需微信会话适配 |

分组总览：

- [总览 06-address-board-01](screenshots/v2/06-address-board-01.png)
- [总览 06-address-board-02](screenshots/v2/06-address-board-02.png)

## 会员、推荐与积分

| 编号 | 页面/状态 | 图片 | 能力边界 |
| --- | --- | --- | --- |
| 087 | 会员与分销档案 | [查看图片](screenshots/v2/07-member/087-membership.png) | 已有领域能力，页面展示或查询契约待补齐 |
| 088 | 开通分销档案 | [查看图片](screenshots/v2/07-member/088-membership-open.png) | 已有消费端接口，仍需微信会话适配 |
| 089 | 会员等级停用 | [查看图片](screenshots/v2/07-member/089-membership-disabled.png) | 已有消费端接口，仍需微信会话适配 |
| 090 | 首次绑定推荐人 | [查看图片](screenshots/v2/07-member/090-referrer-bind.png) | 已有消费端接口，仍需微信会话适配 |
| 091 | 推荐绑定确认弹窗 | [查看图片](screenshots/v2/07-member/091-referrer-confirm.png) | 已有消费端接口，仍需微信会话适配 |
| 092 | 已绑定推荐关系 | [查看图片](screenshots/v2/07-member/092-referrer-bound.png) | 已有消费端接口，仍需微信会话适配 |
| 093 | 邀请码失效或绑定拒绝 | [查看图片](screenshots/v2/07-member/093-referrer-invalid.png) | 已有消费端接口，仍需微信会话适配 |
| 094 | 分享邀请说明 | [查看图片](screenshots/v2/07-member/094-invite-share.png) | PRD 目标流程，当前消费端能力未接通 |
| 095 | 积分账户接入前 | [查看图片](screenshots/v2/07-member/095-points.png) | 当前不可用状态或渠道接入前的限制 |

分组总览：

- [总览 07-member-board-01](screenshots/v2/07-member-board-01.png)
- [总览 07-member-board-02](screenshots/v2/07-member-board-02.png)

## 钱包、佣金与提现

| 编号 | 页面/状态 | 图片 | 能力边界 |
| --- | --- | --- | --- |
| 096 | 我的钱包 | [查看图片](screenshots/v2/08-wallet/096-wallets.png) | 已有消费端接口，仍需微信会话适配 |
| 097 | 佣金钱包 | [查看图片](screenshots/v2/08-wallet/097-wallet-commission.png) | 已有消费端接口，仍需微信会话适配 |
| 098 | 消费钱包 | [查看图片](screenshots/v2/08-wallet/098-wallet-consumption.png) | 已有消费端接口，仍需微信会话适配 |
| 099 | 钱包欠款限制 | [查看图片](screenshots/v2/08-wallet/099-wallet-debt.png) | 已有消费端接口，仍需微信会话适配 |
| 100 | 佣金记录 | [查看图片](screenshots/v2/08-wallet/100-commissions.png) | 已有消费端接口，仍需微信会话适配 |
| 101 | 冻结佣金详情 | [查看图片](screenshots/v2/08-wallet/101-commission-frozen.png) | 已有消费端接口，仍需微信会话适配 |
| 102 | 已结算佣金详情 | [查看图片](screenshots/v2/08-wallet/102-commission-settled.png) | 已有消费端接口，仍需微信会话适配 |
| 103 | 已追回佣金详情 | [查看图片](screenshots/v2/08-wallet/103-commission-recovered.png) | 已有消费端接口，仍需微信会话适配 |
| 104 | 提现申请预备页 | [查看图片](screenshots/v2/08-wallet/104-withdrawal-form.png) | 当前不可用状态或渠道接入前的限制 |
| 105 | 提现记录 | [查看图片](screenshots/v2/08-wallet/105-withdrawal-records.png) | 已有消费端接口，仍需微信会话适配 |
| 106 | 提现待审核 | [查看图片](screenshots/v2/08-wallet/106-withdrawal-review.png) | 已有消费端接口，仍需微信会话适配 |
| 107 | 提现审核通过 | [查看图片](screenshots/v2/08-wallet/107-withdrawal-approved.png) | 已有消费端接口，仍需微信会话适配 |
| 108 | 提现审核未通过 | [查看图片](screenshots/v2/08-wallet/108-withdrawal-rejected.png) | 已有消费端接口，仍需微信会话适配 |
| 109 | 提现执行处理中 | [查看图片](screenshots/v2/08-wallet/109-withdrawal-processing.png) | PRD 目标流程，当前消费端能力未接通 |
| 110 | 提现结果未知 | [查看图片](screenshots/v2/08-wallet/110-withdrawal-unknown.png) | PRD 目标流程，当前消费端能力未接通 |
| 111 | 提现确认完成 | [查看图片](screenshots/v2/08-wallet/111-withdrawal-completed.png) | 已有消费端接口，仍需微信会话适配 |
| 112 | 提现余额不足或欠款 | [查看图片](screenshots/v2/08-wallet/112-withdrawal-balance.png) | 已有消费端接口，仍需微信会话适配 |
| 113 | 钱包流水接入前 | [查看图片](screenshots/v2/08-wallet/113-wallet-ledger-unavailable.png) | 当前不可用状态或渠道接入前的限制 |

分组总览：

- [总览 08-wallet-board-01](screenshots/v2/08-wallet-board-01.png)
- [总览 08-wallet-board-02](screenshots/v2/08-wallet-board-02.png)
- [总览 08-wallet-board-03](screenshots/v2/08-wallet-board-03.png)

## 帮助、隐私与服务

| 编号 | 页面/状态 | 图片 | 能力边界 |
| --- | --- | --- | --- |
| 114 | 帮助与售后 | [查看图片](screenshots/v2/09-service/114-help.png) | 本地交互或静态说明，无独立业务 API |
| 115 | 退款规则说明 | [查看图片](screenshots/v2/09-service/115-help-refund.png) | 本地交互或静态说明，无独立业务 API |
| 116 | 联系售后 | [查看图片](screenshots/v2/09-service/116-contact.png) | 当前不可用状态或渠道接入前的限制 |
| 117 | 隐私说明草案 | [查看图片](screenshots/v2/09-service/117-privacy.png) | 本地交互或静态说明，无独立业务 API |
| 118 | 服务协议草案 | [查看图片](screenshots/v2/09-service/118-terms.png) | 本地交互或静态说明，无独立业务 API |
| 119 | 关于商城 | [查看图片](screenshots/v2/09-service/119-about.png) | 已有领域能力，页面展示或查询契约待补齐 |
| 120 | 头像权限拒绝 | [查看图片](screenshots/v2/09-service/120-permission-photo.png) | 本地交互或静态说明，无独立业务 API |
| 121 | 服务暂时不可用 | [查看图片](screenshots/v2/09-service/121-service-unavailable.png) | 已有消费端接口，仍需微信会话适配 |
| 122 | 请求过于频繁 | [查看图片](screenshots/v2/09-service/122-rate-limited.png) | 本地交互或静态说明，无独立业务 API |
| 123 | 商品图片加载失败 | [查看图片](screenshots/v2/09-service/123-image-error.png) | 已有消费端接口，仍需微信会话适配 |
| 124 | 断网恢复提示 | [查看图片](screenshots/v2/09-service/124-offline.png) | 本地交互或静态说明，无独立业务 API |
| 125 | 登录恢复失败 | [查看图片](screenshots/v2/09-service/125-session-expired.png) | 已有消费端接口，仍需微信会话适配 |
| 126 | 已有内容刷新失败 | [查看图片](screenshots/v2/09-service/126-refresh-error.png) | 已有消费端接口，仍需微信会话适配 |
| 127 | 小程序更新提示 | [查看图片](screenshots/v2/09-service/127-update-prompt.png) | 本地交互或静态说明，无独立业务 API |

分组总览：

- [总览 09-service-board-01](screenshots/v2/09-service-board-01.png)
- [总览 09-service-board-02](screenshots/v2/09-service-board-02.png)
- [总览 09-service-board-03](screenshots/v2/09-service-board-03.png)

## 通用加载、空态与异常

| 编号 | 页面/状态 | 图片 | 能力边界 |
| --- | --- | --- | --- |
| 128 | 首页：首次加载 | [查看图片](screenshots/v2/10-states/128-home-loading.png) | 已有消费端接口，仍需微信会话适配 |
| 129 | 首页：查询失败 | [查看图片](screenshots/v2/10-states/129-home-error.png) | 已有消费端接口，仍需微信会话适配 |
| 130 | 首页：无数据 | [查看图片](screenshots/v2/10-states/130-home-empty.png) | 已有消费端接口，仍需微信会话适配 |
| 131 | 分类：首次加载 | [查看图片](screenshots/v2/10-states/131-category-loading.png) | 已有领域能力，页面展示或查询契约待补齐 |
| 132 | 分类：查询失败 | [查看图片](screenshots/v2/10-states/132-category-error.png) | 已有领域能力，页面展示或查询契约待补齐 |
| 133 | 分类：无数据 | [查看图片](screenshots/v2/10-states/133-category-empty.png) | 已有领域能力，页面展示或查询契约待补齐 |
| 134 | 商品详情：首次加载 | [查看图片](screenshots/v2/10-states/134-product-loading.png) | 已有消费端接口，仍需微信会话适配 |
| 135 | 商品详情：查询失败 | [查看图片](screenshots/v2/10-states/135-product-error.png) | 已有消费端接口，仍需微信会话适配 |
| 136 | 商品详情：无数据 | [查看图片](screenshots/v2/10-states/136-product-empty.png) | 已有消费端接口，仍需微信会话适配 |
| 137 | 购物车：首次加载 | [查看图片](screenshots/v2/10-states/137-cart-loading.png) | 已有领域能力，页面展示或查询契约待补齐 |
| 138 | 购物车：查询失败 | [查看图片](screenshots/v2/10-states/138-cart-error.png) | 已有领域能力，页面展示或查询契约待补齐 |
| 139 | 购物车：无数据 | [查看图片](screenshots/v2/10-states/139-cart-empty.png) | 已有领域能力，页面展示或查询契约待补齐 |
| 140 | 购物车：未登录 | [查看图片](screenshots/v2/10-states/140-cart-login.png) | 已有领域能力，页面展示或查询契约待补齐 |
| 141 | 实物商品结算：首次加载 | [查看图片](screenshots/v2/10-states/141-checkout-physical-loading.png) | 已有消费端接口，仍需微信会话适配 |
| 142 | 实物商品结算：查询失败 | [查看图片](screenshots/v2/10-states/142-checkout-physical-error.png) | 已有消费端接口，仍需微信会话适配 |
| 143 | 实物商品结算：未登录 | [查看图片](screenshots/v2/10-states/143-checkout-physical-login.png) | 已有消费端接口，仍需微信会话适配 |
| 144 | 我的订单：首次加载 | [查看图片](screenshots/v2/10-states/144-orders-list-loading.png) | PRD 目标流程，当前消费端能力未接通 |
| 145 | 我的订单：查询失败 | [查看图片](screenshots/v2/10-states/145-orders-list-error.png) | PRD 目标流程，当前消费端能力未接通 |
| 146 | 我的订单：无数据 | [查看图片](screenshots/v2/10-states/146-orders-list-empty.png) | PRD 目标流程，当前消费端能力未接通 |
| 147 | 我的订单：未登录 | [查看图片](screenshots/v2/10-states/147-orders-list-login.png) | PRD 目标流程，当前消费端能力未接通 |
| 148 | 待付款订单：首次加载 | [查看图片](screenshots/v2/10-states/148-order-pending-loading.png) | 已有消费端接口，仍需微信会话适配 |
| 149 | 待付款订单：查询失败 | [查看图片](screenshots/v2/10-states/149-order-pending-error.png) | 已有消费端接口，仍需微信会话适配 |
| 150 | 待付款订单：未登录 | [查看图片](screenshots/v2/10-states/150-order-pending-login.png) | 已有消费端接口，仍需微信会话适配 |
| 151 | 发货信息：首次加载 | [查看图片](screenshots/v2/10-states/151-fulfillment-physical-loading.png) | 已有消费端接口，仍需微信会话适配 |
| 152 | 发货信息：查询失败 | [查看图片](screenshots/v2/10-states/152-fulfillment-physical-error.png) | 已有消费端接口，仍需微信会话适配 |
| 153 | 本单售后记录：首次加载 | [查看图片](screenshots/v2/10-states/153-refund-history-loading.png) | 已有消费端接口，仍需微信会话适配 |
| 154 | 本单售后记录：查询失败 | [查看图片](screenshots/v2/10-states/154-refund-history-error.png) | 已有消费端接口，仍需微信会话适配 |
| 155 | 本单售后记录：无数据 | [查看图片](screenshots/v2/10-states/155-refund-history-empty.png) | 已有消费端接口，仍需微信会话适配 |
| 156 | 本单售后记录：未登录 | [查看图片](screenshots/v2/10-states/156-refund-history-login.png) | 已有消费端接口，仍需微信会话适配 |
| 157 | 商品评价列表：首次加载 | [查看图片](screenshots/v2/10-states/157-reviews-loading.png) | 已有消费端接口，仍需微信会话适配 |
| 158 | 商品评价列表：查询失败 | [查看图片](screenshots/v2/10-states/158-reviews-error.png) | 已有消费端接口，仍需微信会话适配 |
| 159 | 商品评价列表：无数据 | [查看图片](screenshots/v2/10-states/159-reviews-empty.png) | 已有消费端接口，仍需微信会话适配 |
| 160 | 个人中心：首次加载 | [查看图片](screenshots/v2/10-states/160-mine-loading.png) | 已有领域能力，页面展示或查询契约待补齐 |
| 161 | 个人中心：查询失败 | [查看图片](screenshots/v2/10-states/161-mine-error.png) | 已有领域能力，页面展示或查询契约待补齐 |
| 162 | 个人中心：未登录 | [查看图片](screenshots/v2/10-states/162-mine-login.png) | 已有领域能力，页面展示或查询契约待补齐 |
| 163 | 个人资料：首次加载 | [查看图片](screenshots/v2/10-states/163-profile-loading.png) | 已有消费端接口，仍需微信会话适配 |
| 164 | 个人资料：查询失败 | [查看图片](screenshots/v2/10-states/164-profile-error.png) | 已有消费端接口，仍需微信会话适配 |
| 165 | 个人资料：未登录 | [查看图片](screenshots/v2/10-states/165-profile-login.png) | 已有消费端接口，仍需微信会话适配 |
| 166 | 登录设备：首次加载 | [查看图片](screenshots/v2/10-states/166-sessions-loading.png) | 已有领域能力，页面展示或查询契约待补齐 |
| 167 | 登录设备：查询失败 | [查看图片](screenshots/v2/10-states/167-sessions-error.png) | 已有领域能力，页面展示或查询契约待补齐 |
| 168 | 登录设备：无数据 | [查看图片](screenshots/v2/10-states/168-sessions-empty.png) | 已有领域能力，页面展示或查询契约待补齐 |
| 169 | 登录设备：未登录 | [查看图片](screenshots/v2/10-states/169-sessions-login.png) | 已有领域能力，页面展示或查询契约待补齐 |
| 170 | 收货地址管理：首次加载 | [查看图片](screenshots/v2/10-states/170-addresses-loading.png) | 已有消费端接口，仍需微信会话适配 |
| 171 | 收货地址管理：查询失败 | [查看图片](screenshots/v2/10-states/171-addresses-error.png) | 已有消费端接口，仍需微信会话适配 |
| 172 | 收货地址管理：无数据 | [查看图片](screenshots/v2/10-states/172-addresses-empty.png) | 已有消费端接口，仍需微信会话适配 |
| 173 | 收货地址管理：未登录 | [查看图片](screenshots/v2/10-states/173-addresses-login.png) | 已有消费端接口，仍需微信会话适配 |
| 174 | 会员与分销档案：首次加载 | [查看图片](screenshots/v2/10-states/174-membership-loading.png) | 已有领域能力，页面展示或查询契约待补齐 |
| 175 | 会员与分销档案：查询失败 | [查看图片](screenshots/v2/10-states/175-membership-error.png) | 已有领域能力，页面展示或查询契约待补齐 |
| 176 | 会员与分销档案：无数据 | [查看图片](screenshots/v2/10-states/176-membership-empty.png) | 已有领域能力，页面展示或查询契约待补齐 |
| 177 | 会员与分销档案：未登录 | [查看图片](screenshots/v2/10-states/177-membership-login.png) | 已有领域能力，页面展示或查询契约待补齐 |
| 178 | 我的钱包：首次加载 | [查看图片](screenshots/v2/10-states/178-wallets-loading.png) | 已有消费端接口，仍需微信会话适配 |
| 179 | 我的钱包：查询失败 | [查看图片](screenshots/v2/10-states/179-wallets-error.png) | 已有消费端接口，仍需微信会话适配 |
| 180 | 我的钱包：未登录 | [查看图片](screenshots/v2/10-states/180-wallets-login.png) | 已有消费端接口，仍需微信会话适配 |
| 181 | 佣金记录：首次加载 | [查看图片](screenshots/v2/10-states/181-commissions-loading.png) | 已有消费端接口，仍需微信会话适配 |
| 182 | 佣金记录：查询失败 | [查看图片](screenshots/v2/10-states/182-commissions-error.png) | 已有消费端接口，仍需微信会话适配 |
| 183 | 佣金记录：无数据 | [查看图片](screenshots/v2/10-states/183-commissions-empty.png) | 已有消费端接口，仍需微信会话适配 |
| 184 | 佣金记录：未登录 | [查看图片](screenshots/v2/10-states/184-commissions-login.png) | 已有消费端接口，仍需微信会话适配 |
| 185 | 提现记录：首次加载 | [查看图片](screenshots/v2/10-states/185-withdrawal-records-loading.png) | 已有消费端接口，仍需微信会话适配 |
| 186 | 提现记录：查询失败 | [查看图片](screenshots/v2/10-states/186-withdrawal-records-error.png) | 已有消费端接口，仍需微信会话适配 |
| 187 | 提现记录：无数据 | [查看图片](screenshots/v2/10-states/187-withdrawal-records-empty.png) | 已有消费端接口，仍需微信会话适配 |
| 188 | 提现记录：未登录 | [查看图片](screenshots/v2/10-states/188-withdrawal-records-login.png) | 已有消费端接口，仍需微信会话适配 |

分组总览：

- [总览 10-states-board-01](screenshots/v2/10-states-board-01.png)
- [总览 10-states-board-02](screenshots/v2/10-states-board-02.png)
- [总览 10-states-board-03](screenshots/v2/10-states-board-03.png)
- [总览 10-states-board-04](screenshots/v2/10-states-board-04.png)
- [总览 10-states-board-05](screenshots/v2/10-states-board-05.png)
- [总览 10-states-board-06](screenshots/v2/10-states-board-06.png)
- [总览 10-states-board-07](screenshots/v2/10-states-board-07.png)
- [总览 10-states-board-08](screenshots/v2/10-states-board-08.png)
- [总览 10-states-board-09](screenshots/v2/10-states-board-09.png)
- [总览 10-states-board-10](screenshots/v2/10-states-board-10.png)
- [总览 10-states-board-11](screenshots/v2/10-states-board-11.png)
