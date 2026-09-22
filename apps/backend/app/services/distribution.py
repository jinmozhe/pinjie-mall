from collections.abc import Awaitable, Callable
from typing import TypeVar
from uuid import UUID

from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.db.repositories.commerce_access import CommerceAccessRepository
from app.domains.admin.permissions import PermissionCode
from app.domains.distribution import DistributionService, WithdrawalManualCompletion, WithdrawalRead, WithdrawalReview
from app.services.security_events import AuditCoordinator

T = TypeVar("T")


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

    async def _write(self, permission: PermissionCode, target_id: UUID, operation: Callable[[], Awaitable[T]]) -> T:
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
            action=permission.value,
            target_type="withdrawal_request",
            target_id=target_id,
            changed_fields={"operation": permission.value},
            operation=authorized,
        )

    async def approve_withdrawal(self, withdrawal_id: UUID, data: WithdrawalReview) -> WithdrawalRead:
        return await self._write(
            PermissionCode.WITHDRAWALS_REVIEW,
            withdrawal_id,
            lambda: self.distribution.approve_withdrawal_in_open_transaction(withdrawal_id, data, self.actor_id),
        )

    async def reject_withdrawal(self, withdrawal_id: UUID, data: WithdrawalReview) -> WithdrawalRead:
        return await self._write(
            PermissionCode.WITHDRAWALS_REVIEW,
            withdrawal_id,
            lambda: self.distribution.reject_withdrawal_in_open_transaction(withdrawal_id, data, self.actor_id),
        )

    async def complete_withdrawal_manually(
        self, withdrawal_id: UUID, data: WithdrawalManualCompletion
    ) -> WithdrawalRead:
        return await self._write(
            PermissionCode.WITHDRAWALS_COMPLETE_MANUAL,
            withdrawal_id,
            lambda: self.distribution.complete_withdrawal_manually_in_open_transaction(
                withdrawal_id, data, self.actor_id
            ),
        )
