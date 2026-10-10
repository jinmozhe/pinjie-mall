from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import UserPrincipal, require_permission
from app.api.transaction_dependencies import Cart, ConsumerTrade, Orders
from app.core.context import current_request_id
from app.core.identifiers import new_uuid7
from app.core.pagination import PageResult
from app.core.response import ResponseModel, success_response
from app.domains.admin.permissions import PermissionCode
from app.domains.cart import CartItemInput, CartItemRead, CartItemUpdate
from app.domains.cart.schemas import ConsumerCartItemRead
from app.domains.orders import CheckoutQuote, CheckoutRequest, OrderRead
from app.domains.orders.schemas import OperationIntentRead
from app.services.trade_query_schemas import (
    ConsumerTradeOrderRead,
    TradeFilter,
)

router = APIRouter(tags=["交易"])


@router.get(
    "/admin/orders/{order_id}",
    response_model=ResponseModel[OrderRead],
    summary="查看管理订单详情",
    dependencies=[Depends(require_permission(PermissionCode.ORDERS_READ))],
)
async def admin_order_read(order_id: UUID, orders: Orders) -> ResponseModel[OrderRead]:
    return success_response(data=await orders.admin_read(order_id), request_id=current_request_id())


@router.get("/cart-items", response_model=ResponseModel[list[ConsumerCartItemRead]], summary="读取本人购物车展示数据")
async def cart_list(cart: Cart, current: UserPrincipal) -> ResponseModel[list[ConsumerCartItemRead]]:
    return success_response(data=await cart.list(current.user.id), request_id=current_request_id())


@router.post("/cart-items", response_model=ResponseModel[CartItemRead], status_code=201, summary="加入本人购物车")
async def cart_add(payload: CartItemInput, cart: Cart, current: UserPrincipal) -> ResponseModel[CartItemRead]:
    return success_response(data=await cart.add(current.user.id, payload), request_id=current_request_id())


@router.patch("/cart-items/{item_id}", response_model=ResponseModel[CartItemRead], summary="修改本人购物车条目")
async def cart_update(
    item_id: UUID, payload: CartItemUpdate, cart: Cart, current: UserPrincipal
) -> ResponseModel[CartItemRead]:
    return success_response(data=await cart.update(current.user.id, item_id, payload), request_id=current_request_id())


@router.delete("/cart-items/{item_id}", response_model=ResponseModel[None], summary="移除本人购物车条目")
async def cart_remove(item_id: UUID, cart: Cart, current: UserPrincipal) -> ResponseModel[None]:
    await cart.remove(current.user.id, item_id)
    return success_response(data=None, request_id=current_request_id())


@router.get("/checkout/intent", response_model=ResponseModel[OperationIntentRead], summary="取得新的结算请求号")
async def checkout_intent(current: UserPrincipal) -> ResponseModel[OperationIntentRead]:
    return success_response(data=OperationIntentRead(request_id=new_uuid7()), request_id=current_request_id())


@router.post("/checkout/preview", response_model=ResponseModel[CheckoutQuote], summary="获取服务端结算报价")
async def checkout_preview(
    payload: CheckoutRequest, orders: Orders, current: UserPrincipal
) -> ResponseModel[CheckoutQuote]:
    return success_response(data=await orders.preview(current.user.id, payload), request_id=current_request_id())


@router.post("/orders", response_model=ResponseModel[OrderRead], status_code=201, summary="幂等创建本人订单")
async def order_create(payload: CheckoutRequest, orders: Orders, current: UserPrincipal) -> ResponseModel[OrderRead]:
    return success_response(data=await orders.create(current.user.id, payload), request_id=current_request_id())


@router.get(
    "/orders/by-request/{request_id}", response_model=ResponseModel[OrderRead], summary="按原请求号确认本人订单"
)
async def order_by_request(request_id: UUID, orders: Orders, current: UserPrincipal) -> ResponseModel[OrderRead]:
    return success_response(
        data=await orders.read_by_request(current.user.id, request_id), request_id=current_request_id()
    )


@router.get(
    "/orders",
    response_model=ResponseModel[PageResult[ConsumerTradeOrderRead]],
    summary="按订单与履约事实分页本人订单",
)
async def trade_orders(
    trade: ConsumerTrade,
    current: UserPrincipal,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    status: TradeFilter | None = None,
) -> ResponseModel[PageResult[ConsumerTradeOrderRead]]:
    return success_response(
        data=await trade.orders(current.user.id, page, page_size, status), request_id=current_request_id()
    )


@router.get(
    "/orders/{order_id}",
    response_model=ResponseModel[ConsumerTradeOrderRead],
    summary="读取本人订单履约与操作资格",
)
async def trade_order(
    order_id: UUID, trade: ConsumerTrade, current: UserPrincipal
) -> ResponseModel[ConsumerTradeOrderRead]:
    return success_response(data=await trade.order(current.user.id, order_id), request_id=current_request_id())


@router.post("/orders/{order_id}/cancel", response_model=ResponseModel[OrderRead], summary="取消本人待付款订单")
async def order_cancel(order_id: UUID, orders: Orders, current: UserPrincipal) -> ResponseModel[OrderRead]:
    return success_response(data=await orders.cancel(current.user.id, order_id), request_id=current_request_id())
