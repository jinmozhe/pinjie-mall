from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.core.identifiers import new_uuid7
from app.db.models import DurableTask

from .repository import DurableTaskRepository


@dataclass(frozen=True, slots=True)
class LeasedTask:
    id: UUID
    task_type: str
    business_key: str
    payload: dict[str, object]
    lease_token: UUID
    revision: int


class DurableTaskService:
    """Stores recoverable work intent; callers execute the business command outside this service."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repository = DurableTaskRepository(session)

    async def enqueue_in_open_transaction(
        self,
        *,
        task_type: str,
        business_key: str,
        payload: dict[str, object],
        available_at: datetime | None = None,
        max_failures: int = 5,
    ) -> DurableTask:
        self._validate_input(task_type, business_key, payload, max_failures)
        existing = await self._repository.by_key(task_type, business_key, lock=True)
        if existing is not None:
            if existing.payload != payload:
                raise AppException(
                    status_code=409,
                    code=ErrorCode.DURABLE_TASK_CONFLICT,
                    message="同一持久任务业务键不能使用不同载荷",
                )
            return existing
        row = DurableTask(
            id=new_uuid7(),
            task_type=task_type,
            business_key=business_key,
            payload=payload,
            status="pending",
            available_at=(available_at or datetime.now(UTC)).astimezone(UTC),
            attempt_count=0,
            failure_count=0,
            max_failures=max_failures,
            revision=1,
        )
        self._session.add(row)
        await self._repository.flush()
        return row

    async def lease_in_open_transaction(self, *, limit: int, lease_seconds: int = 60) -> list[LeasedTask]:
        if not 1 <= limit <= 100 or not 1 <= lease_seconds <= 900:
            raise AppException(status_code=422, code=ErrorCode.VALIDATION_ERROR, message="持久任务领取参数无效")
        now = await self._repository.database_now()
        leased: list[LeasedTask] = []
        for row in await self._repository.lease_candidates(now, limit):
            if row.status == "running":
                row.failure_count += 1
                if row.failure_count >= row.max_failures:
                    row.status = "attention"
                    row.lease_token = None
                    row.lease_until = None
                    row.revision += 1
                    row.updated_at = now
                    continue
            token = new_uuid7()
            row.status = "running"
            row.lease_token = token
            row.lease_until = now + timedelta(seconds=lease_seconds)
            row.attempt_count += 1
            row.revision += 1
            row.updated_at = now
            leased.append(
                LeasedTask(
                    id=row.id,
                    task_type=row.task_type,
                    business_key=row.business_key,
                    payload=row.payload,
                    lease_token=token,
                    revision=row.revision,
                )
            )
        await self._repository.flush()
        return leased

    async def complete_in_open_transaction(self, *, task_id: UUID, lease_token: UUID) -> None:
        if not await self._repository.complete_lease(task_id, lease_token):
            raise AppException(
                status_code=409, code=ErrorCode.DURABLE_TASK_LEASE_CONFLICT, message="持久任务租约已失效"
            )

    async def retry_in_open_transaction(
        self,
        *,
        task_id: UUID,
        lease_token: UUID,
        error_code: str,
        error_summary: str,
        retry_delay_seconds: int,
    ) -> str:
        if not 1 <= retry_delay_seconds <= 900:
            raise AppException(status_code=422, code=ErrorCode.VALIDATION_ERROR, message="持久任务重试间隔无效")
        retry_at = await self._repository.database_now() + timedelta(seconds=retry_delay_seconds)
        status = await self._repository.retry_lease(task_id, lease_token, error_code, error_summary, retry_at)
        if status is None:
            raise AppException(
                status_code=409, code=ErrorCode.DURABLE_TASK_LEASE_CONFLICT, message="持久任务租约已失效"
            )
        return status

    async def due_count(self) -> int:
        return await self._repository.count_lease_candidates(await self._repository.database_now())

    @staticmethod
    def _validate_input(task_type: str, business_key: str, payload: dict[str, object], max_failures: int) -> None:
        if not task_type or len(task_type) > 64 or not business_key or len(business_key) > 160:
            raise AppException(status_code=422, code=ErrorCode.VALIDATION_ERROR, message="持久任务类型或业务键无效")
        if not isinstance(payload, dict) or payload.get("schema_version") != 1:
            raise AppException(
                status_code=422, code=ErrorCode.VALIDATION_ERROR, message="持久任务载荷必须包含 schema_version=1"
            )
        required_key = {
            "expire_order": "order_id",
            "payment_submit": "payment_attempt_id",
            "payment_query": "payment_attempt_id",
            "payment_close": "payment_attempt_id",
            "confirm_order": "payment_attempt_id",
            "auto_confirm_fulfillment": "fulfillment_id",
            "refund_submit": "refund_attempt_id",
            "refund_query": "refund_attempt_id",
            "refund_followup": "refund_attempt_id",
            "commission_settlement": "order_id",
            "withdrawal_submit": "withdrawal_request_id",
            "withdrawal_query": "withdrawal_request_id",
        }.get(task_type)
        if required_key is None or set(payload) != {"schema_version", required_key}:
            raise AppException(status_code=422, code=ErrorCode.VALIDATION_ERROR, message="持久任务类型或载荷无效")
        if max_failures <= 0:
            raise AppException(status_code=422, code=ErrorCode.VALIDATION_ERROR, message="持久任务失败阈值必须为正数")


__all__ = ["DurableTaskService", "LeasedTask"]
