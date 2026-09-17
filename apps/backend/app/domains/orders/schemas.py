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


class QuoteLine(BaseModel):
    sku_id: UUID
    product_id: UUID
    product_name: str
    sku_code: str
    specifications: dict[str, str]
    quantity: int
    unit_price: Decimal
    line_amount: Decimal
    weight_grams: int
    product_revision: int
    product_type: str
    shipping_template_id: UUID | None


class ShippingQuoteGroup(BaseModel):
    template_id: UUID | None
    revision: int | None
    product_type: str
    pieces: int
    weight_grams: int
    items_amount: Decimal
    freight: Decimal


class CheckoutQuote(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[QuoteLine]
    shipping: list[ShippingQuoteGroup]
    product_type: str
    items_amount: Decimal
    freight_amount: Decimal
    total_amount: Decimal
    address_id: UUID | None
    address_snapshot: dict[str, object] | None
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


class OrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    status: str
    product_type: str
    items_amount: Decimal
    freight_amount: Decimal
    total_amount: Decimal
    address_snapshot: dict[str, object] | None
    expires_at: datetime
    created_at: datetime
    revision: int
    items: list[OrderItemRead]
