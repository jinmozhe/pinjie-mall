from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.dependencies import require_permission, require_web_csrf
from app.api.transaction_dependencies import Cart, Orders, UserPrincipal
from app.core.context import current_request_id
from app.core.response import ResponseModel, success_response
from app.domains.admin.permissions import PermissionCode
from app.domains.cart import CartItemInput, CartItemRead, CartItemUpdate
from app.domains.orders import CheckoutQuote, CheckoutRequest, OrderRead

router = APIRouter(tags=["交易"])


@router.get(
    "/admin/orders/{order_id}",
    response_model=ResponseModel[OrderRead],
    summary="查看管理订单详情",
    dependencies=[Depends(require_permission(PermissionCode.ORDERS_READ))],
)
async def admin_order_read(order_id: UUID, orders: Orders) -> ResponseModel[OrderRead]:
    return success_response(data=await orders.admin_read(order_id), request_id=current_request_id())


@router.get("/cart-items", response_model=ResponseModel[list[CartItemRead]], summary="查看本人购物车")
async def cart_list(cart: Cart, current: UserPrincipal) -> ResponseModel[list[CartItemRead]]:
    return success_response(data=await cart.list(current.user.id), request_id=current_request_id())


@router.post(
    "/cart-items",
    response_model=ResponseModel[CartItemRead],
    status_code=201,
    summary="加入购物车",
    dependencies=[Depends(require_web_csrf)],
)
async def cart_add(payload: CartItemInput, cart: Cart, current: UserPrincipal) -> ResponseModel[CartItemRead]:
    return success_response(data=await cart.add(current.user.id, payload), request_id=current_request_id())


@router.patch(
    "/cart-items/{item_id}",
    response_model=ResponseModel[CartItemRead],
    summary="修改购物车条目",
    dependencies=[Depends(require_web_csrf)],
)
async def cart_update(
    item_id: UUID, payload: CartItemUpdate, cart: Cart, current: UserPrincipal
) -> ResponseModel[CartItemRead]:
    return success_response(data=await cart.update(current.user.id, item_id, payload), request_id=current_request_id())


@router.delete(
    "/cart-items/{item_id}",
    response_model=ResponseModel[None],
    summary="删除购物车条目",
    dependencies=[Depends(require_web_csrf)],
)
async def cart_delete(item_id: UUID, cart: Cart, current: UserPrincipal) -> ResponseModel[None]:
    await cart.remove(current.user.id, item_id)
    return success_response(data=None, request_id=current_request_id())


@router.post(
    "/checkout/preview",
    response_model=ResponseModel[CheckoutQuote],
    summary="服务端结算预览",
    dependencies=[Depends(require_web_csrf)],
)
async def checkout_preview(
    payload: CheckoutRequest, orders: Orders, current: UserPrincipal
) -> ResponseModel[CheckoutQuote]:
    return success_response(data=await orders.preview(current.user.id, payload), request_id=current_request_id())


@router.post(
    "/orders",
    response_model=ResponseModel[OrderRead],
    status_code=201,
    summary="创建待付款订单",
    dependencies=[Depends(require_web_csrf)],
)
async def order_create(payload: CheckoutRequest, orders: Orders, current: UserPrincipal) -> ResponseModel[OrderRead]:
    return success_response(data=await orders.create(current.user.id, payload), request_id=current_request_id())


@router.get("/orders/{order_id}", response_model=ResponseModel[OrderRead], summary="查看本人订单")
async def order_read(order_id: UUID, orders: Orders, current: UserPrincipal) -> ResponseModel[OrderRead]:
    # 资源归属校验：orders.read 内部通过 repository.order(user_id, order_id)
    # 联合过滤 user_id + order_id，非本人订单返回 404，不存在 IDOR 越权风险。
    return success_response(data=await orders.read(current.user.id, order_id), request_id=current_request_id())


@router.post(
    "/orders/{order_id}/cancel",
    response_model=ResponseModel[OrderRead],
    summary="取消本人待付款订单",
    dependencies=[Depends(require_web_csrf)],
)
async def order_cancel(order_id: UUID, orders: Orders, current: UserPrincipal) -> ResponseModel[OrderRead]:
    return success_response(data=await orders.cancel(current.user.id, order_id), request_id=current_request_id())
