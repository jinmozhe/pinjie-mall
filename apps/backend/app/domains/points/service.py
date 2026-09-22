from collections.abc import Awaitable, Callable
from typing import Protocol, TypeVar
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.core.identifiers import new_uuid7
from app.core.pagination import PageResult
from app.db.models import PointsAccount, PointsLedger
from app.domains.membership import MembershipService, PointsAccountRead, PointsLedgerRead, PointsManualAdjustment

from .repository import PointsRepository

T = TypeVar("T")


class AuditExecutor(Protocol):
    async def execute(
        self,
        *,
        action: str,
        target_type: str,
        target_id: UUID | None,
        changed_fields: dict[str, object],
        operation: Callable[[], Awaitable[T]],
    ) -> T: ...


class PointsService:
    def __init__(
        self, *, session: AsyncSession, actor_id: UUID | None = None, audit: AuditExecutor | None = None
    ) -> None:
        self._session = session
        self._repository = PointsRepository(session)
        self._actor_id = actor_id
        self._audit_coordinator = audit

    async def accounts(self, page: int, page_size: int) -> PageResult[PointsAccountRead]:
        rows, total = await self._repository.account_page(page, page_size)
        return PageResult[PointsAccountRead].create(
            items=[PointsAccountRead.model_validate(row) for row in rows], total=total, page=page, page_size=page_size
        )

    async def ledgers(self, account_id: UUID, page: int, page_size: int) -> PageResult[PointsLedgerRead]:
        rows, total = await self._repository.ledger_page(account_id, page, page_size)
        return PageResult[PointsLedgerRead].create(
            items=[PointsLedgerRead.model_validate(row) for row in rows], total=total, page=page, page_size=page_size
        )

    async def adjust(self, data: PointsManualAdjustment) -> PointsAccountRead:
        if self._actor_id is None or self._audit_coordinator is None:
            raise AppException(status_code=403, code=ErrorCode.PERMISSION_DENIED, message="需要管理员权限")

        async def operation() -> PointsAccountRead:
            existing = await self._repository.ledger_by_key(data.idempotency_key, lock=True)
            if existing is not None:
                account = await self._require_account(existing.account_id)
                return PointsAccountRead.model_validate(account)
            account_for_user = await self._repository.account(data.user_id, lock=True)
            if account_for_user is None:
                account = PointsAccount(id=new_uuid7(), user_id=data.user_id, revision=1)
                self._session.add(account)
                await self._repository.flush()
            else:
                account = account_for_user
            available_delta, debt_delta = await self._apply_adjustment(account, data)
            account.available_points += available_delta
            account.debt_points += debt_delta
            account.revision += 1
            ledger = PointsLedger(
                id=new_uuid7(),
                account_id=account.id,
                entry_type=data.operation,
                available_delta=available_delta,
                frozen_delta=0,
                debt_delta=debt_delta,
                source_type="manual",
                source_id=self._actor_id,
                reverses_ledger_id=data.reverses_ledger_id,
                idempotency_key=data.idempotency_key,
                note=data.note,
            )
            self._session.add(ledger)
            await self._repository.flush()
            membership = MembershipService(session=self._session)
            if data.operation == "grant":
                await membership.record_qualification_event(
                    user_id=data.user_id,
                    metric="points",
                    source_type="points_grant",
                    source_id=ledger.id,
                    idempotency_key=f"points-qualification:{ledger.id}",
                    count_delta=data.points,
                    trigger_type="points",
                )
            else:
                original_ledger_id = data.reverses_ledger_id
                if original_ledger_id is None:
                    raise RuntimeError("validated points reversal has no original ledger")
                original_event = await membership.qualification_event_for_source(
                    user_id=data.user_id,
                    metric="points",
                    source_type="points_grant",
                    source_id=original_ledger_id,
                )
                if original_event is None:
                    raise AppException(
                        status_code=409, code=ErrorCode.STATE_CONFLICT, message="原积分流水没有资格贡献事实"
                    )
                await membership.record_qualification_event(
                    user_id=data.user_id,
                    metric="points",
                    source_type="points_reverse",
                    source_id=ledger.id,
                    idempotency_key=f"points-qualification:{ledger.id}",
                    count_delta=-data.points,
                    reverses_event_id=original_event.id,
                    trigger_type="points",
                )
            return PointsAccountRead.model_validate(account)

        return await self._audit_coordinator.execute(
            action="points.adjust",
            target_type="points_account",
            target_id=None,
            changed_fields={"operation": data.operation, "user_id": str(data.user_id), "points": data.points},
            operation=operation,
        )

    async def _require_account(self, account_id: UUID) -> PointsAccount:
        account = await self._repository.account_by_id(account_id, lock=True)
        if account is None:
            raise AppException(status_code=409, code=ErrorCode.STATE_CONFLICT, message="积分流水账户不存在")
        return account

    async def _apply_adjustment(self, account: PointsAccount, data: PointsManualAdjustment) -> tuple[int, int]:
        if data.operation == "grant":
            debt_payment = min(account.debt_points, data.points)
            return data.points - debt_payment, -debt_payment
        original_id = data.reverses_ledger_id
        if original_id is None:
            raise AppException(status_code=422, code=ErrorCode.VALIDATION_ERROR, message="积分冲销缺少原流水")
        original = await self._repository.ledger(original_id, lock=True)
        if original is None or original.account_id != account.id or original.entry_type != "grant":
            raise AppException(status_code=409, code=ErrorCode.STATE_CONFLICT, message="积分冲销原流水不匹配")
        already_reversed = -await self._repository.reversal_total(original.id)
        if data.points > original.available_delta - already_reversed:
            raise AppException(status_code=409, code=ErrorCode.STATE_CONFLICT, message="积分冲销超过原授予量")
        if data.points > account.available_points:
            return -account.available_points, data.points - account.available_points
        return -data.points, 0


__all__ = ["PointsService"]
