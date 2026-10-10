"""Render versioned miniapp design images and a local image gallery.

Reads only the existing OpenAPI file to check cited routes. No application runs.
"""

import argparse
import html
import json
import os
from pathlib import Path

from PIL import Image, ImageDraw

import render_mockups as ui


ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
PAGES = []
API = {
    'catalog': ['GET /api/v1/product-categories', 'GET /api/v1/products'],
    'product': ['GET /api/v1/products/{product_id}'],
    'review': ['GET /api/v1/products/{product_id}/reviews', 'POST /api/v1/order-items/{order_item_id}/review'],
    'cart': ['GET /api/v1/cart-items', 'POST /api/v1/cart-items', 'PATCH /api/v1/cart-items/{item_id}', 'DELETE /api/v1/cart-items/{item_id}'],
    'checkout': ['POST /api/v1/checkout/preview', 'POST /api/v1/orders', 'POST /api/v1/commerce/quotes'],
    'address': ['GET /api/v1/addresses', 'POST /api/v1/addresses', 'PUT /api/v1/addresses/{address_id}', 'DELETE /api/v1/addresses/{address_id}'],
    'order': ['GET /api/v1/orders/{order_id}', 'POST /api/v1/orders/{order_id}/cancel'],
    'payment': ['POST /api/v1/orders/{order_id}/payment-attempts'],
    'fulfillment': ['GET /api/v1/orders/{order_id}/fulfillment', 'POST /api/v1/orders/{order_id}/fulfillment/confirm-receipt'],
    'refund': ['GET /api/v1/refunds', 'POST /api/v1/orders/{order_id}/refunds'],
    'user': ['GET /api/v1/users/me', 'PATCH /api/v1/users/me', 'PUT /api/v1/users/me/avatar'],
    'auth': ['POST /api/v1/auth/logout', 'POST /api/v1/auth/refresh'],
    'security': ['GET /api/v1/users/me/sessions', 'POST /api/v1/users/me/sessions/revoke', 'POST /api/v1/users/me/sessions/revocation-status', 'GET /api/v1/users/me/closure-precheck'],
    'member': ['GET /api/v1/distribution/me/profile', 'POST /api/v1/distribution/me/profile'],
    'referrer': ['POST /api/v1/distribution/me/referrer', 'GET /api/v1/distribution/me/profile'],
    'commission': ['GET /api/v1/distribution/me/commissions'],
    'wallet': ['GET /api/v1/distribution/me/wallets'],
    'withdrawal': ['GET /api/v1/distribution/me/withdrawals'],
    'system': ['GET /api/v1/system/site-profile', 'GET /api/v1/system/status'],
}
GROUPS = {
    '01-browse': '浏览与商品', '02-purchase': '购物车与结算',
    '03-orders': '订单、支付与履约', '04-aftercare': '售后与评价',
    '05-account': '个人中心、身份与设置', '06-address': '收货地址',
    '07-member': '会员、推荐与积分', '08-wallet': '钱包、佣金与提现',
    '09-service': '帮助、隐私与服务', '10-states': '通用加载、空态与异常',
}
STATUS = {
    'existing': '已有消费端接口，仍需微信会话适配',
    'gap': '已有领域能力，页面展示或查询契约待补齐',
    'target': 'PRD 目标流程，当前消费端能力未接通',
    'unavailable': '当前不可用状态或渠道接入前的限制',
    'local': '本地交互或静态说明，无独立业务 API',
}


def add(group, slug, title, kind, api='', status='existing', note='', **data):
    page = dict(group=group, slug=slug, title=title, kind=kind,
                api=API.get(api, []), status=status, note=note, data=data)
    PAGES.append(page)
    return page


