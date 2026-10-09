from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, UploadFile
from pydantic import BaseModel

from app.api.dependencies import AssetServiceDependency
from app.api.lifecycle_dependencies import Lifecycle
from app.api.miniapp_dependencies import (
    MiniappAddresses,
    MiniappAuth,
    MiniappAvatarUploader,
    MiniappEngagement,
    MiniappFinance,
    MiniappHelp,
    MiniappPrincipal,
    MiniappProfile,
    MiniappTrade,
    require_miniapp_profile,
)
from app.api.transaction_dependencies import Cart, Orders
from app.core.context import current_request_id
from app.core.identifiers import new_uuid7
from app.core.pagination import PageResult
from app.core.response import ResponseModel, success_response
from app.domains.addresses import AddressInput, AddressRead, AddressUpdate
from app.domains.assets.schemas import UploadScene
from app.domains.auth.miniapp_schemas import (
    MiniappCapabilitiesRead,
    MiniappLoginIn,
    MiniappRefreshIn,
    MiniappSessionRead,
    MiniappUserRead,
)
from app.domains.cart.schemas import CartItemInput, CartItemRead, CartItemUpdate, MiniappCartItemRead
from app.domains.distribution import ReferralBindIn
from app.domains.lifecycle.schemas import (
    FulfillmentRead,
    ProductReviewCreate,
    ProductReviewRead,
    ReceiptConfirm,
    RefundRequestCreate,
    RefundRequestRead,
)
from app.domains.orders import CheckoutQuote, CheckoutRequest, OrderRead
from app.domains.users.schemas import UserAvatarUpdateIn, UserUpdateIn
from app.services.miniapp_engagement_schemas import (
    MiniappPointsLedgerRead,
    MiniappPointsRead,
    MiniappReferralRead,
)
from app.services.miniapp_finance_schemas import (
    MiniappAvatarAssetRead,
    MiniappAvatarUpdate,
    MiniappCommissionRead,
    MiniappMemberRead,
    MiniappProfileUpdate,
    MiniappWalletLedgerRead,
    MiniappWalletRead,
    MiniappWithdrawalRead,
    WalletType,
)
from app.services.miniapp_trade_schemas import (
    MiniappHelpRead,
    MiniappRefundLookupRead,
    MiniappRefundRead,
    MiniappTradeOrderRead,
    TradeFilter,
)


class MiniappCheckoutIntentRead(BaseModel):
    request_id: UUID


router = APIRouter(prefix="/miniapp", tags=["小程序"], dependencies=[Depends(require_miniapp_profile)])


@router.get("/referral", response_model=ResponseModel[MiniappReferralRead], summary="查询本人推荐码及绑定事实")
async def referral(
    service: MiniappEngagement,
    current: MiniappPrincipal,
    invitation_code: str | None = Query(default=None, min_length=8, max_length=16, pattern=r"^[A-Z0-9]+$"),
) -> ResponseModel[MiniappReferralRead]:
    return success_response(
        data=await service.referral(current.user.id, invitation_code), request_id=current_request_id()
    )


@router.post(
    "/referral",
    response_model=ResponseModel[MiniappReferralRead],
    summary="主动首次绑定本人推荐关系",
    description="服务端校验首次绑定、自邀与循环；同码幂等。未知结果查询本人关系与原码是否匹配，不自动换码重试。",
)
async def referral_bind(
    payload: ReferralBindIn, service: MiniappEngagement, current: MiniappPrincipal
) -> ResponseModel[MiniappReferralRead]:
    return success_response(data=await service.bind(current.user.id, payload), request_id=current_request_id())


@router.get("/points", response_model=ResponseModel[MiniappPointsRead], summary="查询本人积分账户与精确余额")
async def points(service: MiniappEngagement, current: MiniappPrincipal) -> ResponseModel[MiniappPointsRead]:
    return success_response(data=await service.points(current.user.id), request_id=current_request_id())


