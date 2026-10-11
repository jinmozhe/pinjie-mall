from collections.abc import Awaitable, Callable
from typing import TypeVar
from uuid import UUID

from app.domains.admin.permissions import PermissionCode
from app.domains.lifecycle import (
    FulfillmentRead,
    ReconciliationRecordCreate,
    ReconciliationRecordRead,
    ReconciliationResolve,
    RefundRequestRead,
    RefundReview,
    ShipmentCreate,
    VirtualDeliveryCreate,
)
from app.domains.orders import OrderAcceptance, OrderRead
from app.services.admin_audit import AdminAuditCoordinator
from app.services.payment_lifecycle import LifecycleService

T = TypeVar("T")


class AdminLifecycleApplicationService:
    def __init__(
        self,
        *,
        lifecycle: LifecycleService,
        audit: AdminAuditCoordinator,
        actor_id: UUID,
    ) -> None:
        self.lifecycle = lifecycle
        self.audit = audit
        self.actor_id = actor_id

    async def _write(
        self,
        permission: PermissionCode,
        target_id: UUID | None,
        operation: Callable[[], Awaitable[T]],
    ) -> T:
        return await self.audit.execute(
            action=permission.value,
            target_type=permission.value.split(":")[0],
            target_id=target_id,
            changed_fields={"operation": permission.value},
            operation=operation,
            permission=permission,
        )

    async def ship(self, order_id: UUID, data: ShipmentCreate) -> FulfillmentRead:
        return await self._write(
            PermissionCode.FULFILLMENTS_SHIP,
            order_id,
            lambda: self.lifecycle.ship_in_open_transaction(order_id, data, self.actor_id),
        )

    async def accept_order(self, order_id: UUID, data: OrderAcceptance) -> OrderRead:
        return await self._write(
            PermissionCode.ORDERS_ACCEPT,
            order_id,
            lambda: self.lifecycle.accept_order_in_open_transaction(order_id, data, self.actor_id),
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

    async def resolve_reconciliation(self, record_id: UUID, data: ReconciliationResolve) -> ReconciliationRecordRead:
        return await self.audit.execute(
            action=PermissionCode.RECONCILIATION_RESOLVE.value,
            target_type="reconciliation_record",
            target_id=record_id,
            target_revision=data.revision + 1,
            changed_fields={"operation": PermissionCode.RECONCILIATION_RESOLVE.value, "resolution_status": "resolved"},
            operation=lambda: self.lifecycle.resolve_reconciliation_in_open_transaction(record_id, data, self.actor_id),
        )