def configure():
    g = '01-browse'
    add(g, 'home', '首页', 'home', 'catalog', note='公开浏览；不添加搜索、优惠券或装修轮播。')
    add(g, 'category', '分类', 'category', 'catalog', 'gap', '分类存在；商品列表只有 page/page_size，按分类过滤待后端扩展。')
    add(g, 'subcategory', '分类商品列表', 'category', 'catalog', 'gap', '三级分类与图标展示；不能用当前页过滤冒充完整分类结果。', sub=True)
    add(g, 'product', '商品详情', 'product', 'product', note='基础价格、规格、主图已有；富文本内容边界待完成。')
    add(g, 'product-content', '详情说明与图集', 'content', 'product', 'gap', '复用 description/detail_images/attributes；受限 HTML 净化仍需后端落实。')
    add(g, 'sku-add', '选择规格：加入购物车', 'sku', 'cart')
    add(g, 'sku-buy', '选择规格：立即购买', 'sku', 'checkout', action='确认并进入结算')
    add(g, 'sku-unavailable', '规格无库存反馈', 'sku', 'cart', 'gap', '公开 SKU 不含可用库存；数量校验错误已存在，展示原因需补齐。', warning='当前规格库存不足，请重新选择')
    add(g, 'image-preview', '商品图片预览', 'image', 'product', 'local', '点击主图或详情切片使用微信原生预览；关闭返回原位置。')
    add(g, 'product-virtual', '虚拟商品详情', 'virtual', 'product', note='虚拟商品不索取配送地址；交付事实经 fulfillment 查询。')
    add(g, 'product-unavailable', '商品已下架或不存在', 'result', 'product', title_line='商品暂时无法浏览', message='商品可能已下架或不存在。\n你可以返回商城继续浏览。', action='返回商城', mood='neutral')
    add(g, 'product-price', '会员报价说明', 'info', 'checkout', 'existing', '报价由后端返回，不能按等级自行计算折扣。', rows=[('参考价格', '¥129.00'), ('当前适用单价', '¥119.00'), ('适用数量', '1 件'), ('报价来源', '服务端当前结果')], body='商品详情价格用于参考，结算将重新报价。\n等级、数量或配送地区变化后需刷新报价。')

    g = '02-purchase'
    add(g, 'cart', '购物车', 'cart', 'cart', 'gap', 'quantity/selected/revision 已有；商品缩略图、名称和失效原因需有界查询视图。')
    add(g, 'cart-edit', '购物车管理', 'cart', 'cart', 'gap', '只存在单条删除；设计使用单条确认，不伪造批量删除 API。', edit=True)
    add(g, 'cart-invalid', '购物车失效商品', 'cart', 'cart', 'gap', invalid=True)
    add(g, 'cart-conflict', '购物车版本冲突', 'dialog', 'cart', base='cart', heading='购物车已变更', body='此条目已在其他设备更新。\n请读取最新数量，再确认你的选择。', confirm='刷新购物车')
    add(g, 'cart-remove', '删除购物车条目', 'dialog', 'cart', base='cart', heading='删除这件商品？', body='将从购物车移除基础圆领短袖。\n不会修改已创建的订单。', confirm='确认删除', danger=True)
    add(g, 'cart-added-refresh-error', '加购成功但刷新失败', 'result', 'cart', title_line='已加入，购物车刷新失败', message='本次加购已完成，请勿重复加入。\n可以刷新购物车查看最新条目。', action='刷新购物车', mood='warning')
    add(g, 'checkout-physical', '实物商品结算', 'checkout', 'checkout', note='商品金额 ¥129.00、运费 ¥8.00、应付 ¥137.00 均为示例报价。')
    add(g, 'checkout-virtual', '虚拟商品结算', 'checkout', 'checkout', virtual=True)
    add(g, 'checkout-zero', '零应付结算', 'checkout', 'checkout', zero=True)
    add(g, 'checkout-no-address', '结算缺少地址', 'checkout', 'checkout', no_address=True)
    add(g, 'checkout-region', '配送地区不支持', 'checkout', 'checkout', warning='该地址暂不支持配送，请更换地址', blocked=True)
    add(g, 'checkout-mixed', '混合商品类型拒绝', 'result', 'checkout', title_line='请分开结算', message='实物与虚拟商品不能混合下单。\n请返回购物车分别选择商品。', action='返回购物车', mood='warning')
    add(g, 'quote-changed', '报价变化重新确认', 'dialog', 'checkout', base='checkout', heading='报价已更新', body='原应付 ¥137.00 → 新应付 ¥139.00\n请查看最新报价后重新确认。\n取消不会提交订单。', confirm='查看最新报价')
    add(g, 'checkout-submitting', '下单提交中', 'checkout', 'checkout', busy=True)
    add(g, 'order-create-unknown', '下单结果确认中', 'result', 'checkout', 'gap', 'request_id 已有，未知结果确认查询或安全同键恢复契约仍需专项。', title_line='订单结果确认中', message='本次提交的结果尚未确认。\n请保留当前操作，不要再次下单。', action='查询本次结果', mood='warning')

    g = '03-orders'
    add(g, 'orders-list', '我的订单', 'orders-list', 'order', 'target', '当前只存在本人单笔订单查询；分页、状态筛选与总数待实现，不调用 Admin 列表。')
    add(g, 'order-pending', '待付款订单', 'order', 'order', state='pending')
    add(g, 'order-paid', '已付款待发货', 'order', 'fulfillment', state='paid')
    add(g, 'order-shipped', '待收货订单', 'order', 'fulfillment', state='shipped')
    add(g, 'order-delivered', '已完成订单', 'order', 'fulfillment', state='delivered')
    add(g, 'order-cancelled', '已取消订单', 'order', 'order', state='cancelled')
    add(g, 'order-zero', '零元内部成交订单', 'order', 'order', state='zero')
    add(g, 'order-virtual', '虚拟订单已交付', 'order', 'fulfillment', state='virtual')
    add(g, 'order-snapshot', '订单快照与收货信息', 'info', 'order', rows=[('订单商品', '基础圆领短袖 ×1'), ('成交规格', '白色 / M'), ('收件人', '示例收件人'), ('联系电话', '138****0000'), ('收货地区', '示例省 / 示例市 / 示例区')], body='收货地址：示例路 1 号。\n商品和地址后续变更不会改变本笔订单快照。')
    add(g, 'order-cancel', '取消订单确认', 'dialog', 'order', base='order', heading='取消这笔订单？', body='确认后由服务端取消待付款订单。\n支付结果未确认时可能无法取消。', confirm='确认取消', danger=True)
    add(g, 'order-expiry', '订单支付时限提示', 'result', 'order', title_line='订单已超过支付时限', message='请刷新订单查看服务端最新状态。\n页面倒计时不会自行取消订单。', action='刷新订单', mood='warning')
    add(g, 'payment-unavailable', '支付渠道未开放', 'result', 'payment', 'unavailable', '当前支付意图 status=unavailable；未返回微信调起参数。', title_line='暂时无法付款', message='支付服务暂未开放。\n订单状态以订单详情为准。', action='查看订单', mood='warning')
    add(g, 'payment-confirming', '付款结果确认中', 'result', 'payment', 'target', '真实支付调起、通知与查单尚未接通；目标状态须保留。', title_line='正在确认付款结果', message='请勿重复付款。\n平台返回后仍需确认商城订单状态。', action='查询订单状态', mood='warning')
    add(g, 'payment-success', '已确认付款成功', 'result', 'payment', 'target', '仅可信后端资金事实成功时显示，不能按平台弹窗返回成功显示。', title_line='付款已确认', message='订单已确认支付 ¥137.00。\n你可以查看订单的履约进度。', action='查看订单', mood='success')
    add(g, 'payment-cancelled', '支付弹窗已关闭', 'result', 'payment', 'target', title_line='付款尚未确认', message='关闭支付弹窗不会取消商城订单。\n请返回订单查看最新资金状态。', action='查看订单', mood='neutral')
    add(g, 'payment-late', '取消后收到付款异常', 'result', 'order', 'target', '后端已有异常收款与补偿机制，真实渠道和消费端资金查询投影待接通。', title_line='异常资金处理中', message='此订单已取消，后续收款需要核实处理。\n请查询处理进度或联系售后。', action='查看处理进度', mood='warning')
    add(g, 'fulfillment-physical', '发货信息', 'fulfillment', 'fulfillment', note='仅承运人与运单号，不设计实时物流轨迹。')
    add(g, 'fulfillment-virtual', '虚拟交付信息', 'fulfillment', 'fulfillment', virtual=True)
    add(g, 'confirm-receipt', '确认收货弹窗', 'dialog', 'fulfillment', base='order', base_state='shipped', heading='确认已收到商品？', body='请确认实际收到商品后再继续。\n提交时将校验最新履约版本。', confirm='确认收货')
    add(g, 'receipt-conflict', '确认收货状态冲突', 'dialog', 'fulfillment', base='order', base_state='shipped', heading='订单履约状态已变化', body='请读取最新履约信息后再确认。\n已经完成的收货不会重复执行。', confirm='刷新履约信息')

    g = '04-aftercare'
    add(g, 'refund-form', '整单退款申请', 'refund-form', 'refund', note='只输入原因，不能选择部分商品、数量或自行填写退款金额。')
    add(g, 'refund-automatic', '未接单退款自动审核', 'refund-detail', 'refund', state='approved', automatic=True)
    add(g, 'refund-form-rejected', '退款申请校验失败', 'refund-form', 'refund', invalid=True)
    for slug, title, state in [('refund-review', '退款待审核', 'requested'), ('refund-approved', '审核通过退款处理中', 'approved'), ('refund-rejected', '退款审核未通过', 'rejected'), ('refund-completed', '退款已完成', 'completed')]:
        add(g, slug, title, 'refund-detail', 'refund', state=state,
            note='申请状态 requested/approved/rejected/completed 来自当前 Schema 与业务实现；真实渠道仍未接通。')
    add(g, 'refund-unknown', '退款资金结果未知', 'refund-detail', 'refund', 'target', '申请查询无渠道执行详情；未知资金状态需消费端展示投影，不能将 approved 等同到账。', state='unknown')
    add(g, 'refund-ineligible', '已发货不可申请退款', 'result', 'refund', title_line='当前订单不支持退款申请', message='本期仅支持未发货或未交付订单的整单退款。\n如需帮助，请联系售后。', action='查看订单', mood='warning')
    add(g, 'refund-history', '本单售后记录', 'refund-list', 'refund', note='由单笔订单的退款申请列表展示，不伪造本人全量售后列表。')
    add(g, 'reviews', '商品评价列表', 'reviews', 'review', note='只有 rating/content/published_at；不虚构评价照片、用户头像或好评率。')
    add(g, 'review-form', '评价已交付商品', 'review-form', 'review', note='评分 1 至 5，正文最多 1000 字；不增加图片上传。')
    add(g, 'review-success', '评价提交成功', 'result', 'review', title_line='评价已提交', message='感谢你的真实反馈。\n每条已交付订单明细仅可评价一次。', action='返回订单', mood='success')
    add(g, 'review-denied', '评价资格不满足', 'result', 'review', title_line='当前商品暂不可评价', message='仅本人已交付且未评价的明细可提交。\n请查看最新订单和履约状态。', action='查看订单', mood='warning')

    g = '05-account'
    add(g, 'mine', '个人中心', 'mine', 'user', 'gap', '订单入口可设计；全量统计、积分与会员等级展示需独立 C 端查询，不伪造角标。')
    add(g, 'mine-guest', '未登录个人中心', 'mine', 'user', guest=True)
    add(g, 'wechat-login', '微信登录与协议确认', 'login', '', 'target', '现有 auth/login 是用户名密码 Cookie，尚无微信 code 交换与 Bearer；不复用为小程序登录。')
    add(g, 'login-cancelled', '登录取消保留浏览', 'result', '', 'local', title_line='你可以继续浏览', message='登录已取消，公开商品仍可查看。\n再次购买时可主动发起登录。', action='返回商品', mood='neutral')
    add(g, 'profile', '个人资料', 'profile', 'user')
    add(g, 'profile-edit', '修改昵称与邮箱', 'form', 'user', fields=[('昵称', '商城用户'), ('邮箱（选填）', '请输入邮箱')], action='保存资料', intro='资料只修改当前账户，不自动绑定其他身份。')
    add(g, 'avatar-actions', '头像操作弹层', 'sheet', 'user', base='profile', choices=['拍摄照片', '从相册选择', '移除当前头像'], note='先上传本人头像资产再更新 avatar；权限按用户动作申请。')
    add(g, 'avatar-submitting', '头像上传保存中', 'result', 'user', title_line='正在保存头像', message='本次修改仍在处理中。\n保存完成前请勿重复上传。', action='保存处理中…', mood='neutral', busy=True)
    add(g, 'settings', '设置', 'menu', 'user', entries=['个人资料', '账号安全', '隐私说明', '服务协议', '帮助与售后', '关于商城'], action='退出登录')
    add(g, 'security', '账号安全', 'menu', 'security', 'gap', entries=['登录设备', '退出其他设备', '修改密码（已有密码账户）', '注销账户'], note='统一消费者会话与只读注销前置已接入；旧密码入口退役，实际注销保持关闭。')
    add(g, 'sessions', '登录设备', 'sessions', 'security', 'gap', '当前会话模型只允许 browser_cookie，微信设备会话适配未实现。')
    add(g, 'session-revoke', '退出其他设备确认', 'dialog', 'security', base='sessions', heading='退出其他登录设备？', body='其他设备将需要重新登录。\n当前设备会话将保留。', confirm='确认退出')
    add(g, 'password', '已有密码账户修改密码', 'form', 'security', 'gap', '仅具有密码凭据的既有账户适用；不要求微信无密码账户填不存在的密码。', fields=[('当前密码', '请输入当前密码'), ('新密码', '6 至 64 个字符'), ('确认新密码', '再次输入新密码')], action='确认修改', intro='仅已有密码凭据的账户显示此入口。')
    add(g, 'logout', '退出登录确认', 'dialog', 'auth', base='mine', heading='退出当前账户？', body='退出后将清除本机私有内容。\n商品公开浏览仍可继续。', confirm='退出登录')
    add(g, 'account-delete', '注销账户说明', 'info', 'security', 'gap', '当前注销是软删除并要求密码；微信账户证明与资金前置检查必须专项确认。', rows=[('注销对象', '当前本人账户'), ('历史交易', '按适用规则保留'), ('资金与售后', '先核实未结事项')], body='请先处理未完成交易、售后与资金事项。\n注销不会立即物理删除全部历史记录。', action='继续核对注销条件')
    add(g, 'account-disabled', '账户停用反馈', 'result', 'user', title_line='当前账户无法使用', message='账户已停用或会话被撤销。\n私有内容已停止展示，请联系运营。', action='查看帮助', mood='warning')

    g = '06-address'
    add(g, 'addresses', '收货地址管理', 'address-list', 'address')
    add(g, 'address-select', '选择收货地址', 'address-list', 'address', select=True)
    add(g, 'address-add', '新增收货地址', 'address-form', 'address')
    add(g, 'address-edit', '编辑收货地址', 'address-form', 'address', edit=True)
    add(g, 'address-region', '省市区选择', 'region', 'address', 'gap', 'AddressInput 要求三级六位行政编码；行政区数据来源尚需工程专项确认。')
    add(g, 'address-delete', '删除地址确认', 'dialog', 'address', base='address-list', heading='删除这条收货地址？', body='将删除当前默认地址。\n如有其他地址，服务端将确定替补默认地址。', confirm='确认删除', danger=True)
    add(g, 'address-conflict', '地址版本冲突', 'dialog', 'address', base='address-form', heading='地址已在其他设备修改', body='请读取最新地址再编辑。\n本次输入可保留，不能覆盖新版本。', confirm='读取最新地址')
    add(g, 'address-limit', '收货地址数量上限', 'result', 'address', title_line='收货地址已达上限', message='最多保存 20 条收货地址。\n请编辑或删除不再使用的地址。', action='管理收货地址', mood='warning')
    add(g, 'address-validation', '地址表单校验', 'address-form', 'address', invalid=True)

    g = '07-member'
    add(g, 'membership', '会员与分销档案', 'membership', 'member', 'gap', '档案返回 level_id 与邀请码，不含等级名称、权益、有效邀请统计；不调用 Admin 等级接口。')
    add(g, 'membership-open', '开通分销档案', 'info', 'member', rows=[('当前档案', '尚未开通'), ('开通方式', '本人主动确认'), ('会员等级', '由服务端资格决定')], body='开通分销档案不等于获得付费会员等级。\n不承诺收益，不自动绑定推荐人。', action='确认开通档案')
    add(g, 'membership-disabled', '会员等级停用', 'info', 'checkout', rows=[('等级状态', '已停用'), ('适用价格', '按当前服务端报价'), ('原有交易', '保留历史快照')], body='停用等级的价格权益不再用于新报价。\n已有订单继续按原快照展示。')
    add(g, 'referrer-bind', '首次绑定推荐人', 'form', 'referrer', fields=[('推荐人邀请码', 'ABCD1234')], intro='推荐关系只允许首次绑定。\n请核对邀请码后主动确认。', action='核对并确认绑定')
    add(g, 'referrer-confirm', '推荐绑定确认弹窗', 'dialog', 'referrer', base='membership', heading='绑定此推荐人？', body='邀请码：ABCD1234（设计示例）\n首次绑定后不能随意更改。\n服务端将校验自邀与循环关系。', confirm='确认绑定')
    add(g, 'referrer-bound', '已绑定推荐关系', 'info', 'member', rows=[('推荐关系', '已首次绑定'), ('绑定时间', '2026-10-09 10:00'), ('推荐人', '已绑定，身份信息受保护')], body='推荐关系已经确认，不能自行更换。\n推荐人完整身份资料受隐私保护。', note='当前 inviter_id 不应直接展示完整 UUID；昵称/脱敏投影待补齐。')
    add(g, 'referrer-invalid', '邀请码失效或绑定拒绝', 'result', 'referrer', title_line='暂时无法绑定推荐人', message='邀请码无效、自邀、循环或已绑定时会被拒绝。\n请核对服务端返回的具体原因。', action='返回核对邀请码', mood='warning')
    add(g, 'invite-share', '分享邀请说明', 'share', 'member', 'target', '邀请码已有；微信分享参数与有效邀请政策待专项，不画伪造二维码或收益统计。')
    add(g, 'points', '积分账户接入前', 'result', '', 'unavailable', '仅有 Admin 积分账户/流水接口，无本人 C 端查询；不展示假余额、兑换或抵扣。', title_line='积分服务暂未开放', message='积分账户的本人查询尚未开放。\n当前不提供兑换、抵扣或到期操作。', action='返回个人中心', mood='neutral')

    g = '08-wallet'
    add(g, 'wallets', '我的钱包', 'wallets', 'wallet')
    add(g, 'wallet-commission', '佣金钱包', 'wallet', 'wallet', wallet_type='commission')
    add(g, 'wallet-consumption', '消费钱包', 'wallet', 'wallet', wallet_type='consumption')
    add(g, 'wallet-debt', '钱包欠款限制', 'wallet', 'wallet', wallet_type='commission', debt=True)
    add(g, 'commissions', '佣金记录', 'commissions', 'commission', note='只有 page/page_size；不添加服务端尚不支持的状态筛选和全量收入汇总。')
    add(g, 'commission-frozen', '冻结佣金详情', 'commission', 'commission', state='frozen')
    add(g, 'commission-settled', '已结算佣金详情', 'commission', 'commission', state='settled')
    add(g, 'commission-recovered', '已追回佣金详情', 'commission', 'commission', state='recovered')
    add(g, 'withdrawal-form', '提现申请预备页', 'withdraw-form', 'withdrawal', 'unavailable', '申请/审核/人工完成已有；自动打款与收款引用接入未完成，当前设计禁用提交。')
    add(g, 'withdrawal-records', '提现记录', 'withdraw-list', 'withdrawal')
    for slug, title, state in [('withdrawal-review', '提现待审核', 'requested'), ('withdrawal-approved', '提现审核通过', 'approved'), ('withdrawal-rejected', '提现审核未通过', 'rejected'), ('withdrawal-processing', '提现执行处理中', 'processing'), ('withdrawal-unknown', '提现结果未知', 'unknown'), ('withdrawal-completed', '提现确认完成', 'succeeded')]:
        add(g, slug, title, 'withdraw-detail', 'withdrawal', 'existing' if state in ['requested', 'approved', 'rejected', 'succeeded'] else 'target', state=state, note='状态枚举已有；succeeded 可由已授权人工凭证确认，不能将 approved 当到账；真实自动打款未接通。')
    add(g, 'withdrawal-balance', '提现余额不足或欠款', 'result', 'withdrawal', title_line='当前无法申请提现', message='可用佣金不足或存在欠款时不能申请。\n请查询钱包的可用、冻结与欠款金额。', action='查看佣金钱包', mood='warning')
    add(g, 'wallet-ledger-unavailable', '钱包流水接入前', 'result', 'wallet', 'unavailable', '钱包账本在后端存在，但没有本人钱包流水 API；不拼凑佣金列表冒充资金流水。', title_line='钱包流水查询暂未开放', message='当前可查看钱包余额与佣金、提现记录。\n完整钱包资金流水入口尚未开放。', action='返回钱包', mood='neutral')

    g = '09-service'
    add(g, 'help', '帮助与售后', 'menu', '', 'local', entries=['下单与付款说明', '配送与交付说明', '退款申请规则', '会员与钱包说明', '联系售后'], note='帮助内容为草案，真实服务联系方式需运营配置确认。')
    add(g, 'help-refund', '退款规则说明', 'info', 'refund', 'local', rows=[('适用订单', '已成交且未发货/交付'), ('退款范围', '整单商品及原运费'), ('审核方式', '按接单事实判定')], body='已接单需人工审核，未接单可自动审核。\n审核通过后仍需确认退款资金结果。\n已发货或已交付订单本期不能新增申请。')
    add(g, 'contact', '联系售后', 'info', '', 'unavailable', 'site-profile 未提供联系方式字段；不虚构电话、在线聊天或营业时间。', rows=[('服务方式', '等待运营公布'), ('订单求助', '提供脱敏订单摘要'), ('隐私提醒', '勿提供密码或付款秘密')], body='当前联系方式尚未配置。\n具体服务方式以商城正式公布的信息为准。')
    add(g, 'privacy', '隐私说明草案', 'info', '', 'local', rows=[('公开浏览', '无需强制登录'), ('资料与地址', '用于本人资料与履约'), ('设备权限', '按实际操作申请')], body='仅获取完成对应业务必要的信息。\n拒绝非必要权限不影响公开商品浏览。\n退出清除本机私有缓存；历史交易按规则保留。\n此为设计结构草案，正式文本需审核。')
    add(g, 'terms', '服务协议草案', 'info', '', 'local', rows=[('商品与成交', '以服务端报价为准'), ('退款与履约', '遵守已公布的规则'), ('资金结果', '以可信事实为准')], body='请阅读商城正式发布的服务协议。\n本设计仅说明页面结构，不形成法律承诺。')
    add(g, 'about', '关于商城', 'info', 'system', 'gap', 'site-profile 当前为 Web 通用字段；小程序信息与联系方式须专项适配。', rows=[('商城名称', '拼捷商城（设计示例）'), ('客户端形态', '微信小程序'), ('相关说明', '隐私与服务协议')], body='商品、订单和资金状态由商城服务提供。\n版本与主体信息以正式发布内容为准。')
    add(g, 'permission-photo', '头像权限拒绝', 'result', 'user', 'local', title_line='未允许使用相册', message='本次头像修改未完成。\n可以继续使用原头像并浏览商城。', action='返回个人资料', mood='neutral')
    add(g, 'service-unavailable', '服务暂时不可用', 'result', 'system', title_line='服务暂时不可用', message='请稍后重试，当前内容未能刷新。\n网络故障不会自动清除你的登录状态。', action='重试查询', mood='warning')
    add(g, 'rate-limited', '请求过于频繁', 'result', '', 'local', title_line='操作有点频繁', message='请按提示稍后重试。\n未确认的交易请查询结果，不要重复提交。', action='返回原页面', mood='warning')
    add(g, 'image-error', '商品图片加载失败', 'result', 'product', title_line='图片暂未加载成功', message='商品文字信息仍可查看。\n可以重试加载图片或返回商品详情。', action='重新加载图片', mood='neutral')
    add(g, 'offline', '断网恢复提示', 'result', '', 'local', title_line='网络连接已断开', message='暂时不能刷新数据或提交交易。\n恢复网络后请核对最新订单与报价。', action='检查网络后重试', mood='warning')
    add(g, 'session-expired', '登录恢复失败', 'result', 'auth', title_line='需要重新登录', message='当前登录状态已失效。\n原操作尚未自动提交，登录后请重新确认。', action='主动重新登录', mood='warning')
    add(g, 'refresh-error', '已有内容刷新失败', 'dialog', 'cart', base='cart', heading='当前内容未能刷新', body='页面保留上次成功读取的内容。\n请重新查询后再进行交易确认。', confirm='重试刷新')
    add(g, 'update-prompt', '小程序更新提示', 'dialog', '', 'local', base='mine', heading='新版本已准备好', body='请在交易结果确认后再更新。\n更新前保留待确认的订单操作意图。', confirm='稍后更新')

    # Every data-oriented page family gets concrete initial states.
    state_families = ['home', 'category', 'product', 'cart', 'checkout-physical',
                      'orders-list', 'order-pending', 'fulfillment-physical',
                      'refund-history', 'reviews', 'mine', 'profile', 'sessions',
                      'addresses', 'membership', 'wallets', 'commissions', 'withdrawal-records']
    no_empty = {'checkout-physical', 'order-pending', 'fulfillment-physical', 'mine', 'profile', 'wallets'}
    private = {'cart', 'checkout-physical', 'orders-list', 'order-pending', 'refund-history', 'mine', 'profile', 'sessions', 'addresses', 'membership', 'wallets', 'commissions', 'withdrawal-records'}
    originals = {p['slug']: p for p in PAGES}
    for slug in state_families:
        original = originals[slug]
        for state in ['loading', 'error'] + ([] if slug in no_empty else ['empty']) + (['login'] if slug in private else []):
            state_title = {'loading': '首次加载', 'error': '查询失败', 'empty': '无数据', 'login': '未登录'}[state]
            page = add('10-states', f'{slug}-{state}', f'{original["title"]}：{state_title}', 'state', status=original['status'], note=f'复用 {slug} 的能力边界；{state_title}独立呈现，不伪造业务结果。', state=state, parent=slug, page_title=original['title'], tab={'home': 'home', 'category': 'grid', 'cart': 'cart', 'mine': 'user'}.get(slug))
            page['api'] = original['api']


