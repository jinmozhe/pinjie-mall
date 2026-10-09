from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.api.miniapp_dependencies import MiniappAddresses, MiniappAuth, MiniappPrincipal, require_miniapp_profile
from app.api.transaction_dependencies import Cart, Orders
from app.core.context import current_request_id
from app.core.identifiers import new_uuid7
from app.core.pagination import PageResult
from app.core.response import ResponseModel, success_response
from app.domains.addresses import AddressInput, AddressRead, AddressUpdate
from app.domains.auth.miniapp_schemas import (
    MiniappCapabilitiesRead,
    MiniappLoginIn,
    MiniappRefreshIn,
    MiniappSessionRead,
    MiniappUserRead,
)
from app.domains.cart.schemas import CartItemInput, CartItemRead, CartItemUpdate, MiniappCartItemRead
from app.domains.orders import CheckoutQuote, CheckoutRequest, OrderRead

router = APIRouter(prefix="/miniapp", tags=["小程序"], dependencies=[Depends(require_miniapp_profile)])


class MiniappCheckoutIntentRead(BaseModel):
    request_id: UUID


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
