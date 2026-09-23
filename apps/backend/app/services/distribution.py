from collections.abc import Awaitable, Callable
from typing import TypeVar
from uuid import UUID

from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.core.identifiers import new_uuid7
from app.db.repositories.commerce_access import CommerceAccessRepository
from app.domains.admin.permissions import PermissionCode
from app.domains.distribution import (
    DistributionService,
    WithdrawalCreate,
    WithdrawalManualCompletion,
    WithdrawalRead,
    WithdrawalReview,
)
from app.services.security_events import AuditCoordinator, AuditSuccess

T = TypeVar("T")


class UserDistributionApplicationService:
    def __init__(self, *, distribution: DistributionService, audit: AuditCoordinator, actor_id: UUID) -> None:
        self.distribution = distribution
        self.audit = audit
        self.actor_id = actor_id

    async def create_withdrawal(self, data: WithdrawalCreate) -> WithdrawalRead:
        withdrawal_id = new_uuid7()

        async def operation() -> tuple[WithdrawalRead, bool]:
            return await self.distribution.create_withdrawal_in_open_transaction(self.actor_id, data, withdrawal_id)

        def success_event(result: tuple[WithdrawalRead, bool]) -> AuditSuccess:
            withdrawal, created = result
            return AuditSuccess(
                action="withdrawal.state_changed" if created else "withdrawal.request_replayed",
                target_id=withdrawal.id,
                target_revision=withdrawal.revision,
                changed_fields={
                    "schema_version": 1,
                    "operation": "withdrawal.create" if created else "withdrawal.replay",
                    "from_status": None if created else withdrawal.status,
                    "to_status": withdrawal.status,
                    "reason": None,
                    "payload_hash": None,
                },
            )

        withdrawal, _ = await self.audit.execute(
            action="withdrawal.state_changed",
            target_type="withdrawal_request",
            target_id=withdrawal_id,
            target_revision=1,
            actor_type="user",
            changed_fields={},
            operation=operation,
            success_event=success_event,
        )
        return withdrawal


class AdminDistributionApplicationService:
    def __init__(
        self,
        *,
        distribution: DistributionService,
        access: CommerceAccessRepository,
        audit: AuditCoordinator,
        actor_id: UUID,
    ) -> None:
        self.distribution = distribution
        self.access = access
        self.audit = audit
        self.actor_id = actor_id

    async def _write(
        self,
        permission: PermissionCode,
        target_id: UUID,
        target_revision: int,
        from_status: str,
        to_status: str,
        reason: str,
        operation: Callable[[], Awaitable[T]],
    ) -> T:
        async def authorized() -> T:
            admin = await self.access.get_admin_for_update(self.actor_id)
            if admin is None or not admin.is_active:
                raise AppException(status_code=403, code=ErrorCode.PERMISSION_DENIED, message="当前管理员权限已失效")
            granted = admin.is_superuser or any(
                role.is_active and any(item.is_active and item.code == permission.value for item in role.permissions)
                for role in admin.roles
            )
            if not granted:
                raise AppException(status_code=403, code=ErrorCode.PERMISSION_DENIED, message="当前管理员权限已失效")
            return await operation()

        return await self.audit.execute(
            action="withdrawal.state_changed",
            target_type="withdrawal_request",
            target_id=target_id,
            target_revision=target_revision,
            changed_fields={
                "schema_version": 1,
                "operation": permission.value,
                "from_status": from_status,
                "to_status": to_status,
                "reason": reason,
                "payload_hash": None,
            },
            operation=authorized,
        )

    async def approve_withdrawal(self, withdrawal_id: UUID, data: WithdrawalReview) -> WithdrawalRead:
        return await self._write(
            PermissionCode.WITHDRAWALS_REVIEW,
            withdrawal_id,
            data.revision + 1,
            "requested",
            "approved",
            data.note,
            lambda: self.distribution.approve_withdrawal_in_open_transaction(withdrawal_id, data, self.actor_id),
        )

    async def reject_withdrawal(self, withdrawal_id: UUID, data: WithdrawalReview) -> WithdrawalRead:
        return await self._write(
            PermissionCode.WITHDRAWALS_REVIEW,
            withdrawal_id,
            data.revision + 1,
            "requested",
            "rejected",
            data.note,
            lambda: self.distribution.reject_withdrawal_in_open_transaction(withdrawal_id, data, self.actor_id),
        )

    async def complete_withdrawal_manually(
        self, withdrawal_id: UUID, data: WithdrawalManualCompletion
    ) -> WithdrawalRead:
        return await self._write(
            PermissionCode.WITHDRAWALS_COMPLETE_MANUAL,
            withdrawal_id,
            data.revision + 1,
            "approved",
            "succeeded",
            data.note,
            lambda: self.distribution.complete_withdrawal_manually_in_open_transaction(
                withdrawal_id, data, self.actor_id
            ),
        )