@router.get(
    "/points/ledgers",
    response_model=ResponseModel[PageResult[MiniappPointsLedgerRead]],
    summary="分页查询本人积分流水安全投影",
)
async def points_ledgers(
    service: MiniappEngagement,
    current: MiniappPrincipal,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
) -> ResponseModel[PageResult[MiniappPointsLedgerRead]]:
    return success_response(
        data=await service.points_ledgers(current.user.id, page, page_size), request_id=current_request_id()
    )


@router.patch("/me", response_model=ResponseModel[MiniappUserRead], summary="修改本人小程序昵称")
async def profile_update(
    payload: MiniappProfileUpdate, service: MiniappProfile, current: MiniappPrincipal
) -> ResponseModel[MiniappUserRead]:
    user = await service.update_profile(current.user.id, UserUpdateIn(display_name=payload.display_name))
    return success_response(data=MiniappUserRead.model_validate(user), request_id=current_request_id())


@router.put("/me/avatar", response_model=ResponseModel[MiniappUserRead], summary="绑定或移除本人头像资产")
async def avatar_update(
    payload: MiniappAvatarUpdate, service: MiniappProfile, current: MiniappPrincipal
) -> ResponseModel[MiniappUserRead]:
    user = await service.update_avatar(current.user.id, UserAvatarUpdateIn(asset_id=payload.asset_id))
    return success_response(data=MiniappUserRead.model_validate(user), request_id=current_request_id())


@router.post(
    "/me/avatar-assets",
    response_model=ResponseModel[MiniappAvatarAssetRead],
    status_code=201,
    summary="上传本人头像资产",
    description="仅允许 avatar 场景；复用类型、体积及存储校验，只返回资产标识和公开地址，上传不自动绑定头像。",
)
async def avatar_upload(
    file: Annotated[UploadFile, File()], uploader: MiniappAvatarUploader, service: AssetServiceDependency
) -> ResponseModel[MiniappAvatarAssetRead]:
    asset = await service.upload(
        source=file.file, original_name=file.filename or "", scene=UploadScene.AVATAR, uploader=uploader
    )
    return success_response(data=MiniappAvatarAssetRead.model_validate(asset), request_id=current_request_id())


@router.get("/membership", response_model=ResponseModel[MiniappMemberRead], summary="读取本人档案和会员等级有效状态")
async def membership(service: MiniappFinance, current: MiniappPrincipal) -> ResponseModel[MiniappMemberRead]:
    return success_response(data=await service.member(current.user.id), request_id=current_request_id())


@router.post("/membership", response_model=ResponseModel[MiniappMemberRead], summary="主动幂等开通本人会员分销档案")
async def membership_activate(service: MiniappFinance, current: MiniappPrincipal) -> ResponseModel[MiniappMemberRead]:
    return success_response(data=await service.activate(current.user.id), request_id=current_request_id())


@router.get("/wallets", response_model=ResponseModel[list[MiniappWalletRead]], summary="查询本人双轨钱包")
async def wallets(service: MiniappFinance, current: MiniappPrincipal) -> ResponseModel[list[MiniappWalletRead]]:
    return success_response(data=await service.wallets(current.user.id), request_id=current_request_id())


@router.get(
    "/wallets/{wallet_type}/ledgers",
    response_model=ResponseModel[PageResult[MiniappWalletLedgerRead]],
    summary="分页查询本人指定轨道钱包流水",
)
async def wallet_ledgers(
    wallet_type: WalletType,
    service: MiniappFinance,
    current: MiniappPrincipal,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
) -> ResponseModel[PageResult[MiniappWalletLedgerRead]]:
    return success_response(
        data=await service.ledgers(current.user.id, wallet_type, page, page_size), request_id=current_request_id()
    )


@router.get(
    "/commissions", response_model=ResponseModel[PageResult[MiniappCommissionRead]], summary="分页查询本人安全佣金记录"
)
async def commissions(
    service: MiniappFinance,
    current: MiniappPrincipal,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
) -> ResponseModel[PageResult[MiniappCommissionRead]]:
    return success_response(
        data=await service.commissions(current.user.id, page, page_size), request_id=current_request_id()
    )