class Canvas:
    def __init__(self, title, tab=None):
        self.im = ui.shell(title, back=tab is None)
        self.tab = tab
        self.limit = 1472 if tab else 1470
        self.rects = []

    def txt(self, x, y, value, size=28, color='text', bold=False, max_width=638):
        draw = ImageDraw.Draw(self.im)
        for content in value.split('\n'):
            current = ''
            for char in content:
                if draw.textlength(current + char, font=ui.font(size, bold)) > max_width:
                    ui.text(self.im, (x, y), current, size, color, bold)
                    y += int(size * 1.5)
                    current = char
                else:
                    current += char
            if current:
                ui.text(self.im, (x, y), current, size, color, bold)
            y += int(size * 1.5)
        if y > self.limit:
            raise ValueError(f'Text below content area: {value}')
        return y

    def card(self, y, h):
        if y + h > self.limit:
            raise ValueError('Card overlaps reserved footer')
        ui.box(self.im, (32, y, 718, y + h), radius=20)

    def row(self, y, label, value='', arrow=False, color='secondary'):
        self.txt(56, y + 22, label, max_width=270)
        if value:
            d = ImageDraw.Draw(self.im)
            width = d.textlength(value, font=ui.font(26))
            self.txt(680 - width - (28 if arrow else 0), y + 24, value, 26, color, max_width=350)
        if arrow:
            ui.icon(self.im, 653, y + 18, 'next')
        ui.line(self.im, [(56, y + 78), (694, y + 78)], width=1)
        return y + 88

    def notice(self, y, message):
        lines = message.count('\n') + 1
        h = 40 + lines * 38
        ui.box(self.im, (32, y, 718, y + h), 'soft', radius=12)
        self.txt(56, y + 18, message, 24, 'primary')
        return y + h + 24

    def title(self, y, title, description=''):
        y = self.txt(32, y, title, 36, bold=True)
        if description:
            y = self.txt(32, y + 12, description, 26, 'secondary')
        return y + 24

    def button(self, label, disabled=False, secondary=None):
        if self.tab:
            ui.box(self.im, (32, 1240, 718, 1328), 'border' if disabled else 'primary', 12)
            ui.text(self.im, (375, 1284), label, 28, 'secondary' if disabled else 'surface', True, 'mm')
            return
        ui.box(self.im, (0, 1478, 750, 1624), radius=0)
        ui.line(self.im, [(0, 1478), (750, 1478)], width=1)
        fill = 'border' if disabled else 'primary'
        x = 32 if secondary is None else 384
        ui.box(self.im, (x, 1494, 718, 1582), fill, 12)
        ui.text(self.im, ((x + 718) / 2, 1538), label, 28,
                'secondary' if disabled else 'surface', True, 'mm')
        if secondary:
            ui.box(self.im, (32, 1494, 360, 1582), 'surface', 12, 'border')
            ui.text(self.im, (196, 1538), secondary, 28, 'text', anchor='mm')

    def finish(self):
        if self.tab:
            ui.tabbar(self.im, self.tab)
        else:
            ui.home_indicator(self.im)
        return self.im


