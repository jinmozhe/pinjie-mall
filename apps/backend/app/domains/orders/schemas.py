from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CheckoutLine(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sku_id: UUID
    quantity: int = Field(ge=1, le=999)


class CheckoutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: UUID
    items: list[CheckoutLine] = Field(min_length=1, max_length=50)
    address_id: UUID | None = None
    quote_fingerprint: str | None = Field(default=None, min_length=64, max_length=64)


class OrderAcceptance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision: int = Field(gt=0)


class QuoteLine(BaseModel):
    model_config = ConfigDict(frozen=True)

    sku_id: UUID
    product_id: UUID
    product_name: str
    sku_code: str
    specifications: dict[str, str]
    quantity: int
    unit_price: Decimal
    line_amount: Decimal
    product_revision: int
    product_type: str
    price_snapshot: dict[str, object]
    category_snapshot: dict[str, object]
    brand_snapshot: dict[str, object] | None
    commission_snapshot: dict[str, object]
    purchase_limit_quantity: int
    weight_grams: int | None


class CheckoutQuote(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[QuoteLine]
    shipping_snapshot: dict[str, object]
    product_type: str
    items_amount: Decimal
    freight_amount: Decimal
    total_amount: Decimal
    address_id: UUID | None
    address_snapshot: dict[str, object] | None
    buyer_level_id: UUID | None
    buyer_level_snapshot: dict[str, object]
    fingerprint: str
    expires_at: datetime


class OrderItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    sku_id: UUID
    product_name: str
    sku_code: str
    specifications: dict[str, str]
    quantity: int
    unit_price: Decimal
    line_amount: Decimal
    price_snapshot: dict[str, object]


class OrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: str
    product_type: str
    items_amount: Decimal
    freight_amount: Decimal
    total_amount: Decimal
    address_snapshot: dict[str, object] | None
    shipping_snapshot: dict[str, object]
    buyer_level_snapshot: dict[str, object]
    settlement_kind: str | None
    expires_at: datetime
    created_at: datetime
    revision: int
    acceptance_status: str
    items: list[OrderItemRead]


class OrderFact(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: UUID
    user_id: UUID
    status: str
    product_type: str
    currency: str
    items_amount: Decimal
    freight_amount: Decimal
    total_amount: Decimal
    expires_at: datetime
    created_at: datetime
    paid_at: datetime | None
    accepted_payment_attempt_id: UUID | None
    settlement_kind: str | None
    acceptance_status: str


class OrderItemFact(OrderItemRead):
    model_config = ConfigDict(from_attributes=True, frozen=True)

    order_id: UUID
    product_id: UUID


class AdminOrderSummary(OrderFact):
    """管理端订单发现入口，不包含收货地址与订单明细。"""