@router.get(
    "/withdrawals",
    response_model=ResponseModel[PageResult[MiniappWithdrawalRead]],
    summary="分页查询本人历史提现审核和确认事实",
)
async def withdrawals(
    service: MiniappFinance,
    current: MiniappPrincipal,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
) -> ResponseModel[PageResult[MiniappWithdrawalRead]]:
    return success_response(
        data=await service.withdrawals(current.user.id, page, page_size), request_id=current_request_id()
    )


@router.get("/help", response_model=ResponseModel[MiniappHelpRead], summary="查询公开支持联系方式")
async def help_read(help_info: MiniappHelp) -> ResponseModel[MiniappHelpRead]:
    return success_response(data=help_info, request_id=current_request_id())


@router.get(
    "/trade-orders",
    response_model=ResponseModel[PageResult[MiniappTradeOrderRead]],
    summary="按订单与履约事实分页本人订单",
)
async def trade_orders(
    trade: MiniappTrade,
    current: MiniappPrincipal,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    status: TradeFilter | None = None,
) -> ResponseModel[PageResult[MiniappTradeOrderRead]]:
    return success_response(
        data=await trade.orders(current.user.id, page, page_size, status), request_id=current_request_id()
    )


@router.get(
    "/trade-orders/{order_id}",
    response_model=ResponseModel[MiniappTradeOrderRead],
    summary="读取本人订单履约与操作资格",
)
async def trade_order(
    order_id: UUID, trade: MiniappTrade, current: MiniappPrincipal
) -> ResponseModel[MiniappTradeOrderRead]:
    return success_response(data=await trade.order(current.user.id, order_id), request_id=current_request_id())


@router.post(
    "/orders/{order_id}/receipt", response_model=ResponseModel[FulfillmentRead], summary="按版本确认本人实物订单收货"
)
async def receipt(
    order_id: UUID, payload: ReceiptConfirm, lifecycle: Lifecycle, current: MiniappPrincipal
) -> ResponseModel[FulfillmentRead]:
    return success_response(
        data=await lifecycle.confirm_receipt(current.user.id, order_id, payload.revision),
        request_id=current_request_id(),
    )


@router.get("/refunds/intent", response_model=ResponseModel[MiniappCheckoutIntentRead], summary="取得新的退款请求号")
async def refund_intent(current: MiniappPrincipal) -> ResponseModel[MiniappCheckoutIntentRead]:
    return success_response(data=MiniappCheckoutIntentRead(request_id=new_uuid7()), request_id=current_request_id())


@router.post(
    "/orders/{order_id}/refunds",
    response_model=ResponseModel[RefundRequestRead],
    status_code=201,
    summary="幂等申请本人未发货或未交付整单退款",
)
async def refund_create(
    order_id: UUID, payload: RefundRequestCreate, lifecycle: Lifecycle, current: MiniappPrincipal
) -> ResponseModel[RefundRequestRead]:
    return success_response(
        data=await lifecycle.create_refund(current.user.id, order_id, payload), request_id=current_request_id()
    )


@router.get("/refunds", response_model=ResponseModel[PageResult[MiniappRefundRead]], summary="分页读取本人整单售后记录")
async def refund_list(
    trade: MiniappTrade,
    current: MiniappPrincipal,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    order_id: UUID | None = None,
) -> ResponseModel[PageResult[MiniappRefundRead]]:
    return success_response(
        data=await trade.refunds(current.user.id, page, page_size, order_id), request_id=current_request_id()
    )


@router.get(
    "/refunds/by-request/{request_id}",
    response_model=ResponseModel[MiniappRefundLookupRead],
    summary="按原请求号确认本人退款受理事实",
)
async def refund_lookup(
    request_id: UUID, trade: MiniappTrade, current: MiniappPrincipal
) -> ResponseModel[MiniappRefundLookupRead]:
    return success_response(
        data=await trade.refund_by_request(current.user.id, request_id), request_id=current_request_id()
    )


