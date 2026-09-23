from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PointsAccount, PointsLedger


class PointsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def lock_adjustment(self, idempotency_key: str, user_id: UUID) -> None:
        for key in (f"pinjie:points:adjustment:{idempotency_key}", f"pinjie:points:account:{user_id}"):
            await self.session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": key})

    async def account(self, user_id: UUID, *, lock: bool = False) -> PointsAccount | None:
        statement = (
            select(PointsAccount).where(PointsAccount.user_id == user_id).execution_options(populate_existing=True)
        )
        if lock:
            statement = statement.with_for_update()
        return (await self.session.scalars(statement)).one_or_none()

    async def account_by_id(self, account_id: UUID, *, lock: bool = False) -> PointsAccount | None:
        statement = (
            select(PointsAccount).where(PointsAccount.id == account_id).execution_options(populate_existing=True)
        )
        if lock:
            statement = statement.with_for_update()
        return (await self.session.scalars(statement)).one_or_none()

    async def ledger(self, ledger_id: UUID, *, lock: bool = False) -> PointsLedger | None:
        statement = select(PointsLedger).where(PointsLedger.id == ledger_id).execution_options(populate_existing=True)
        if lock:
            statement = statement.with_for_update()
        return (await self.session.scalars(statement)).one_or_none()

    async def ledger_by_key(self, idempotency_key: str, *, lock: bool = False) -> PointsLedger | None:
        statement = (
            select(PointsLedger)
            .where(PointsLedger.idempotency_key == idempotency_key)
            .execution_options(populate_existing=True)
        )
        if lock:
            statement = statement.with_for_update()
        return (await self.session.scalars(statement)).one_or_none()

    async def reversal_total(self, ledger_id: UUID) -> int:
        return int(
            await self.session.scalar(
                select(func.coalesce(func.sum(PointsLedger.available_delta), 0)).where(
                    PointsLedger.reverses_ledger_id == ledger_id
                )
            )
            or 0
        )

    async def account_page(self, page: int, page_size: int) -> tuple[list[PointsAccount], int]:
        total = int(await self.session.scalar(select(func.count()).select_from(PointsAccount)) or 0)
        rows = await self.session.scalars(
            select(PointsAccount).order_by(PointsAccount.id.desc()).offset((page - 1) * page_size).limit(page_size)
        )
        return list(rows), total

    async def ledger_page(self, account_id: UUID, page: int, page_size: int) -> tuple[list[PointsLedger], int]:
        predicate = PointsLedger.account_id == account_id
        total = int(await self.session.scalar(select(func.count()).select_from(PointsLedger).where(predicate)) or 0)
        rows = await self.session.scalars(
            select(PointsLedger)
            .where(predicate)
            .order_by(PointsLedger.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(rows), total

    async def flush(self) -> None:
        await self.session.flush()


__all__ = ["PointsRepository"]
