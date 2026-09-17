from datetime import datetime
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.address import UserAddress
from app.db.models.inventory import InventoryAccount
from app.db.models.order import Order, OrderEvent, OrderItem
from app.db.models.product import Product, ProductSku
from app.db.models.reservation import InventoryReservation
from app.db.models.shipping import ShippingTemplate


class OrderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def lock_user_checkout(self, user_id: UUID) -> None:
        await self.session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"pinjie:orders:{user_id}"},
        )

    async def lock_catalog(self) -> None:
        await self.session.execute(text("SELECT pg_advisory_xact_lock(722341901)"))

    async def catalog(
        self, sku_ids: list[UUID], *, lock: bool = False
    ) -> list[tuple[ProductSku, Product, ShippingTemplate | None]]:
        if not sku_ids:
            return []
        stmt = (
            select(ProductSku, Product, ShippingTemplate)
            .join(Product, Product.id == ProductSku.product_id)
            .outerjoin(ShippingTemplate, ShippingTemplate.id == Product.shipping_template_id)
            .where(ProductSku.id.in_(sku_ids))
            .order_by(ProductSku.id)
        )
        if lock:
            stmt = stmt.with_for_update(of=ProductSku).execution_options(populate_existing=True)
        rows = await self.session.execute(stmt)
        return [(sku, product, template) for sku, product, template in rows.tuples()]

    async def lock_templates(self, template_ids: list[UUID]) -> list[ShippingTemplate]:
        if not template_ids:
            return []
        return list(
            await self.session.scalars(
                select(ShippingTemplate)
                .where(ShippingTemplate.id.in_(template_ids))
                .order_by(ShippingTemplate.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        )

    async def address(self, user_id: UUID, address_id: UUID, *, lock: bool = False) -> UserAddress | None:
        stmt = select(UserAddress).where(UserAddress.user_id == user_id, UserAddress.id == address_id)
        if lock:
            stmt = stmt.with_for_update().execution_options(populate_existing=True)
        return (await self.session.scalars(stmt)).one_or_none()

    async def order_by_request(self, user_id: UUID, request_id: UUID, *, lock: bool = False) -> Order | None:
        stmt = select(Order).where(Order.user_id == user_id, Order.request_id == request_id)
        if lock:
            stmt = stmt.with_for_update().execution_options(populate_existing=True)
        return (await self.session.scalars(stmt)).one_or_none()

    async def order(self, user_id: UUID, order_id: UUID, *, lock: bool = False) -> Order | None:
        stmt = select(Order).where(Order.user_id == user_id, Order.id == order_id)
        if lock:
            stmt = stmt.with_for_update().execution_options(populate_existing=True)
        return (await self.session.scalars(stmt)).one_or_none()

    async def order_by_id(self, order_id: UUID, *, lock: bool = False) -> Order | None:
        stmt = select(Order).where(Order.id == order_id)
        if lock:
            stmt = stmt.with_for_update().execution_options(populate_existing=True)
        return (await self.session.scalars(stmt)).one_or_none()

    async def count_expired(self, now: datetime) -> int:
        from sqlalchemy import func

        return int(
            await self.session.scalar(
                select(func.count())
                .select_from(Order)
                .where(Order.status == "pending_payment", Order.expires_at <= now)
            )
            or 0
        )

    async def expired_orders(self, now: datetime, limit: int) -> list[Order]:
        return list(
            await self.session.scalars(
                select(Order)
                .where(Order.status == "pending_payment", Order.expires_at <= now)
                .order_by(Order.expires_at, Order.id)
                .limit(limit)
                .with_for_update(skip_locked=True)
                .execution_options(populate_existing=True)
            )
        )

    async def items(self, order_id: UUID) -> list[OrderItem]:
        return list(
            await self.session.scalars(
                select(OrderItem).where(OrderItem.order_id == order_id).order_by(OrderItem.created_at, OrderItem.id)
            )
        )

    async def reservations(self, order_id: UUID, *, lock: bool = False) -> list[InventoryReservation]:
        stmt = (
            select(InventoryReservation)
            .where(InventoryReservation.order_id == order_id)
            .order_by(InventoryReservation.sku_id)
        )
        if lock:
            stmt = stmt.with_for_update().execution_options(populate_existing=True)
        return list(await self.session.scalars(stmt))

    async def inventory_accounts(self, sku_ids: list[UUID]) -> list[InventoryAccount]:
        if not sku_ids:
            return []
        return list(
            await self.session.scalars(
                select(InventoryAccount)
                .where(InventoryAccount.sku_id.in_(sku_ids))
                .order_by(InventoryAccount.sku_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        )

    async def save(self, value: Order | OrderItem | OrderEvent | InventoryReservation) -> None:
        self.session.add(value)
        await self.session.flush()
