from typing import Annotated

from fastapi import Depends

from app.api.dependencies import CurrentUser, DatabaseSession, get_current_user
from app.services.cart import CartService
from app.services.orders import OrderService


def get_cart_service(session: DatabaseSession) -> CartService:
    return CartService(session)


def get_order_service(session: DatabaseSession) -> OrderService:
    return OrderService(session)


Cart = Annotated[CartService, Depends(get_cart_service)]
Orders = Annotated[OrderService, Depends(get_order_service)]
UserPrincipal = Annotated[CurrentUser, Depends(get_current_user)]