@router.get(
    "/refunds/{refund_id}", response_model=ResponseModel[MiniappRefundRead], summary="读取本人售后审核与资金事实"
)
async def refund_detail(
    refund_id: UUID, trade: MiniappTrade, current: MiniappPrincipal
) -> ResponseModel[MiniappRefundRead]:
    return success_response(data=await trade.refund(current.user.id, refund_id), request_id=current_request_id())


@router.post(
    "/order-items/{item_id}/review",
    response_model=ResponseModel[ProductReviewRead],
    status_code=201,
    summary="评价本人已交付订单明细",
)
async def review_create(
    item_id: UUID, payload: ProductReviewCreate, lifecycle: Lifecycle, current: MiniappPrincipal
) -> ResponseModel[ProductReviewRead]:
    return success_response(
        data=await lifecycle.create_review(current.user.id, item_id, payload), request_id=current_request_id()
    )


@router.get("/auth/capabilities", response_model=ResponseModel[MiniappCapabilitiesRead], summary="查询微信登录开放状态")
async def capabilities(auth: MiniappAuth) -> ResponseModel[MiniappCapabilitiesRead]:
    return success_response(
        data=MiniappCapabilitiesRead(login_enabled=auth.settings.miniapp_login_enabled), request_id=current_request_id()
    )


@router.post("/auth/login", response_model=ResponseModel[MiniappSessionRead], summary="微信凭证登录")
async def login(payload: MiniappLoginIn, auth: MiniappAuth) -> ResponseModel[MiniappSessionRead]:
    return success_response(data=await auth.login(payload.code), request_id=current_request_id())


@router.post("/auth/refresh", response_model=ResponseModel[MiniappSessionRead], summary="轮换小程序会话凭据")
async def refresh(payload: MiniappRefreshIn, auth: MiniappAuth) -> ResponseModel[MiniappSessionRead]:
    return success_response(data=await auth.refresh(payload.refresh_token), request_id=current_request_id())


@router.post("/auth/logout", response_model=ResponseModel[None], summary="退出小程序会话")
async def logout(auth: MiniappAuth, current: MiniappPrincipal) -> ResponseModel[None]:
    await auth.logout(current.user.id, current.login_session.id)
    return success_response(data=None, request_id=current_request_id())


@router.get("/me", response_model=ResponseModel[MiniappUserRead], summary="读取本人基础信息")
async def me(current: MiniappPrincipal) -> ResponseModel[MiniappUserRead]:
    return success_response(data=MiniappUserRead.model_validate(current.user), request_id=current_request_id())


@router.get("/cart-items", response_model=ResponseModel[list[MiniappCartItemRead]], summary="读取本人购物车展示数据")
async def cart_list(cart: Cart, current: MiniappPrincipal) -> ResponseModel[list[MiniappCartItemRead]]:
    return success_response(data=await cart.miniapp_list(current.user.id), request_id=current_request_id())


@router.post("/cart-items", response_model=ResponseModel[CartItemRead], status_code=201, summary="加入本人购物车")
async def cart_add(payload: CartItemInput, cart: Cart, current: MiniappPrincipal) -> ResponseModel[CartItemRead]:
    return success_response(data=await cart.add(current.user.id, payload), request_id=current_request_id())


@router.patch("/cart-items/{item_id}", response_model=ResponseModel[CartItemRead], summary="修改本人购物车条目")
async def cart_update(
    item_id: UUID, payload: CartItemUpdate, cart: Cart, current: MiniappPrincipal
) -> ResponseModel[CartItemRead]:
    return success_response(data=await cart.update(current.user.id, item_id, payload), request_id=current_request_id())


@router.delete("/cart-items/{item_id}", response_model=ResponseModel[None], summary="移除本人购物车条目")
async def cart_remove(item_id: UUID, cart: Cart, current: MiniappPrincipal) -> ResponseModel[None]:
    await cart.remove(current.user.id, item_id)
    return success_response(data=None, request_id=current_request_id())


