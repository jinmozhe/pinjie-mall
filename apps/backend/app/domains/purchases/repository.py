from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.purchase import ProductPurchaseLimit, ProductPurchaseRecord


class PurchaseLimitRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def lock_account(self, user_id: UUID, product_id: UUID) -> None:
        """对 (user_id, product_id) 组合加事务级 advisory lock，防止账户并发创建冲突。"""
        # 取两个 UUID 整数值的低 32 位与高 32 位组合成两个 int4 作为锁键
        key1 = (user_id.int ^ (product_id.int >> 64)) & 0x7FFFFFFF
        key2 = (user_id.int ^ product_id.int) & 0x7FFFFFFF
        await self.session.execute(text("SELECT pg_advisory_xact_lock(:k1, :k2)"), {"k1": key1, "k2": key2})

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
