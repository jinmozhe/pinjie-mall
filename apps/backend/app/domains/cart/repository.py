from uuid import UUID

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.cart import CartItem
from app.db.models.inventory import InventoryAccount
from app.db.models.product import Product, ProductSku


class CartRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def lock_user(self, user_id: UUID) -> None:
        await self.session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"pinjie:carts:{user_id}"},
        )

    async def available_quantity(self, sku_id: UUID) -> int | None:
        return (
            await self.session.scalars(
                select(InventoryAccount.available)
                .join(ProductSku, ProductSku.id == InventoryAccount.sku_id)
                .join(Product, Product.id == ProductSku.product_id)
                .where(ProductSku.id == sku_id, Product.status == "on_sale", ProductSku.is_active.is_(True))
            )
        ).one_or_none()

    async def list_for_user(self, user_id: UUID) -> list[CartItem]:
        return list(
            await self.session.scalars(
                select(CartItem).where(CartItem.user_id == user_id).order_by(CartItem.created_at, CartItem.id)
            )
        )

    async def get(self, user_id: UUID, item_id: UUID, *, lock: bool = False) -> CartItem | None:
        stmt = select(CartItem).where(CartItem.user_id == user_id, CartItem.id == item_id)
        if lock:
            stmt = stmt.with_for_update().execution_options(populate_existing=True)
        return (await self.session.scalars(stmt)).one_or_none()

    async def get_by_sku(self, user_id: UUID, sku_id: UUID, *, lock: bool = False) -> CartItem | None:
        stmt = select(CartItem).where(CartItem.user_id == user_id, CartItem.sku_id == sku_id)
        if lock:
            stmt = stmt.with_for_update().execution_options(populate_existing=True)
        return (await self.session.scalars(stmt)).one_or_none()

    async def save(self, item: CartItem) -> None:
        self.session.add(item)
        await self.session.flush()

    async def delete(self, item: CartItem) -> None:
        await self.session.delete(item)
        await self.session.flush()

    async def count_for_user(self, user_id: UUID) -> int:
        return int(
            await self.session.scalar(select(func.count()).select_from(CartItem).where(CartItem.user_id == user_id))
            or 0
        )

    async def clear_skus(self, user_id: UUID, sku_ids: list[UUID]) -> None:
        if sku_ids:
            await self.session.execute(
                delete(CartItem).where(CartItem.user_id == user_id, CartItem.sku_id.in_(sku_ids))
            )