@router.get("/addresses", response_model=ResponseModel[list[AddressRead]], summary="读取本人收货地址")
async def addresses_list(addresses: MiniappAddresses) -> ResponseModel[list[AddressRead]]:
    return success_response(data=await addresses.list_addresses(), request_id=current_request_id())


@router.post("/addresses", response_model=ResponseModel[AddressRead], status_code=201, summary="创建本人收货地址")
async def address_add(payload: AddressInput, addresses: MiniappAddresses) -> ResponseModel[AddressRead]:
    return success_response(data=await addresses.create(payload), request_id=current_request_id())


@router.put("/addresses/{address_id}", response_model=ResponseModel[AddressRead], summary="更新本人收货地址")
async def address_update(
    address_id: UUID, payload: AddressUpdate, addresses: MiniappAddresses
) -> ResponseModel[AddressRead]:
    return success_response(data=await addresses.update(address_id, payload), request_id=current_request_id())


@router.delete("/addresses/{address_id}", response_model=ResponseModel[None], summary="按版本删除本人收货地址")
async def address_remove(
    address_id: UUID, addresses: MiniappAddresses, revision: int = Query(gt=0)
) -> ResponseModel[None]:
    await addresses.delete(address_id, revision)
    return success_response(data=None, request_id=current_request_id())


@router.get("/checkout/intent", response_model=ResponseModel[MiniappCheckoutIntentRead], summary="取得新的结算请求号")
async def checkout_intent(current: MiniappPrincipal) -> ResponseModel[MiniappCheckoutIntentRead]:
    return success_response(data=MiniappCheckoutIntentRead(request_id=new_uuid7()), request_id=current_request_id())


@router.post("/checkout/preview", response_model=ResponseModel[CheckoutQuote], summary="获取服务端结算报价")
async def checkout_preview(
    payload: CheckoutRequest, orders: Orders, current: MiniappPrincipal
) -> ResponseModel[CheckoutQuote]:
    return success_response(data=await orders.preview(current.user.id, payload), request_id=current_request_id())


@router.post("/orders", response_model=ResponseModel[OrderRead], status_code=201, summary="幂等创建本人订单")
async def order_create(payload: CheckoutRequest, orders: Orders, current: MiniappPrincipal) -> ResponseModel[OrderRead]:
    return success_response(data=await orders.create(current.user.id, payload), request_id=current_request_id())


@router.get("/orders", response_model=ResponseModel[PageResult[OrderRead]], summary="分页筛选本人订单")
async def orders_list(
    orders: Orders,
    current: MiniappPrincipal,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    status: Literal["pending_payment", "paid", "cancelled"] | None = None,
) -> ResponseModel[PageResult[OrderRead]]:
    return success_response(
        data=await orders.user_page(current.user.id, page, page_size, status=status), request_id=current_request_id()
    )


@router.get(
    "/orders/by-request/{request_id}", response_model=ResponseModel[OrderRead], summary="按原请求号确认本人订单"
)
async def order_by_request(request_id: UUID, orders: Orders, current: MiniappPrincipal) -> ResponseModel[OrderRead]:
    return success_response(
        data=await orders.read_by_request(current.user.id, request_id), request_id=current_request_id()
    )


@router.get("/orders/{order_id}", response_model=ResponseModel[OrderRead], summary="读取本人订单详情")
async def order_read(order_id: UUID, orders: Orders, current: MiniappPrincipal) -> ResponseModel[OrderRead]:
    return success_response(data=await orders.read(current.user.id, order_id), request_id=current_request_id())


@router.post("/orders/{order_id}/cancel", response_model=ResponseModel[OrderRead], summary="取消本人待付款订单")
async def order_cancel(order_id: UUID, orders: Orders, current: MiniappPrincipal) -> ResponseModel[OrderRead]:
    return success_response(data=await orders.cancel(current.user.id, order_id), request_id=current_request_id())
