import hashlib
import json
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

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

    @classmethod
    def for_session(cls, session: AsyncSession) -> "InventoryService":
        return cls(InventoryRepository(session))

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
        request_hash = hashlib.sha256(
            json.dumps(
                {**data.model_dump(mode="json"), "actor_id": str(actor_id)}, sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()
        if previous is not None:
            if previous.request_hash != request_hash or previous.source_type != "manual_adjustment":
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
            actor_type="admin",
            source_type="manual_adjustment",
            source_id=None,
            request_hash=request_hash,
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

    async def require_available(self, quantities: dict[UUID, int]) -> None:
        accounts = await self.repository.available_accounts(sorted(quantities))
        if not quantities or len(accounts) != len(quantities):
            raise AppException(status_code=409, code=ErrorCode.ORDER_STOCK_REJECTED, message="SKU 库存账户不存在")
        for account in accounts:
            quantity = quantities[account.sku_id]
            if not 1 <= quantity <= 999 or account.available < quantity:
                raise AppException(
                    status_code=409, code=ErrorCode.ORDER_STOCK_REJECTED, message="库存不足或占用数量不合法"
                )

    async def transition_reservations(
        self,
        order_id: UUID,
        quantities: dict[UUID, int],
        status: Literal["confirmed", "released"],
        *,
        archived_sku_ids: set[UUID],
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
            if status == "released" and account.sku_id in archived_sku_ids:
                await self.archive_available(account.sku_id, reservation.id)

    async def archive_available(self, sku_id: UUID, source_id: UUID) -> None:
        account = await self.repository.get(sku_id, lock=True)
        if account is None:
            raise AppException(status_code=409, code=ErrorCode.INVENTORY_NOT_FOUND, message="归档 SKU 缺少库存账户")
        if account.available == 0:
            return
        quantity = account.available
        digest = hashlib.sha256(f"sku_archive:{sku_id}:{source_id}:{account.revision}:{quantity}".encode()).hexdigest()
        movement = InventoryMovement(
            sku_id=sku_id,
            request_id=new_uuid7(),
            actor_type="system",
            actor_id=None,
            source_type="sku_archive",
            source_id=source_id,
            request_hash=digest,
            quantity_delta=-quantity,
            before_available=quantity,
            after_available=0,
            expected_revision=account.revision,
            resulting_revision=account.revision + 1,
            reason="归档货品可用库存清退",
        )
        account.available = 0
        account.revision += 1
        await self.repository.save(movement)

    async def restock_from_refund_in_open_transaction(
        self, lines: list[tuple[UUID, UUID, int]], *, archived_sku_ids: set[UUID]
    ) -> None:
        """Return each whole-order refund line to its original SKU exactly once."""
        if not lines:
            raise AppException(status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="退款缺少原订单明细")
        if len({refund_item_id for refund_item_id, _, _ in lines}) != len(lines):
            raise AppException(status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="退款库存回补来源重复")
        accounts = {
            row.sku_id: row for row in await self.repository.accounts(sorted({sku_id for _, sku_id, _ in lines}))
        }
        if len(accounts) != len({sku_id for _, sku_id, _ in lines}):
            raise AppException(status_code=409, code=ErrorCode.INVENTORY_NOT_FOUND, message="原 SKU 库存账户不存在")
        for refund_item_id, sku_id, quantity in sorted(lines, key=lambda item: item[1].hex):
            if not 1 <= quantity <= 999:
                raise AppException(status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="退款库存回补数量异常")
            account = accounts[sku_id]
            existing = await self.repository.movement(sku_id, refund_item_id)
            request_hash = hashlib.sha256(f"refund-restock:{refund_item_id}:{sku_id}:{quantity}".encode()).hexdigest()
            if existing is not None:
                if (
                    existing.source_type != "refund_unshipped"
                    or existing.source_id != refund_item_id
                    or existing.quantity_delta != quantity
                    or existing.request_hash != request_hash
                ):
                    raise AppException(
                        status_code=409,
                        code=ErrorCode.INVENTORY_IDEMPOTENCY_CONFLICT,
                        message="退款库存回补幂等来源冲突",
                    )
                continue
            before_available = account.available
            account.available += quantity
            account.revision += 1
            await self.repository.save(
                InventoryMovement(
                    id=new_uuid7(),
                    sku_id=sku_id,
                    request_id=refund_item_id,
                    actor_id=None,
                    actor_type="system",
                    source_type="refund_unshipped",
                    source_id=refund_item_id,
                    request_hash=request_hash,
                    quantity_delta=quantity,
                    before_available=before_available,
                    after_available=account.available,
                    expected_revision=account.revision - 1,
                    resulting_revision=account.revision,
                    reason="未发货或未交付整单退款库存回补",
                )
            )
            if sku_id in archived_sku_ids:
                await self.archive_available(sku_id, refund_item_id)

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