def item(c, y, shade='white', quantity=1, selection=False, invalid=False, virtual=False, amount='129.00'):
    c.card(y, 230)
    x = 96 if selection else 56
    if virtual:
        ui.box(c.im, (x, y + 24, x + 160, y + 184), 'soft', 12)
        ui.icon(c.im, x + 50, y + 70, 'phone', 'primary', 60)
    else:
        c.im.paste(ui.garment((160, 160), shade), (x, y + 24))
    if selection:
        ImageDraw.Draw(c.im).ellipse((50, y + 86, 82, y + 118), outline=ui.C['border'] if invalid else ui.C['primary'], fill=None if invalid else ui.C['primary'], width=2)
        if not invalid:
            ui.line(c.im, [(58, y + 102), (63, y + 107), (75, y + 94)], 'surface', 3)
    c.txt(x + 184, y + 24, '虚拟商品示例' if virtual else '基础圆领短袖', 28, bold=True, max_width=400)
    c.txt(x + 184, y + 70, '虚拟交付' if virtual else ('白色 / M' if shade == 'white' else '黑色 / L'), 24, 'secondary')
    c.txt(x + 184, y + 116, '暂不可售' if invalid else '¥' + amount, 32, 'primary', True)
    c.txt(595, y + 128, f'×{quantity}', 24, 'secondary', max_width=80)
    return y + 254


