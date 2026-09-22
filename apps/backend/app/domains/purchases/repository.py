from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.purchase import ProductPurchaseLimit, ProductPurchaseRecord


class PurchaseLimitRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def records(self, order_id: UUID) -> list[ProductPurchaseRecord]:
        return list(
            await self.session.scalars(
                select(ProductPurchaseRecord)
                .where(ProductPurchaseRecord.order_id == order_id)
                .order_by(ProductPurchaseRecord.product_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        )

    async def account(self, user_id: UUID, product_id: UUID) -> ProductPurchaseLimit | None:
        return (
            await self.session.scalars(
                select(ProductPurchaseLimit)
                .where(ProductPurchaseLimit.user_id == user_id, ProductPurchaseLimit.product_id == product_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).one_or_none()

    async def save(self, row: ProductPurchaseLimit | ProductPurchaseRecord) -> None:
        self.session.add(row)
        await self.session.flush()
