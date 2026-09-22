from datetime import datetime
from uuid import UUID

from sqlalchemy import case, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DurableTask


class DurableTaskRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def by_key(self, task_type: str, business_key: str, *, lock: bool = False) -> DurableTask | None:
        statement = (
            select(DurableTask)
            .where(DurableTask.task_type == task_type, DurableTask.business_key == business_key)
            .execution_options(populate_existing=True)
        )
        if lock:
            statement = statement.with_for_update()
        return (await self.session.scalars(statement)).one_or_none()

    async def database_now(self) -> datetime:
        value: object = await self.session.scalar(select(func.clock_timestamp()))
        if not isinstance(value, datetime):
            raise RuntimeError("database clock did not return a timestamp")
        return value

    async def lease_candidates(self, now: datetime, limit: int) -> list[DurableTask]:
        return list(
            await self.session.scalars(
                select(DurableTask)
                .where(
                    or_(
                        (DurableTask.status == "pending") & (DurableTask.available_at <= now),
                        (DurableTask.status == "running")
                        & (DurableTask.lease_until.is_not(None))
                        & (DurableTask.lease_until <= now),
                    )
                )
                .order_by(DurableTask.available_at, DurableTask.id)
                .limit(limit)
                .with_for_update(skip_locked=True)
                .execution_options(populate_existing=True)
            )
        )

    async def count_lease_candidates(self, now: datetime) -> int:
        value = await self.session.scalar(
            select(func.count())
            .select_from(DurableTask)
            .where(
                or_(
                    (DurableTask.status == "pending") & (DurableTask.available_at <= now),
                    (DurableTask.status == "running")
                    & (DurableTask.lease_until.is_not(None))
                    & (DurableTask.lease_until <= now),
                )
            )
        )
        return int(value or 0)

    async def task(self, task_id: UUID, *, lock: bool = False) -> DurableTask | None:
        statement = select(DurableTask).where(DurableTask.id == task_id).execution_options(populate_existing=True)
        if lock:
            statement = statement.with_for_update()
        return (await self.session.scalars(statement)).one_or_none()

    async def complete_lease(self, task_id: UUID, lease_token: UUID) -> bool:
        result = await self.session.execute(
            update(DurableTask)
            .where(
                DurableTask.id == task_id,
                DurableTask.status == "running",
                DurableTask.lease_token == lease_token,
                DurableTask.lease_until > func.clock_timestamp(),
            )
            .values(
                status="succeeded",
                lease_token=None,
                lease_until=None,
                completed_at=func.clock_timestamp(),
                last_error_code=None,
                last_error_summary=None,
                revision=DurableTask.revision + 1,
                updated_at=func.clock_timestamp(),
            )
            .returning(DurableTask.id)
        )
        value: object = result.scalar_one_or_none()
        return isinstance(value, UUID)

    async def retry_lease(
        self,
        task_id: UUID,
        lease_token: UUID,
        error_code: str,
        error_summary: str,
        retry_at: datetime,
    ) -> str | None:
        next_failure_count = DurableTask.failure_count + 1
        terminal = next_failure_count >= DurableTask.max_failures
        result = await self.session.execute(
            update(DurableTask)
            .where(
                DurableTask.id == task_id,
                DurableTask.status == "running",
                DurableTask.lease_token == lease_token,
                DurableTask.lease_until > func.clock_timestamp(),
            )
            .values(
                status=case((terminal, "attention"), else_="pending"),
                failure_count=next_failure_count,
                lease_token=None,
                lease_until=None,
                available_at=case((terminal, DurableTask.available_at), else_=retry_at),
                last_error_code=error_code[:64],
                last_error_summary=error_summary[:500],
                revision=DurableTask.revision + 1,
                updated_at=func.clock_timestamp(),
            )
            .returning(DurableTask.status)
        )
        value: object = result.scalar_one_or_none()
        return value if isinstance(value, str) else None

    async def flush(self) -> None:
        await self.session.flush()


__all__ = ["DurableTaskRepository"]
