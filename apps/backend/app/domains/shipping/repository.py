from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.shipping import ShippingTemplate


class ShippingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, template_id: UUID, *, lock: bool = False) -> ShippingTemplate | None:
        stmt = select(ShippingTemplate).where(ShippingTemplate.id == template_id)
        if lock:
            stmt = stmt.with_for_update().execution_options(populate_existing=True)
        return (await self.session.scalars(stmt)).one_or_none()

    async def page(self, page: int, page_size: int) -> tuple[list[ShippingTemplate], int]:
        total = int(await self.session.scalar(select(func.count()).select_from(ShippingTemplate)) or 0)
        rows = await self.session.scalars(
            select(ShippingTemplate)
            .order_by(ShippingTemplate.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(rows), total

    async def save(self, template: ShippingTemplate) -> None:
        self.session.add(template)
        await self.session.flush()
