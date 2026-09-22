from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.core.identifiers import new_uuid7
from app.db.models.cart import CartItem
from app.db.transaction import transaction_scope
from app.domains.cart.repository import CartRepository
from app.domains.cart.schemas import CartItemInput, CartItemRead, CartItemUpdate
from app.domains.inventory import InventoryService
from app.domains.inventory.repository import InventoryRepository
from app.domains.products import ProductService
from app.domains.products.repository import ProductRepository
from app.domains.users import UserAccessService


class CartService:
    def __init__(
        self,
        session: AsyncSession,
        repository: CartRepository | None = None,
        *,
        access: UserAccessService | None = None,
    ) -> None:
        self.session = session
        self.repository = repository or CartRepository(session)
        self.access = access or UserAccessService(session)
        self.products = ProductService(ProductRepository(session))
        self.inventory = InventoryService(InventoryRepository(session))

    async def _available(self, sku_id: UUID) -> int:
        await self.products.checkout_skus([sku_id])
        return (await self.inventory.read(sku_id)).available

    async def list(self, user_id: UUID) -> list[CartItemRead]:
        await self.access.require_active_user(user_id)
        return [CartItemRead.model_validate(row) for row in await self.repository.list_for_user(user_id)]

    async def add(self, user_id: UUID, data: CartItemInput) -> CartItemRead:
        async with transaction_scope(self.session):
            await self.access.require_active_user(user_id)
            await self.repository.lock_user(user_id)
            available = await self._available(data.sku_id)
            if available is None or available < data.quantity:
                raise AppException(status_code=409, code=ErrorCode.CHECKOUT_INVALID, message="商品不可售或库存不足")
            existing = await self.repository.get_by_sku(user_id, data.sku_id, lock=True)
            if existing is not None:
                if existing.quantity + data.quantity > 999:
                    raise AppException(
                        status_code=409, code=ErrorCode.CART_QUANTITY_REJECTED, message="购物车数量超过上限"
                    )
                if existing.quantity + data.quantity > available:
                    raise AppException(status_code=409, code=ErrorCode.CHECKOUT_INVALID, message="商品库存不足")
                existing.quantity += data.quantity
                existing.revision += 1
                await self.repository.save(existing)
                return CartItemRead.model_validate(existing)
            if await self.repository.count_for_user(user_id) >= 100:
                raise AppException(status_code=409, code=ErrorCode.CART_LIMIT, message="购物车条目达到上限")
            row = CartItem(
                id=new_uuid7(), user_id=user_id, sku_id=data.sku_id, quantity=data.quantity, selected=True, revision=1
            )
            await self.repository.save(row)
            return CartItemRead.model_validate(row)

    async def update(self, user_id: UUID, item_id: UUID, data: CartItemUpdate) -> CartItemRead:
        async with transaction_scope(self.session):
            await self.access.require_active_user(user_id)
            await self.repository.lock_user(user_id)
            row = await self.repository.get(user_id, item_id, lock=True)
            if row is None:
                raise AppException(status_code=404, code=ErrorCode.CART_ITEM_NOT_FOUND, message="购物车条目不存在")
            if row.revision != data.revision:
                raise AppException(
                    status_code=409, code=ErrorCode.CART_REVISION_CONFLICT, message="购物车已变更，请重新读取"
                )
            if data.quantity is not None:
                available = await self._available(row.sku_id)
                if available is None or data.quantity > available:
                    raise AppException(status_code=409, code=ErrorCode.CHECKOUT_INVALID, message="商品不可售或库存不足")
                row.quantity = data.quantity
            if data.selected is not None:
                row.selected = data.selected
            row.revision += 1
            await self.repository.save(row)
            return CartItemRead.model_validate(row)

    async def remove(self, user_id: UUID, item_id: UUID) -> None:
        async with transaction_scope(self.session):
            await self.access.require_active_user(user_id)
            await self.repository.lock_user(user_id)
            row = await self.repository.get(user_id, item_id, lock=True)
            if row is None:
                raise AppException(status_code=404, code=ErrorCode.CART_ITEM_NOT_FOUND, message="购物车条目不存在")
            await self.repository.delete(row)
