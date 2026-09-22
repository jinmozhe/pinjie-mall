from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

PaymentChannel = Literal["wechat", "alipay"]


class PaymentAttemptCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: UUID
    channel: PaymentChannel


class PaymentAttemptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    order_id: UUID
    channel: PaymentChannel
    merchant_reference: str
    status: str
    amount: Decimal
    currency: str
    unavailable_reason: str | None
    created_at: datetime


class VerifiedPaymentConfirmation(BaseModel):
    """Only a configured channel adapter may construct this after signature validation."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    payment_attempt_id: UUID
    channel: PaymentChannel
    channel_transaction_id: str = Field(min_length=1, max_length=160)
    amount: Decimal = Field(gt=0, max_digits=15, decimal_places=2)
    currency: Literal["CNY"]
    confirmed_at: datetime
    payload_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class VerifiedRefundConfirmation(BaseModel):
    """Only a configured channel adapter may construct this after refund result verification."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    refund_attempt_id: UUID
    channel: PaymentChannel
    payment_transaction_id: str = Field(min_length=1, max_length=160)
    amount: Decimal = Field(gt=0, max_digits=15, decimal_places=2)
    currency: Literal["CNY"]
    channel_refund_id: str = Field(min_length=1, max_length=160)
    confirmed_at: datetime
    payload_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class FulfillmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    order_id: UUID
    product_type: str
    status: str
    carrier: str | None
    tracking_number: str | None
    delivery_reference: str | None
    shipped_at: datetime | None
    delivered_at: datetime | None
    auto_confirm_at: datetime | None
    revision: int


class ShipmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    carrier: str = Field(min_length=1, max_length=80)
    tracking_number: str = Field(min_length=1, max_length=120)
    revision: int = Field(gt=0)


class VirtualDeliveryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    delivery_reference: str = Field(min_length=1, max_length=200)
    revision: int = Field(gt=0)


class ReceiptConfirm(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision: int = Field(gt=0)


class RefundRequestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: UUID
    reason: str = Field(min_length=1, max_length=300)


class RefundRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    order_id: UUID
    status: str
    review_mode: str
    items_amount: Decimal
    freight_amount: Decimal
    amount: Decimal
    currency: str
    reason: str
    review_note: str | None
    created_at: datetime
    reviewed_at: datetime | None
    completed_at: datetime | None
    revision: int


class RefundAttemptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    refund_request_id: UUID | None
    merchant_refund_reference: str
    channel: PaymentChannel
    amount: Decimal
    currency: str
    status: str
    channel_refund_id: str | None
    confirmed_at: datetime | None
    created_at: datetime


class RefundReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: str = Field(min_length=1, max_length=300)
    revision: int = Field(gt=0)


class ProductReviewCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rating: int = Field(ge=1, le=5)
    content: str = Field(default="", max_length=1000)


class ProductReviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    product_id: UUID
    rating: int
    content: str
    published_at: datetime


class ReconciliationRecordCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    channel: PaymentChannel
    record_type: Literal["payment", "refund", "withdrawal"]
    channel_transaction_id: str = Field(min_length=1, max_length=160)
    source_reference: str = Field(min_length=1, max_length=160)
    source_hash: str = Field(min_length=64, max_length=64)
    amount: Decimal = Field(gt=0, max_digits=15, decimal_places=2)
    currency: Literal["CNY"]
    occurred_at: datetime


class ReconciliationRecordRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    channel: PaymentChannel
    channel_transaction_id: str
    source_reference: str
    amount: Decimal
    currency: str
    occurred_at: datetime
    status: str
    payment_attempt_id: UUID | None
    refund_attempt_id: UUID | None
    withdrawal_request_id: UUID | None
    resolution_status: str
    note: str | None