def render(page):
    kind, data = page['kind'], page['data']
    title = data.get('page_title', page['title'].split('：')[0])
    if kind in ['home', 'product', 'sku']:
        if kind == 'home':
            return ui.home()
        if kind == 'product':
            return ui.detail()
        im = ui.sku()
        if data.get('action'):
            ui.box(im, (32, 1488, 718, 1576), 'primary', 12)
            ui.text(im, (375, 1532), data['action'], 28, 'surface', True, 'mm')
        if data.get('warning'):
            ui.box(im, (20, 1350, 730, 1438), 'soft', 12)
            ui.text(im, (44, 1380), data['warning'], 24, 'primary')
        return im
    c = Canvas(title, data.get('tab') or {'category': 'grid', 'cart': 'cart', 'mine': 'user'}.get(kind))
    y = 206
    if kind == 'category':
        ui.box(c.im, (0, 174, 178, 1488), '#EFF0F3', 0)
        for i, label in enumerate(['服饰', '鞋靴', '家居', '数码', '虚拟商品']):
            if i == 0:
                ui.box(c.im, (0, 192, 178, 280), 'surface', 0)
                ui.box(c.im, (0, 213, 6, 259), 'primary', 0)
            ui.text(c.im, (89, 236 + i * 104), label, 28, 'primary' if i == 0 else 'secondary', i == 0, 'mm')
        c.txt(206, 206, '服饰 / 基础上装' if data.get('sub') else '服饰', 32, bold=True, max_width=480)
        for i, label in enumerate(['全部', '上装', '下装']):
            ui.box(c.im, (206 + 168 * i, 278, 352 + 168 * i, 354), 'soft' if i == 0 else 'surface', 12)
            ui.text(c.im, (279 + i * 168, 316), label, 26, 'primary' if i == 0 else 'secondary', anchor='mm')
        for i, shade in enumerate(['white', 'black', 'gray']):
            yy = 386 + i * 342
            ui.box(c.im, (206, yy, 718, yy + 318), 'surface', 20)
            c.im.paste(ui.garment((228, 228), shade), (222, yy + 16))
            c.txt(474, yy + 24, '基础圆领\n短袖', 28, bold=True, max_width=220)
            c.txt(474, yy + 128, ['白色', '黑色', '灰色'][i], 24, 'secondary')
            c.txt(474, yy + 182, '¥129.00', 32, 'primary', True, max_width=220)
            c.txt(222, yy + 265, '实物商品 · 参考价', 24, 'secondary')
    elif kind == 'cart':
        y = c.title(y, '购物车', '管理' if not data.get('edit') else '逐件删除并确认')
        y = item(c, y, selection=True)
        y = item(c, y, 'black', 2, True, data.get('invalid', False))
        if data.get('invalid'):
            y = c.notice(y, '失效商品无法结算，请修改或删除')
        else:
            c.card(y, 110)
            c.row(y + 10, '数量调整', '−    1    +')
            y += 134
        c.txt(32, y + 10, '选中数量与条目以购物车为准。\n金额仅供参考，结算将重新报价。', 24, 'secondary')
        ui.box(c.im, (0, 1368, 750, 1488), radius=0)
        c.txt(32, 1410, '全选', 28)
        c.txt(164, 1390, '参考合计', 24, 'secondary')
        c.txt(164, 1422, '¥129.00' if data.get('invalid') else '¥387.00', 32, 'primary', True)
        ui.box(c.im, (460, 1384, 718, 1472), 'primary', 12)
        ui.text(c.im, (589, 1428), '去结算' if not data.get('edit') else '完成管理', 28, 'surface', True, 'mm')
    elif kind == 'checkout':
        y = c.title(y, '确认订单')
        if data.get('warning'):
            y = c.notice(y, data['warning'])
        c.card(y, 174)
        if data.get('virtual'):
            c.txt(56, y + 24, '虚拟商品，无需收货地址', 28, bold=True)
            c.txt(56, y + 80, '成交后按订单交付信息查看内容。', 24, 'secondary')
        elif data.get('no_address'):
            c.txt(56, y + 24, '请选择收货地址', 32, bold=True)
            c.txt(56, y + 84, '新增或选择本人地址后获取配送报价。', 24, 'secondary')
        else:
            c.txt(56, y + 24, '示例收件人  138****0000', 28, bold=True)
            c.txt(56, y + 80, '示例省 / 示例市 / 示例区\n示例路 1 号', 24, 'secondary')
        ui.icon(c.im, 650, y + 65, 'next')
        y += 198
        y = item(c, y, virtual=data.get('virtual', False), amount='0.00' if data.get('zero') else '129.00')
        c.card(y, 300)
        unquoted = data.get('no_address') or data.get('blocked')
        c.row(y + 8, '商品参考金额' if unquoted else '商品金额', '¥0.00' if data.get('zero') else '¥129.00')
        c.row(y + 96, '运费', '尚未报价' if unquoted else ('¥0.00' if data.get('zero') or data.get('virtual') else '¥8.00'))
        c.row(y + 184, '应付总额', '尚未报价' if unquoted else ('¥0.00' if data.get('zero') else ('¥129.00' if data.get('virtual') else '¥137.00')), color='primary')
        y += 324
        c.txt(32, y, '请选择可配送地址后重新获取报价。' if unquoted else ('零应付由商城内部确认成交，不调用支付。' if data.get('zero') else '金额由服务端报价；提交时再次校验。\n不提供钱包抵扣、优惠券或混合商品下单。'), 24, 'secondary')
        c.button('提交订单中…' if data.get('busy') else ('确认零应付成交' if data.get('zero') else '提交订单'), data.get('busy') or data.get('blocked') or data.get('no_address'))
    elif kind == 'orders-list':
        y = c.title(y, '我的订单')
        for i, label in enumerate(['全部', '待付款', '待发货', '待收货']):
            ui.text(c.im, (116 + i * 174, y + 28), label, 26, 'primary' if i == 0 else 'secondary', anchor='mm')
        y += 80
        for i, label in enumerate(['待付款', '已付款 · 待发货', '已发货 · 待收货']):
            c.card(y, 286)
            c.txt(56, y + 22, '订单示例 01' + str(i + 1), 24, 'secondary')
            c.txt(440, y + 22, label, 24, 'primary', max_width=250)
            c.im.paste(ui.garment((112, 112)), (56, y + 76))
            c.txt(192, y + 84, '基础圆领短袖', 28, bold=True)
            c.txt(192, y + 130, '白色 / M ×1', 24, 'secondary')
            c.txt(56, y + 218, '应付 ¥137.00', 28, bold=True)
            ui.box(c.im, (510, y + 200, 694, y + 264), 'surface', 12, 'border')
            ui.text(c.im, (602, y + 232), '查看详情', 24, anchor='mm')
            y += 310
    elif kind == 'order':
        state = data.get('state', 'pending')
        heading, explanation = {
            'pending': ('待付款', '请在订单支付时限内完成付款。'),
            'paid': ('已付款，等待发货', '商家将按订单信息安排履约。'),
            'shipped': ('商品已发货', '请在实际收到商品后确认收货。'),
            'delivered': ('订单已完成', '商品已交付，可以按资格提交评价。'),
            'cancelled': ('订单已取消', '资金异常需单独查询，不自动再次付款。'),
            'zero': ('零应付已内部成交', '无需调起支付，后续按订单履约。'),
            'virtual': ('虚拟商品已交付', '请查看交付信息，不需要收货地址。'),
        }[state]
        y = c.title(y, heading, explanation)
        y = item(c, y, virtual=state == 'virtual', amount='0.00' if state == 'zero' else '129.00')
        c.card(y, 282)
        c.row(y + 6, '商品金额', '¥0.00' if state == 'zero' else '¥129.00')
        c.row(y + 94, '运费', '¥0.00' if state in ['zero', 'virtual'] else '¥8.00')
        c.row(y + 182, '订单应付', '¥0.00' if state == 'zero' else ('¥129.00' if state == 'virtual' else '¥137.00'), color='primary')
        y += 306
        c.card(y, 268)
        c.row(y + 8, '订单编号', '示例订单 001')
        c.row(y + 96, '创建时间', '2026-10-09 10:00')
        c.row(y + 184, '履约信息', '查看交付' if state == 'virtual' else '查看详情', True)
        y += 292
        if state in ['pending', 'paid', 'shipped']:
            c.txt(32, y, '订单与履约分别查询，不按客户端推断状态。', 24, 'secondary')
        if state == 'pending':
            c.button('付款暂未开放', True, '取消订单')
        elif state == 'shipped':
            c.button('确认收货', secondary='发货信息')
        elif state in ['virtual', 'delivered']:
            c.button('评价商品', secondary='查看履约')
        elif state == 'paid':
            c.button('查看履约', secondary='整单退款')
    elif kind == 'fulfillment':
        y = c.title(y, '已交付' if data.get('virtual') else '商品已发货', '以下信息来自订单履约事实')
        c.card(y, 288)
        if data.get('virtual'):
            c.row(y + 8, '商品类型', '虚拟商品')
            c.row(y + 96, '交付状态', '已交付')
            c.row(y + 184, '交付时间', '2026-10-09 12:00')
            y += 312
            c.card(y, 170)
            c.txt(56, y + 24, '交付信息', 28, bold=True)
            c.txt(56, y + 80, '交付说明示例，仅向本人展示。', 26, 'secondary')
        else:
            c.row(y + 8, '承运人', '示例承运商')
            c.row(y + 96, '运单号', 'DEMO-001')
            c.row(y + 184, '发货时间', '2026-10-09 12:00')
            y += 312
            c.txt(32, y, '可复制运单号到承运商官方渠道查询。\n商城本期不提供实时物流轨迹。', 26, 'secondary')
            c.button('确认收货')
    elif kind == 'refund-form':
        y = c.notice(y, '仅支持整单退款，包含原订单运费')
        y = item(c, y)
        c.card(y, 182)
        c.row(y + 8, '商品金额', '¥129.00')
        c.row(y + 96, '退款总额（含运费）', '¥137.00', color='primary')
        y += 206
        c.card(y, 286)
        c.txt(56, y + 24, '退款原因', 28, bold=True)
        c.txt(56, y + 84, '请说明退款原因，最多 300 字。', 26, 'secondary')
        c.txt(600, y + 232, '0 / 300', 24, 'secondary', max_width=100)
        c.txt(32, y + 320, '请填写退款原因，原输入已保留。' if data.get('invalid') else '提交后按接单事实自动或人工审核。\n审核通过不代表款项已退回。', 24, 'primary' if data.get('invalid') else 'secondary')
        c.button('提交整单退款申请')
    elif kind == 'refund-detail':
        state = data['state']
        heading, desc = {
            'requested': ('退款申请待审核', '申请已提交，等待审核结果。'),
            'approved': ('审核通过，退款处理中', '资金退回尚未确认，请勿重复申请。'),
            'rejected': ('审核未通过', '请查看审核意见，如需帮助联系售后。'),
            'completed': ('退款已完成', '仅在服务端确认退款完成后展示。'),
            'unknown': ('退款资金结果确认中', '当前结果未知，不显示到账承诺。'),
        }[state]
        y = c.title(y, heading, desc)
        c.card(y, 276)
        c.row(y + 8, '退款商品金额', '¥129.00')
        c.row(y + 96, '原运费', '¥8.00')
        c.row(y + 184, '退款总额', '¥137.00', color='primary')
        y += 300
        c.card(y, 366)
        c.row(y + 8, '申请编号', '示例退款 001')
        c.row(y + 96, '申请时间', '2026-10-09 10:30')
        c.row(y + 184, '审核方式', '未接单：自动审核' if data.get('automatic') else '已接单：人工审核')
        c.txt(56, y + 282, '审核意见：' + ('不满足当前申请条件' if state == 'rejected' else ('尚未审核' if state == 'requested' else '同意整单退款')), 26, 'secondary')
        y += 390
        c.txt(32, y, '申请 → 审核 → 资金确认\n审核与到账是两个独立事实。', 26, 'secondary')
        c.button('刷新申请状态', secondary='联系售后')
    elif kind in ['refund-list', 'withdraw-list', 'commissions', 'reviews', 'sessions']:
        entries = {
            'refund-list': [('整单退款 ¥137.00', '审核通过，退款处理中', '2026-10-09 10:30'), ('历史申请 ¥137.00', '已拒绝 · 详见审核意见', '2026-10-08 11:00')],
            'withdraw-list': [('提现 ¥100.00', '待审核', '2026-10-09 10:30'), ('提现 ¥80.00', '审核通过，尚未确认完成', '2026-10-08 11:00'), ('提现 ¥50.00', '已确认完成', '2026-10-07 15:00')],
            'commissions': [('佣金 ¥12.90', '冻结 · 一级佣金', '2026-10-09 10:30'), ('佣金 ¥8.00', '已结算 · 二级佣金', '2026-10-08 11:00'), ('佣金 ¥6.00', '已追回 · 退款关联', '2026-10-07 15:00')],
            'reviews': [('评分 5 / 5', '款式简洁，日常穿着合适。', '2026-10-09 10:30'), ('评分 4 / 5', '已收到商品，反馈供购买参考。', '2026-10-08 11:00')],
            'sessions': [('当前登录设备', '当前设备 · 来源已脱敏', '最近活动 2026-10-09 10:30'), ('其他登录设备', '可以单独撤销该会话', '最近活动 2026-10-08 11:00')],
        }[kind]
        y = c.title(y, title, '按服务端分页加载' if kind != 'refund-list' else '本笔订单的退款申请')
        for heading, body, when in entries:
            c.card(y, 218)
            c.txt(56, y + 24, heading, 32, bold=True)
            c.txt(56, y + 82, body, 26, 'primary' if kind != 'reviews' else 'secondary')
            c.txt(56, y + 152, when, 24, 'secondary')
            if kind != 'reviews':
                ui.icon(c.im, 656, y + 22, 'next')
            y += 242
        c.txt(32, y + 10, '没有更多记录' if kind == 'refund-list' else '继续加载下一页', 24, 'secondary')
    elif kind == 'review-form':
        y = item(c, y)
        c.card(y, 166)
        c.txt(56, y + 24, '商品评分', 28, bold=True)
        c.txt(56, y + 80, '★   ★   ★   ★   ★', 44, 'primary')
        y += 190
        c.card(y, 404)
        c.txt(56, y + 24, '评价内容（选填）', 28, bold=True)
        c.txt(56, y + 84, '请分享真实体验，最多 1000 字。', 26, 'secondary')
        c.txt(570, y + 350, '0 / 1000', 24, 'secondary', max_width=140)
        c.txt(32, y + 438, '每条已交付明细只能评价一次。\n本期不支持评价图片上传。', 24, 'secondary')
        c.button('提交评价')
    elif kind == 'mine':
        guest = data.get('guest')
        c.card(y, 208)
        ui.box(c.im, (56, y + 42, 164, y + 150), 'soft', 54)
        ui.icon(c.im, 88, y + 70, 'user', 'primary', 44)
        c.txt(192, y + 44, '登录后查看账户' if guest else '商城用户', 36, bold=True)
        c.txt(192, y + 110, '公开商品仍可浏览' if guest else '个人资料与账户设置', 26, 'secondary')
        y += 232
        c.card(y, 182)
        c.txt(56, y + 24, '我的订单', 32, bold=True)
        for i, label in enumerate(['待付款', '待发货', '待收货', '全部订单']):
            ui.text(c.im, (132 + i * 164, y + 114), label, 26, 'secondary', anchor='mm')
        y += 206
        c.card(y, 528)
        for label in ['收货地址', '会员与分销', '我的钱包', '积分服务', '帮助与售后', '设置']:
            y = c.row(y, label, arrow=True)
        if guest:
            c.txt(32, y + 28, '查看私有内容时再主动登录。', 24, 'secondary')
    elif kind == 'profile':
        y = c.title(y, '个人资料')
        c.card(y, 360)
        c.row(y + 8, '头像', '选择或移除', True)
        c.row(y + 96, '昵称', '商城用户', True)
        c.row(y + 184, '邮箱', '未填写', True)
        c.row(y + 272, '账户状态', '正常')
        c.txt(32, y + 400, '昵称与邮箱可按需填写。\n头像只在主动修改时申请相关权限。', 26, 'secondary')
    elif kind == 'login':
        y = c.title(330, '登录后继续操作', '使用微信身份建立本人商城账户')
        c.card(y, 270)
        c.txt(56, y + 30, '登录后可以', 32, bold=True)
        c.txt(56, y + 94, '查看本人购物车、订单和收货地址。\n按资格查看会员与资金记录。\n登录成功后不会自动提交交易。', 28, 'secondary')
        c.txt(48, 1120, '○  我已阅读并同意服务协议与隐私说明', 26)
        c.button('同意协议后微信登录', True, '继续浏览')
    elif kind == 'form':
        y = c.title(y, title, data.get('intro', ''))
        fields = data['fields']
        for label, value in fields:
            c.card(y, 160)
            c.txt(56, y + 18, label, 28, bold=True)
            c.txt(56, y + 80, value, 28, 'secondary')
            y += 184
        c.button(data.get('action', '保存'))
    elif kind == 'address-form':
        y = c.title(y, '编辑地址' if data.get('edit') else '新增地址')
        fields = [('收件人', '示例收件人' if data.get('edit') else '请输入收件人姓名'), ('联系电话', '10000000000' if data.get('edit') else '请输入联系电话'), ('省 / 市 / 区', '示例省 / 示例市 / 示例区' if data.get('edit') else '请选择地区'), ('详细地址', '示例路 1 号' if data.get('edit') else '街道、门牌号等详细信息')]
        for label, value in fields:
            c.card(y, 142)
            c.txt(56, y + 18, label, 28, bold=True)
            c.txt(56, y + 76, value, 26, 'secondary')
            y += 166
        c.card(y, 110)
        c.row(y + 6, '设为默认地址', '○')
        y += 134
        if data.get('invalid'):
            c.txt(32, y, '请填写收件人并选择完整省市区。\n联系电话格式不正确，请核对。', 26, 'primary')
        else:
            c.txt(32, y, '最多保存 20 条，仅本人可以访问。\n首次地址默认设置由服务端决定。', 24, 'secondary')
        c.button('保存地址')
    elif kind == 'address-list':
        y = c.title(y, '选择配送地址' if data.get('select') else '我的收货地址')
        for i in range(2):
            c.card(y, 272)
            c.txt(56, y + 24, '示例收件人  138****0000', 28, bold=True)
            c.txt(56, y + 84, '示例省 / 示例市 / 示例区\n示例路 ' + str(i + 1) + ' 号', 26, 'secondary')
            c.txt(56, y + 212, '默认地址' if i == 0 else '设为默认', 24, 'primary' if i == 0 else 'secondary')
            c.txt(552, y + 212, '选择' if data.get('select') else '编辑', 26, 'primary', max_width=140)
            y += 296
        c.button('新增收货地址')
    elif kind == 'region':
        c = Canvas('选择地区')
        y = c.title(y, '省 / 市 / 区', '请依次选择完整地区')
        for i, value in enumerate(['示例省', '示例市', '请选择区县']):
            ui.text(c.im, (120 + i * 250, y + 24), value, 26, 'primary' if i == 2 else 'secondary', anchor='mm')
        y += 86
        c.card(y, 440)
        for i, label in enumerate(['示例区 A', '示例区 B', '示例区 C', '示例区 D']):
            c.row(y + i * 96, label, '已选' if i == 0 else '')
        c.button('确认地区')
    elif kind == 'menu':
        y = c.title(y, title)
        entries = data['entries']
        c.card(y, len(entries) * 96 + 16)
        for entry in entries:
            c.row(y + 8, entry, arrow=True)
            y += 96
        if data.get('action'):
            c.button(data['action'])
    elif kind in ['info', 'commission', 'withdraw-detail']:
        if kind == 'commission':
            state = data['state']
            heading = {'frozen': '佣金冻结中', 'settled': '佣金已结算', 'recovered': '佣金已追回'}[state]
            rows = [('佣金金额', '¥12.90'), ('分佣层级', '一级'), ('关联订单', '示例订单 001'), ('已追回金额', '¥12.90' if state == 'recovered' else '¥0.00'), ('结算时间', '2026-10-09' if state == 'settled' else '未结算')]
            body = '比例、金额与规则来自订单行佣金快照。\n不按分享次数估算收益，不暴露来源用户身份。'
        elif kind == 'withdraw-detail':
            state = data['state']
            heading = {'requested': '提现待审核', 'approved': '审核通过，尚未确认完成', 'rejected': '审核未通过', 'processing': '提现处理中', 'unknown': '提现结果确认中', 'succeeded': '提现已确认完成'}[state]
            review_note = '尚未审核' if state == 'requested' else ('收款资料需核对' if state == 'rejected' else '已同意申请')
            rows = [('提现金额', '¥100.00'), ('申请时间', '2026-10-09 10:30'), ('收款引用', '脱敏目标示例'), ('审核意见', review_note), ('完成时间', '2026-10-09 16:00' if state == 'succeeded' else '尚未确认')]
            body = {
                'requested': '申请金额已冻结，等待审核。\n请勿重复提交同一提现意图。',
                'approved': '审核通过，执行结果尚未确认。\n到账以已确认收款事实为准。',
                'rejected': '本次申请未通过，请核对审核意见。\n冻结金额已解冻，请查看最新钱包。',
                'succeeded': '提现已确认完成，请核对实际收款。\n如有疑问，可以联系售后。',
            }.get(state, '资金执行结果尚未确认。\n请查询记录，不要重复申请。')
        else:
            heading, rows, body = title, data.get('rows', []), data.get('body', '')
        y = c.title(y, heading)
        if rows:
            c.card(y, len(rows) * 88 + 16)
            for label, value in rows:
                c.row(y + 8, label, value)
                y += 88
            y += 40
        if body:
            c.txt(32, y, body, 28, 'secondary')
        if data.get('action'):
            c.button(data['action'])
        elif kind == 'withdraw-detail':
            c.button('刷新记录', secondary='联系售后')
    elif kind in ['wallets', 'wallet']:
        y = c.title(y, '我的钱包' if kind == 'wallets' else ('消费钱包' if data.get('wallet_type') == 'consumption' else '佣金钱包'))
        types = ['commission', 'consumption'] if kind == 'wallets' else [data.get('wallet_type', 'commission')]
        for wallet_type in types:
            c.card(y, 288)
            c.txt(56, y + 24, '佣金可用金额' if wallet_type == 'commission' else '消费可用金额', 28, bold=True)
            c.txt(56, y + 82, '¥268.00' if wallet_type == 'commission' else '¥36.00', 44, 'primary', True)
            c.txt(56, y + 170, '冻结金额', 24, 'secondary')
            c.txt(56, y + 212, '¥100.00' if wallet_type == 'commission' else '¥0.00', 32, bold=True)
            c.txt(390, y + 170, '欠款金额', 24, 'secondary')
            c.txt(390, y + 212, '¥12.00' if data.get('debt') else '¥0.00', 32, 'primary' if data.get('debt') else 'text', True)
            y += 312
        if data.get('debt'):
            y = c.notice(y, '存在欠款，当前不能申请提现')
        c.card(y, 184)
        c.row(y + 4, '佣金记录', arrow=True)
        c.row(y + 92, '提现记录', arrow=True)
        y += 208
        c.txt(32, y, '两类钱包分别记账，不提供充值、互转或抵扣。\n提现服务未开放时只查询余额与历史记录。', 24, 'secondary')
        if kind == 'wallet' and types[0] == 'commission':
            c.button('提现暂未开放', True)
    elif kind == 'withdraw-form':
        y = c.notice(y, '提现服务暂未开放，当前不能提交申请')
        c.card(y, 200)
        c.txt(56, y + 24, '佣金钱包可用金额', 28)
        c.txt(56, y + 86, '¥268.00', 44, 'primary', True)
        y += 224
        c.card(y, 204)
        c.txt(56, y + 24, '提现金额', 28, bold=True)
        c.txt(56, y + 96, '¥  100.00', 44)
        y += 228
        c.card(y, 160)
        c.txt(56, y + 24, '收款目标', 28, bold=True)
        c.txt(56, y + 84, '收款方式接通后展示脱敏引用', 26, 'secondary')
        c.txt(32, y + 204, '存在欠款或余额不足时不能申请。\n金额精确到分，不承诺自动或即时到账。', 26, 'secondary')
        c.button('提现暂未开放', True)
    elif kind == 'membership':
        y = c.title(y, '会员与分销')
        c.card(y, 264)
        c.txt(56, y + 24, '本人分销档案', 32, bold=True)
        c.txt(56, y + 88, '邀请码：DEMO1234', 32, 'primary', True)
        c.txt(56, y + 152, '会员待遇与商品报价以服务端资格为准。', 24, 'secondary')
        y += 288
        c.card(y, 392)
        for label in ['推荐关系', '分享邀请', '佣金记录', '我的钱包']:
            c.row(y + 8, label, arrow=True)
            y += 96
        c.txt(32, y + 40, '开通档案不承诺等级或收益。\n佣金仅按已确认交易记录展示。', 26, 'secondary')
    elif kind == 'share':
        y = c.title(y, '分享邀请', '由你主动发起分享')
        c.card(y, 342)
        c.txt(56, y + 38, '我的邀请码', 28, bold=True)
        c.txt(56, y + 112, 'DEMO1234', 44, 'primary', True)
        c.txt(56, y + 208, '分享参数仅代表邀请意图。\n对方确认后由服务端校验首次绑定。', 26, 'secondary')
        c.txt(32, y + 394, '本设计不生成二维码或承诺邀请收益。\n无效或失效分享保持明确反馈。', 26, 'secondary')
        c.button('分享能力待接通', True)
    elif kind == 'content':
        y = c.title(y, '商品说明与详情')
        c.card(y, 226)
        c.txt(56, y + 24, '基础圆领款式', 32, bold=True)
        c.txt(56, y + 90, '材质与参数以商品公开资料为准。\n说明与详情图集分别展示。', 28, 'secondary')
        y += 250
        c.im.paste(ui.garment((686, 514)), (32, y))
        y += 542
        c.card(y, 176)
        c.row(y + 4, '颜色', '白色 / 黑色 / 灰色')
        c.row(y + 92, '评价', '查看公开评价', True)
    elif kind == 'virtual':
        y = c.title(y, '虚拟商品示例', '虚拟交付，无需配送地址')
        c.card(y, 424)
        ui.icon(c.im, 300, y + 74, 'phone', 'primary', 150)
        c.txt(56, y + 300, '商品封面示意', 28, 'secondary')
        y += 448
        c.card(y, 212)
        c.txt(56, y + 24, '¥129.00', 44, 'primary', True)
        c.txt(56, y + 112, '按成交订单查看已授权的交付信息。', 26, 'secondary')
        c.button('进入结算')
    elif kind == 'image':
        c.im = Image.new('RGB', (750, 1624), '#131517')
        c.im.paste(ui.garment((750, 900)), (0, 330))
        ui.text(c.im, (375, 180), '1 / 3', 32, 'surface', anchor='mm')
        ui.icon(c.im, 32, 100, 'close', 'surface')
        ui.text(c.im, (375, 1390), '轻触关闭 · 双指缩放示意', 26, 'surface', anchor='mm')
        return c.im
    elif kind in ['dialog', 'sheet']:
        base_kind = data.get('base', 'mine')
        base = {'kind': base_kind, 'title': {'cart': '购物车', 'checkout': '确认订单', 'order': '订单详情', 'profile': '个人资料', 'membership': '会员与分销', 'address-list': '收货地址', 'address-form': '编辑地址', 'sessions': '登录设备', 'mine': '我的'}[base_kind], 'data': {'state': data.get('base_state', 'pending')}}
        im = render(base)
        im = Image.alpha_composite(im.convert('RGBA'), Image.new('RGBA', im.size, (0, 0, 0, 105))).convert('RGB')
        if kind == 'sheet':
            ui.box(im, (0, 1112, 750, 1650), radius=24)
            for i, label in enumerate(data['choices'] + ['取消']):
                ui.text(im, (375, 1172 + i * 112), label, 28, 'primary' if i == 2 else 'text', anchor='mm')
                ui.line(im, [(32, 1228 + i * 112), (718, 1228 + i * 112)], width=1)
        else:
            ui.box(im, (56, 532, 694, 1038), radius=24)
            ui.text(im, (88, 580), data['heading'], 32, bold=True)
            temp = Canvas('')
            temp.im = im
            temp.txt(88, 656, data['body'], 28, 'secondary', max_width=574)
            ui.box(im, (88, 906, 351, 994), 'background', 12)
            ui.text(im, (219, 950), '取消', 28, anchor='mm')
            ui.box(im, (375, 906, 662, 994), 'primary', 12)
            ui.text(im, (518, 950), data['confirm'], 28, 'surface', True, 'mm')
        return im
    elif kind in ['result', 'state']:
        state = data.get('state')
        if state == 'loading':
            y = c.title(y, '正在加载')
            for i in range(3):
                c.card(y, 244)
                ui.box(c.im, (56, y + 28, 216, y + 188), 'border', 12)
                for j, width in enumerate([414, 302, 214]):
                    ui.box(c.im, (240, y + 30 + j * 54, 240 + width, y + 58 + j * 54), 'background', 8)
                y += 268
            c.txt(32, y + 16, '等待查询结果，不提前显示空数据。', 24, 'secondary')
        else:
            headings = {'error': '加载失败，请重试', 'empty': '暂时没有相关内容', 'login': '登录后查看本人内容'}
            messages = {'error': '查询未完成，请检查网络或稍后重试。\n失败不会被当作空列表。', 'empty': '当前查询成功，但没有符合条件的记录。\n可以返回上一页继续操作。', 'login': '公开商品仍可浏览。\n登录只恢复上下文，不自动提交写操作。'}
            actions = {'error': '重试查询', 'empty': '返回上一页', 'login': '主动登录'}
            if state == 'empty':
                empty_copy = {
                    'home': ('暂时没有上架商品', '商城暂时没有可浏览的商品。\n你可以稍后再刷新查看。', '刷新商品'),
                    'category': ('这个分类暂无商品', '当前分类没有可浏览的商品。\n可以选择其他分类继续浏览。', '返回分类'),
                    'product': ('商品暂时无法浏览', '当前商品已下架或不存在。\n你可以返回商城继续浏览。', '返回商城'),
                    'cart': ('购物车还是空的', '还没有加入购物车的商品。\n去商城选择你需要的商品吧。', '去逛逛'),
                    'orders-list': ('你还没有订单', '当前查询没有订单记录。\n可以先浏览商品再下单。', '浏览商品'),
                    'refund-history': ('本单暂无售后申请', '此订单没有退款申请记录。\n申请资格请以订单当前状态为准。', '查看订单'),
                    'reviews': ('暂无公开评价', '当前商品还没有公开评价。\n可以返回商品查看详细资料。', '返回商品'),
                    'sessions': ('当前页暂无设备记录', '此页未查询到登录设备。\n可以返回账号安全查看当前会话。', '返回账号安全'),
                    'addresses': ('还没有收货地址', '实物商品结算前需要本人收货地址。\n现在可以新增一条地址。', '新增收货地址'),
                    'membership': ('尚未开通分销档案', '当前账户还没有分销档案。\n可以查看说明后主动确认开通。', '查看开通说明'),
                    'commissions': ('暂无佣金记录', '当前查询没有佣金记录。\n收益只按后端已确认事实展示。', '返回钱包'),
                    'withdrawal-records': ('暂无提现记录', '当前查询没有提现申请。\n你可以返回钱包查看余额与服务状态。', '返回钱包'),
                }
                headings['empty'], messages['empty'], actions['empty'] = empty_copy[data['parent']]
            heading = headings.get(state, data.get('title_line', title))
            message = messages.get(state, data.get('message', ''))
            mood = data.get('mood', 'neutral')
            fill = '#16794A' if mood == 'success' else ('#8A4B08' if mood == 'warning' else ui.C['secondary'])
            ui.box(c.im, (303, 400, 447, 544), 'surface', 72)
            if mood == 'success':
                ui.line(c.im, [(343, 470), (367, 494), (411, 444)], fill, 7)
            else:
                ui.text(c.im, (375, 472), '!' if mood == 'warning' or state == 'error' else '·', 68, fill, anchor='mm')
            y = c.title(590, heading)
            c.txt(32, y, message, 28, 'secondary')
            c.button(actions.get(state, data.get('action', '返回上一页')), data.get('busy', False))
    else:
        raise ValueError(kind)
    return c.finish()


