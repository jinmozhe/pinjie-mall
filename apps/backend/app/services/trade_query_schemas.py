"""Consumer-only read models, separate from operations and channel DTOs."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.domains.lifecycle.schemas import FulfillmentRead, ProductReviewRead, RefundRequestRead
from app.domains.orders.schemas import OrderRead

TradeFilter = Literal[
    "pending_payment", "paid", "cancelled", "awaiting_shipment", "awaiting_delivery", "shipped", "delivered"
]
DisplayStatus = Literal[
    "pending_payment",
    "cancelled",
    "awaiting_fulfillment",
    "awaiting_shipment",
    "awaiting_delivery",
    "shipped",
    "delivered",
    "refund_completed",
]
RefundExecutionStatus = Literal["not_started", "created", "processing", "succeeded", "abnormal", "unknown", "closed"]
RefundFundsStatus = Literal["not_confirmed", "confirmed", "no_funds"]


class ConsumerItemReviewRead(BaseModel):
    order_item_id: UUID
    can_review: bool
    review: ProductReviewRead | None


class ConsumerTradeOrderRead(OrderRead):
    display_status: DisplayStatus
    paid_at: datetime | None
    fulfillment: FulfillmentRead | None
    can_confirm_receipt: bool
    can_refund: bool
    item_reviews: list[ConsumerItemReviewRead]


class ConsumerRefundRead(RefundRequestRead):
    request_id: UUID
    execution_status: RefundExecutionStatus
    funds_status: RefundFundsStatus
    funds_confirmed_at: datetime | None


class ConsumerRefundLookupRead(BaseModel):
    state: Literal["found", "not_found"]
    refund: ConsumerRefundRead | None
