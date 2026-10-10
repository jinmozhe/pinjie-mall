"""Authorized, read-only cross-domain projection for the miniapp consumer."""

from collections.abc import Sequence
from typing import cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.core.pagination import PageResult
from app.db.models.commerce_lifecycle import Fulfillment, ProductReview, RefundAttempt, RefundRequest
from app.db.models.order import Order, OrderItem
from app.domains.lifecycle.schemas import FulfillmentRead, ProductReviewRead, RefundRequestRead
from app.domains.orders.schemas import OrderItemRead
from app.domains.users import UserAccessService
from app.services.trade_query_schemas import (
    ConsumerItemReviewRead,
    ConsumerRefundLookupRead,
    ConsumerRefundRead,
    ConsumerTradeOrderRead,
    DisplayStatus,
    RefundExecutionStatus,
    RefundFundsStatus,
    TradeFilter,
)


def display_status(status: str, fulfillment_status: str | None) -> DisplayStatus:
    if status in {"pending_payment", "cancelled"}:
        return cast(DisplayStatus, status)
    if status != "paid":
        raise AppException(status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="订单状态无法展示")
    if fulfillment_status is None:
        return "awaiting_fulfillment"
    if fulfillment_status == "cancelled":
        return "refund_completed"
    if fulfillment_status not in {"awaiting_shipment", "awaiting_delivery", "shipped", "delivered"}:
        raise AppException(status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="履约状态无法展示")
    return cast(DisplayStatus, fulfillment_status)


def refund_read(row: RefundRequest, attempt: RefundAttempt | None) -> ConsumerRefundRead:
    if attempt is not None and (
        attempt.refund_request_id != row.id
        or attempt.order_id != row.order_id
        or attempt.amount != row.amount
        or attempt.currency != row.currency
        or attempt.purpose != "after_sale"
    ):
        raise AppException(status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="退款执行事实不匹配")
    # Only a verified channel fact proves a positive-amount return of funds.
    funds: RefundFundsStatus = "no_funds" if row.amount == 0 and row.status == "completed" else "not_confirmed"
    if row.amount > 0 and attempt is not None and attempt.status == "succeeded" and attempt.confirmed_at is not None:
        funds = "confirmed"
    return ConsumerRefundRead(
        **RefundRequestRead.model_validate(row).model_dump(),
        request_id=row.request_id,
        execution_status=cast(RefundExecutionStatus, attempt.status if attempt is not None else "not_started"),
        funds_status=funds,
        funds_confirmed_at=attempt.confirmed_at if funds == "confirmed" and attempt is not None else None,
    )


