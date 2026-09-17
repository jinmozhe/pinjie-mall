from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.core.identifiers import new_uuid7
from app.core.pagination import PageResult
from app.db.models.inventory import InventoryAccount, InventoryMovement
from app.db.models.reservation import InventoryReservation, InventoryReservationEvent

from .repository import InventoryRepository
from .schemas import InventoryAdjustment, InventoryMovementRead, InventoryRead, adjusted_available


class InventoryService:
    def __init__(self, repository: InventoryRepository) -> None:
        self.repository = repository

    async def initialize(self, sku_id: UUID) -> None:
        await self.repository.save(InventoryAccount(sku_id=sku_id, available=0, reserved=0, revision=1))

    async def read(self, sku_id: UUID) -> InventoryRead:
        account = await self.repository.get(sku_id)
        if account is None:
            raise AppException(status_code=404, code=ErrorCode.INVENTORY_NOT_FOUND, message="库存账户不存在")
        return InventoryRead.model_validate(account)

    async def adjust(self, sku_id: UUID, data: InventoryAdjustment, actor_id: UUID) -> InventoryMovementRead:
        account = await self.repository.get(sku_id, lock=True)
        if account is None:
            raise AppException(status_code=404, code=ErrorCode.INVENTORY_NOT_FOUND, message="库存账户不存在")
        previous = await self.repository.movement(sku_id, data.request_id)
        if previous is not None:
            if (previous.quantity_delta, previous.expected_revision, previous.reason, previous.actor_id) != (
                data.quantity_delta,
                data.revision,
                data.reason,
                actor_id,
            ):
                raise AppException(
                    status_code=409, code=ErrorCode.INVENTORY_IDEMPOTENCY_CONFLICT, message="请求号已用于其他调整"
                )
            return InventoryMovementRead.model_validate(previous)
        if account.revision != data.revision:
            raise AppException(
                status_code=409, code=ErrorCode.INVENTORY_REVISION_CONFLICT, message="库存已变更，请重新读取"
            )
        try:
            after = adjusted_available(account.available, data.quantity_delta)
            adjusted_available(after, account.reserved)
        except ValueError as exc:
            raise AppException(status_code=409, code=ErrorCode.INVENTORY_QUANTITY_REJECTED, message=str(exc)) from exc
        movement = InventoryMovement(
            sku_id=sku_id,
            request_id=data.request_id,
            actor_id=actor_id,
            quantity_delta=data.quantity_delta,
            before_available=account.available,
            after_available=after,
            expected_revision=data.revision,
            resulting_revision=account.revision + 1,
            reason=data.reason,
        )
        account.available = after
        account.revision += 1
        await self.repository.save(movement)
        return InventoryMovementRead.model_validate(movement)

    async def reserve(self, order_id: UUID, quantities: dict[UUID, int]) -> None:
        existing = await self.repository.reservations(order_id)
        if existing:
            if {item.sku_id: item.quantity for item in existing} != quantities or any(
                item.status != "reserved" for item in existing
            ):
                raise AppException(status_code=409, code=ErrorCode.ORDER_STOCK_REJECTED, message="订单库存占用内容冲突")
            return
        accounts = await self.repository.accounts(sorted(quantities))
        if not quantities or len(accounts) != len(quantities):
            raise AppException(status_code=409, code=ErrorCode.ORDER_STOCK_REJECTED, message="SKU 库存账户不存在")
        for account in accounts:
            quantity = quantities[account.sku_id]
            if not 1 <= quantity <= 999 or account.available < quantity:
                raise AppException(
                    status_code=409, code=ErrorCode.ORDER_STOCK_REJECTED, message="库存不足或占用数量不合法"
                )
            before_available, before_reserved = account.available, account.reserved
            account.available -= quantity
            account.reserved += quantity
            account.revision += 1
            reservation = InventoryReservation(
                id=new_uuid7(),
                order_id=order_id,
                sku_id=account.sku_id,
                quantity=quantity,
                status="reserved",
                revision=1,
            )
            await self.repository.save(reservation)
            await self._reservation_event(reservation, account, before_available, before_reserved)

    async def transition_reservations(
        self, order_id: UUID, quantities: dict[UUID, int], status: Literal["confirmed", "released"]
    ) -> None:
        reservations = await self.repository.reservations(order_id)
        if not quantities or {item.sku_id: item.quantity for item in reservations} != quantities:
            raise AppException(status_code=409, code=ErrorCode.ORDER_STOCK_REJECTED, message="订单明细与库存占用不一致")
        accounts = await self.repository.accounts(sorted(quantities))
        if len(accounts) != len(quantities):
            raise AppException(status_code=409, code=ErrorCode.ORDER_STOCK_REJECTED, message="SKU 库存账户不存在")
        by_sku = {account.sku_id: account for account in accounts}
        for reservation in reservations:
            if reservation.status == status:
                continue
            account = by_sku[reservation.sku_id]
            if reservation.status != "reserved" or account.reserved < reservation.quantity:
                raise AppException(
                    status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="库存占用状态或数量异常"
                )
            before_available, before_reserved = account.available, account.reserved
            account.reserved -= reservation.quantity
            if status == "released":
                account.available += reservation.quantity
                reservation.released_at = datetime.now(UTC)
            account.revision += 1
            reservation.status = status
            reservation.revision += 1
            await self.repository.save(reservation)
            await self._reservation_event(reservation, account, before_available, before_reserved)

    async def _reservation_event(
        self, reservation: InventoryReservation, account: InventoryAccount, before_available: int, before_reserved: int
    ) -> None:
        await self.repository.save(
            InventoryReservationEvent(
                reservation_id=reservation.id,
                revision=reservation.revision,
                to_status=reservation.status,
                before_available=before_available,
                after_available=account.available,
                before_reserved=before_reserved,
                after_reserved=account.reserved,
                resulting_inventory_revision=account.revision,
            )
        )

    async def history(self, sku_id: UUID, page: int, page_size: int) -> PageResult[InventoryMovementRead]:
        await self.read(sku_id)
        rows, total = await self.repository.history(sku_id, page, page_size)
        return PageResult[InventoryMovementRead].create(
            items=[InventoryMovementRead.model_validate(row) for row in rows],
            total=total,
            page=page,
            page_size=page_size,
        )
