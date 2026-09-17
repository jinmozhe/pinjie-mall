from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.inventory import InventoryAccount, InventoryMovement


class InventoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, sku_id: UUID, *, lock: bool = False) -> InventoryAccount | None:
        stmt = select(InventoryAccount).where(InventoryAccount.sku_id == sku_id)
        if lock:
            stmt = stmt.with_for_update().execution_options(populate_existing=True)
        return (await self.session.scalars(stmt)).one_or_none()

    async def movement(self, sku_id: UUID, request_id: UUID) -> InventoryMovement | None:
        return (
            await self.session.scalars(
                select(InventoryMovement).where(
                    InventoryMovement.sku_id == sku_id, InventoryMovement.request_id == request_id
                )
            )
        ).one_or_none()

    async def history(self, sku_id: UUID, page: int, page_size: int) -> tuple[list[InventoryMovement], int]:
        query = select(InventoryMovement).where(InventoryMovement.sku_id == sku_id)
        total = int(await self.session.scalar(select(func.count()).select_from(query.subquery())) or 0)
        rows = await self.session.scalars(
            query.order_by(InventoryMovement.created_at.desc(), InventoryMovement.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(rows), total

    async def save(self, value: InventoryAccount | InventoryMovement) -> None:
        self.session.add(value)
        await self.session.flush()
