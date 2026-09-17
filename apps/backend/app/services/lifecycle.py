from collections.abc import Awaitable, Callable
from typing import TypeVar
from uuid import UUID

from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.db.repositories.commerce_access import CommerceAccessRepository
from app.domains.admin.permissions import PERMISSION_CODES, PermissionCode
from app.domains.lifecycle import (
    FulfillmentRead,
    ReconciliationRecordCreate,
    ReconciliationRecordRead,
    RefundRequestRead,
    RefundReview,
    ShipmentCreate,
    VirtualDeliveryCreate,
)
from app.domains.lifecycle.service import LifecycleService
from app.services.security_events import AuditCoordinator

T = TypeVar("T")


class AdminLifecycleApplicationService:
    def __init__(
        self,
        *,
        lifecycle: LifecycleService,
        access: CommerceAccessRepository,
        audit: AuditCoordinator,
        actor_id: UUID,
    ) -> None:
        self.lifecycle = lifecycle
        self.access = access
        self.audit = audit
        self.actor_id = actor_id

    async def _write(
        self,
        permission: PermissionCode,
        target_id: UUID | None,
        operation: Callable[[], Awaitable[T]],
    ) -> T:
        async def authorized() -> T:
            admin = await self.access.get_admin_for_update(self.actor_id)
            if admin is None or not admin.is_active or permission.value not in PERMISSION_CODES:
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
            target_type=permission.value.split(":")[0],
            target_id=target_id,
            changed_fields={"operation": permission.value},
            operation=authorized,
        )

    async def ship(self, order_id: UUID, data: ShipmentCreate) -> FulfillmentRead:
        return await self._write(
            PermissionCode.FULFILLMENTS_SHIP,
            order_id,
            lambda: self.lifecycle.ship_in_open_transaction(order_id, data, self.actor_id),
        )

    async def deliver_virtual(self, order_id: UUID, data: VirtualDeliveryCreate) -> FulfillmentRead:
        return await self._write(
            PermissionCode.FULFILLMENTS_DELIVER_VIRTUAL,
            order_id,
            lambda: self.lifecycle.deliver_virtual_in_open_transaction(order_id, data, self.actor_id),
        )

    async def approve_refund(self, refund_id: UUID, data: RefundReview) -> RefundRequestRead:
        return await self._write(
            PermissionCode.REFUNDS_REVIEW,
            refund_id,
            lambda: self.lifecycle.approve_refund_in_open_transaction(refund_id, data, self.actor_id),
        )

    async def reject_refund(self, refund_id: UUID, data: RefundReview) -> RefundRequestRead:
        return await self._write(
            PermissionCode.REFUNDS_REVIEW,
            refund_id,
            lambda: self.lifecycle.reject_refund_in_open_transaction(refund_id, data, self.actor_id),
        )

    async def reconcile(self, data: ReconciliationRecordCreate) -> ReconciliationRecordRead:
        return await self._write(
            PermissionCode.RECONCILIATION_IMPORT,
            None,
            lambda: self.lifecycle.reconcile_in_open_transaction(data),
        )