def gallery(version, pages, boards):
    nav = ''.join(f'<a href="#{g}">{html.escape(label)}</a>' for g, label in GROUPS.items())
    sections = []
    for group, label in GROUPS.items():
        figures = []
        for p in pages:
            if p['group'] != group:
                continue
            filename = p['file']
            api = '<br>'.join(html.escape(v) for v in p['api']) or '无独立消费端 API'
            figures.append(f'<figure><a href="{filename}" target="_blank"><img loading="lazy" src="{filename}" alt="{html.escape(p["title"])}"></a><figcaption><b>{p["number"]:03d} {html.escape(p["title"])}</b><p>{html.escape(STATUS[p["status"]])}</p><details><summary>接口与设计边界</summary><p>{html.escape(p["note"])}</p><code>{api}</code></details></figcaption></figure>')
        sections.append(f'<section id="{group}"><h2>{label}</h2><div class="grid">{"".join(figures)}</div></section>')
    return f'''<!doctype html>
<html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>拼捷商城小程序设计图集</title>
<style>body{{margin:0;background:#F7F8FA;color:#1D2939;font-family:system-ui,"Microsoft YaHei",sans-serif}}header,main{{max-width:1280px;margin:auto;padding:28px}}h1{{font-size:30px}}p{{line-height:1.7}}nav{{display:flex;gap:12px;flex-wrap:wrap}}a{{color:#B42318}}nav a{{padding:10px;background:white;border-radius:8px}}section{{scroll-margin-top:20px;margin:50px 0}}.grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:24px}}figure{{margin:0;background:white;border:1px solid #E4E7EC;border-radius:10px;overflow:hidden}}img{{width:100%;height:auto;display:block}}figcaption{{padding:18px}}figcaption p{{font-size:14px;color:#475467}}details{{font-size:14px}}code{{font-size:12px;overflow-wrap:anywhere}}footer{{padding:30px;text-align:center;color:#475467}}@media(max-width:850px){{.grid{{grid-template-columns:repeat(2,minmax(0,1fr))}}}}@media(max-width:520px){{.grid{{grid-template-columns:1fr}}header,main{{padding:18px}}}}</style>
<header><h1>拼捷商城 · 小程序完整设计图集 {version}</h1><p>共 {len(pages)} 张页面、弹层与状态图。视觉沿用已确认的 V1，扩展流程待评审。所有用户、商品、金额、地址、编号均为设计示例。这是图片浏览目录，未接 API，也不是可操作小程序或业务 HTML 原型。</p><nav>{nav}</nav><p>点击图片查看原图；展开下方说明核对后端能力。私有 API 当前使用浏览器 Cookie，尚需微信 Bearer 适配。真实支付、退款和自动打款尚未接通。</p></header><main>{''.join(sections)}</main><footer>本地离线文件，无外部资源、脚本、服务或追踪请求。静态图不能验证真实交互与真机表现。</footer></html>
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', default='v2')
    windows_fonts = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts'
    parser.add_argument('--font', type=Path, default=windows_fonts / 'msyh.ttc')
    parser.add_argument('--bold-font', type=Path, default=windows_fonts / 'msyhbd.ttc')
    args = parser.parse_args()
    if not args.version or not all(c.isalnum() or c == '-' for c in args.version):
        raise ValueError('Version must contain only letters, digits or hyphens')
    out = ROOT / 'screenshots' / args.version
    gallery_path = ROOT / f'gallery-{args.version}.html'
    catalog_path = ROOT / f'catalog-{args.version}.md'
    if out.exists() or gallery_path.exists() or catalog_path.exists():
        raise FileExistsError('Use a new version; existing design sets are preserved')
    ui.REGULAR, ui.BOLD = args.font, args.bold_font
    ui.FONTS.clear()
    configure()
    contract = json.loads((REPO / 'openapi.json').read_text(encoding='utf-8'))
    known = {f'{method.upper()} {path}' for path, operations in contract['paths'].items()
             for method in operations if method in ['get', 'post', 'put', 'patch', 'delete']}
    for p in PAGES:
        for route in p['api']:
            if route not in known or '/admin/' in route:
                raise ValueError(f'Invalid consumer API reference: {route}')
    rendered = []
    # Validate layouts entirely before creating any output assets.
    for number, p in enumerate(PAGES, 1):
        p['number'] = number
        p['file'] = f'screenshots/{args.version}/{p["group"]}/{number:03d}-{p["slug"]}.png'
        rendered.append((p, render(p)))
    out.mkdir(parents=True)
    for p, im in rendered:
        dest = ROOT / p['file']
        dest.parent.mkdir(parents=True, exist_ok=True)
        im.save(dest)
    boards = []
    for group, label in GROUPS.items():
        entries = [(p, im) for p, im in rendered if p['group'] == group]
        for start in range(0, len(entries), 6):
            board = Image.new('RGB', (1290, 1920), '#ECEDEA')
            ui.text(board, (30, 28), f'{label} / {args.version} / {start // 6 + 1}', 32, bold=True)
            ui.text(board, (30, 84), '全部内容为设计示例 · 扩展页面待评审 · 非微信运行截图', 24, 'secondary')
            for i, (p, im) in enumerate(entries[start:start + 6]):
                x, y = 30 + (i % 3) * 420, 144 + (i // 3) * 872
                label_text = f'{p["number"]:03d} {p["title"]}'
                label_size = 22
                while ImageDraw.Draw(board).textlength(label_text, font=ui.font(label_size, True)) > 375:
                    label_size -= 1
                    if label_size < 16:
                        raise ValueError('Board label is too long')
                ui.text(board, (x, y), label_text, label_size, bold=True)
                board.paste(im.resize((375, 812), Image.Resampling.LANCZOS), (x, y + 42))
            filename = f'screenshots/{args.version}/{group}-board-{start // 6 + 1:02d}.png'
            board.save(ROOT / filename)
            boards.append(filename)
    manifest = dict(version=args.version, purpose='static-design-metadata-not-api-contract',
                    count=len(PAGES), groups=GROUPS, status=STATUS, pages=PAGES, boards=boards)
    (out / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    gallery_path.write_text(gallery(args.version, PAGES, boards), encoding='utf-8')
    lines = ['# 小程序全页面设计目录 ' + args.version.upper(), '',
             f'共 {len(PAGES)} 张独立页面、弹层和状态图；所有内容为设计示例，扩展流程待评审。', '',
             f'离线浏览全部图片：[图片图集](gallery-{args.version}.html)。能力分层与源码证据见[接口映射说明](api-coverage.md)。本目录是图片索引，不定义 API/DTO。', '']
    for group, label in GROUPS.items():
        lines += [f'## {label}', '', '| 编号 | 页面/状态 | 图片 | 能力边界 |', '| --- | --- | --- | --- |']
        for p in PAGES:
            if p['group'] == group:
                lines.append(f'| {p["number"]:03d} | {p["title"]} | [查看图片]({p["file"]}) | {STATUS[p["status"]]} |')
        lines += ['', '分组总览：', '']
        for filename in boards:
            if group in filename:
                lines.append(f'- [总览 {Path(filename).stem}]({filename})')
        lines += ['']
    catalog_path.write_text('\n'.join(lines), encoding='utf-8')
    for p, im in rendered:
        with Image.open(ROOT / p['file']) as check:
            assert check.size == (750, 1624)
            check.verify()
    print(f'{len(PAGES)} screens, {len(boards)} boards; all cited routes exist in root OpenAPI')
    print(gallery_path)


if __name__ == '__main__':
    main()
