from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from .repository import OrderRepository
from .schemas import OrderFact, OrderItemFact


class OrderQueryService:
    """为跨领域用例返回不可变订单事实，锁定读取沿用订单事务。"""

    def __init__(self, session: AsyncSession) -> None:
        self.repository = OrderRepository(session)

    async def order(self, order_id: UUID, *, lock: bool = False) -> OrderFact | None:
        row = await self.repository.order_by_id(order_id, lock=lock)
        return OrderFact.model_validate(row) if row is not None else None

    async def user_order(self, user_id: UUID, order_id: UUID, *, lock: bool = False) -> OrderFact | None:
        row = await self.repository.order(user_id, order_id, lock=lock)
        return OrderFact.model_validate(row) if row is not None else None

    async def order_items(self, order_id: UUID) -> list[OrderItemFact]:
        return [OrderItemFact.model_validate(row) for row in await self.repository.items(order_id)]

    async def order_item(self, order_item_id: UUID) -> OrderItemFact | None:
        row = await self.repository.item(order_item_id)
        return OrderItemFact.model_validate(row) if row is not None else None