class ConsumerTradeQueryService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.access = UserAccessService(session)

    async def orders(
        self, user_id: UUID, page: int, page_size: int, status: TradeFilter | None
    ) -> PageResult[ConsumerTradeOrderRead]:
        await self.access.require_active_user(user_id)
        stmt = (
            select(Order, Fulfillment)
            .outerjoin(Fulfillment, Fulfillment.order_id == Order.id)
            .where(Order.user_id == user_id)
        )
        if status in {"pending_payment", "paid", "cancelled"}:
            stmt = stmt.where(Order.status == status)
        elif status is not None:
            stmt = stmt.where(Order.status == "paid", Fulfillment.status == status)
        total = int(await self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        rows = (
            await self.session.execute(stmt.order_by(Order.id.desc()).offset((page - 1) * page_size).limit(page_size))
        ).all()
        orders = await self._project(user_id, [(row[0], row[1]) for row in rows])
        return PageResult[ConsumerTradeOrderRead].create(items=orders, total=total, page=page, page_size=page_size)

    async def order(self, user_id: UUID, order_id: UUID) -> ConsumerTradeOrderRead:
        await self.access.require_active_user(user_id)
        row = (
            await self.session.execute(
                select(Order, Fulfillment)
                .outerjoin(Fulfillment, Fulfillment.order_id == Order.id)
                .where(Order.id == order_id, Order.user_id == user_id)
            )
        ).one_or_none()
        if row is None:
            raise AppException(status_code=404, code=ErrorCode.ORDER_NOT_FOUND, message="订单不存在")
        return (await self._project(user_id, [(row[0], row[1])]))[0]

    async def _project(
        self, user_id: UUID, rows: Sequence[tuple[Order, Fulfillment | None]]
    ) -> list[ConsumerTradeOrderRead]:
        if not rows:
            return []
        order_ids = [order.id for order, _ in rows]
        items: dict[UUID, list[OrderItem]] = {}
        for item in await self.session.scalars(
            select(OrderItem).where(OrderItem.order_id.in_(order_ids)).order_by(OrderItem.id)
        ):
            items.setdefault(item.order_id, []).append(item)
        blocked = set(
            await self.session.scalars(
                select(RefundRequest.order_id).where(
                    RefundRequest.order_id.in_(order_ids), RefundRequest.status != "rejected"
                )
            )
        )
        reviews = {
            review.order_item_id: review
            for review in await self.session.scalars(
                select(ProductReview)
                .join(OrderItem, OrderItem.id == ProductReview.order_item_id)
                .where(OrderItem.order_id.in_(order_ids), ProductReview.user_id == user_id)
            )
        }
        result = []
        for order, fulfillment in rows:
            state = display_status(order.status, fulfillment.status if fulfillment is not None else None)
            delivered = order.status == "paid" and state == "delivered"
            result.append(
                ConsumerTradeOrderRead(
                    id=order.id,
                    status=order.status,
                    product_type=order.product_type,
                    items_amount=order.items_amount,
                    freight_amount=order.freight_amount,
                    total_amount=order.total_amount,
                    address_snapshot=order.address_snapshot,
                    shipping_snapshot=order.shipping_snapshot,
                    buyer_level_snapshot=order.buyer_level_snapshot,
                    settlement_kind=order.settlement_kind,
                    expires_at=order.expires_at,
                    created_at=order.created_at,
                    revision=order.revision,
                    acceptance_status=order.acceptance_status,
                    items=[OrderItemRead.model_validate(item) for item in items.get(order.id, [])],
                    display_status=state,
                    paid_at=order.paid_at,
                    fulfillment=FulfillmentRead.model_validate(fulfillment) if fulfillment is not None else None,
                    can_confirm_receipt=order.product_type == "physical" and state == "shipped",
                    can_refund=(
                        state == ("awaiting_shipment" if order.product_type == "physical" else "awaiting_delivery")
                        and order.id not in blocked
                    ),
                    item_reviews=[
                        ConsumerItemReviewRead(
                            order_item_id=item.id,
                            can_review=delivered and item.id not in reviews,
                            review=ProductReviewRead.model_validate(reviews[item.id]) if item.id in reviews else None,
                        )
                        for item in items.get(order.id, [])
                    ],
                )
            )
        return result

    async def refunds(
        self, user_id: UUID, page: int, page_size: int, order_id: UUID | None
    ) -> PageResult[ConsumerRefundRead]:
        await self.access.require_active_user(user_id)
        if order_id is not None:
            # Explicit ownership before an empty per-order result.
            await self.order(user_id, order_id)
        stmt = (
            select(RefundRequest)
            .join(Order, Order.id == RefundRequest.order_id)
            .where(RefundRequest.user_id == user_id, Order.user_id == user_id)
        )
        if order_id is not None:
            stmt = stmt.where(RefundRequest.order_id == order_id)
        total = int(await self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        rows = list(
            await self.session.scalars(
                stmt.order_by(RefundRequest.id.desc()).offset((page - 1) * page_size).limit(page_size)
            )
        )
        return PageResult[ConsumerRefundRead].create(
            items=await self._refunds(rows), total=total, page=page, page_size=page_size
        )

    async def _refunds(self, rows: Sequence[RefundRequest]) -> list[ConsumerRefundRead]:
        if not rows:
            return []
        attempts: dict[UUID, RefundAttempt] = {}
        for attempt in await self.session.scalars(
            select(RefundAttempt).where(RefundAttempt.refund_request_id.in_([row.id for row in rows]))
        ):
            if attempt.refund_request_id is None or attempt.refund_request_id in attempts:
                raise AppException(status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="退款执行记录不唯一")
            attempts[attempt.refund_request_id] = attempt
        return [refund_read(row, attempts.get(row.id)) for row in rows]

    async def refund(self, user_id: UUID, refund_id: UUID) -> ConsumerRefundRead:
        await self.access.require_active_user(user_id)
        row = await self.session.scalar(
            select(RefundRequest)
            .join(Order, Order.id == RefundRequest.order_id)
            .where(RefundRequest.id == refund_id, RefundRequest.user_id == user_id, Order.user_id == user_id)
        )
        if row is None:
            raise AppException(status_code=404, code=ErrorCode.ORDER_NOT_FOUND, message="售后记录不存在")
        return (await self._refunds([row]))[0]

    async def refund_by_request(self, user_id: UUID, request_id: UUID) -> ConsumerRefundLookupRead:
        await self.access.require_active_user(user_id)
        row = await self.session.scalar(
            select(RefundRequest)
            .join(Order, Order.id == RefundRequest.order_id)
            .where(RefundRequest.request_id == request_id, RefundRequest.user_id == user_id, Order.user_id == user_id)
        )
        if row is None:
            return ConsumerRefundLookupRead(state="not_found", refund=None)
        return ConsumerRefundLookupRead(state="found", refund=(await self._refunds([row]))[0])
