from collections import defaultdict
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.core.identifiers import new_uuid7
from app.db.models.purchase import ProductPurchaseLimit, ProductPurchaseRecord

from .repository import PurchaseLimitRepository


class PurchaseLimitService:
    def __init__(self, repository: PurchaseLimitRepository) -> None:
        self._repository = repository

    @classmethod
    def for_session(cls, session: AsyncSession) -> "PurchaseLimitService":
        return cls(PurchaseLimitRepository(session))

    async def reserve(self, order_id: UUID, user_id: UUID, lines: list[tuple[UUID, int, int]]) -> None:
        grouped: defaultdict[UUID, int] = defaultdict(int)
        limits: dict[UUID, int] = {}
        for product_id, quantity, limit in lines:
            grouped[product_id] += quantity
            limits[product_id] = limit
        existing = await self._repository.records(order_id)
        if existing:
            expected = {product_id: quantity for product_id, quantity in grouped.items()}
            if {record.product_id: record.quantity for record in existing} != expected or any(
                record.status != "reserved" for record in existing
            ):
                raise AppException(status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="订单限购预占内容冲突")
            return
        for product_id in sorted(grouped, key=lambda value: value.hex):
            quantity, limit = grouped[product_id], limits[product_id]
            # 按 (user_id, product_id) 加行级咨询锁，防止账户不存在时并发创建触发唯一键冲突
            await self._repository.lock_account(user_id, product_id)
            account = await self._repository.account(user_id, product_id)
            if account is None:
                account = ProductPurchaseLimit(
                    id=new_uuid7(),
                    user_id=user_id,
                    product_id=product_id,
                    purchased_quantity=0,
                    reserved_quantity=0,
                    revision=1,
                )
            if limit > 0 and account.purchased_quantity + account.reserved_quantity + quantity > limit:
                raise AppException(status_code=409, code=ErrorCode.CHECKOUT_INVALID, message="商品累计限购数量不足")
            account.reserved_quantity += quantity
            account.revision += 1
            await self._repository.save(account)
            await self._repository.save(
                ProductPurchaseRecord(
                    id=new_uuid7(),
                    order_id=order_id,
                    user_id=user_id,
                    product_id=product_id,
                    quantity=quantity,
                    status="reserved",
                    revision=1,
                    limit_snapshot=limit,
                )
            )

    async def transition(
        self, order_id: UUID, status: Literal["confirmed", "released", "refunded"], at: datetime
    ) -> None:
        records = await self._repository.records(order_id)
        if not records:
            raise AppException(status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="订单缺少限购预占事实")
        for record in records:
            if record.status == status:
                continue
            if status == "refunded" and record.status == "confirmed":
                record.status = "refunded"
                record.refunded_at = at.astimezone(UTC)
                record.revision += 1
                await self._repository.save(record)
                continue
            if record.status != "reserved":
                raise AppException(status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="限购预占状态异常")
            account = await self._repository.account(record.user_id, record.product_id)
            if account is None or account.reserved_quantity < record.quantity:
                raise AppException(status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="限购账户状态异常")
            account.reserved_quantity -= record.quantity
            if status == "confirmed":
                account.purchased_quantity += record.quantity
                record.confirmed_at = at.astimezone(UTC)
            elif status == "released":
                record.released_at = at.astimezone(UTC)
            else:
                raise AppException(status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="限购状态转换异常")
            account.revision += 1
            record.status = status
            record.revision += 1
            await self._repository.save(account)
            await self._repository.save(record)
