from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.order import Order, OrderEvent, OrderItem


class OrderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def lock_user_checkout(self, user_id: UUID) -> None:
        await self.session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"pinjie:orders:{user_id}"},
        )

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
            await self.session.scalars(select(OrderItem).where(OrderItem.order_id == order_id).order_by(OrderItem.id))
        )

    async def item(self, order_item_id: UUID) -> OrderItem | None:
        return await self.session.get(OrderItem, order_item_id)

    async def page(self, page: int, page_size: int) -> tuple[list[Order], int]:
        count = int(await self.session.scalar(select(func.count()).select_from(Order)) or 0)
        rows = await self.session.scalars(
            select(Order).order_by(Order.id.desc()).offset((page - 1) * page_size).limit(page_size)
        )
        return list(rows), count

    async def save(self, value: Order | OrderItem | OrderEvent) -> None:
        self.session.add(value)
        await self.session.flush()
