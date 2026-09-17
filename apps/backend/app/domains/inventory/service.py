from uuid import UUID

from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.core.pagination import PageResult
from app.db.models.inventory import InventoryAccount, InventoryMovement

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

    async def history(self, sku_id: UUID, page: int, page_size: int) -> PageResult[InventoryMovementRead]:
        await self.read(sku_id)
        rows, total = await self.repository.history(sku_id, page, page_size)
        return PageResult[InventoryMovementRead].create(
            items=[InventoryMovementRead.model_validate(row) for row in rows],
            total=total,
            page=page,
            page_size=page_size,
        )
