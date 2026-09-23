from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

Money = Decimal


class MembershipInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MemberLevelCreate(MembershipInput):
    code: str = Field(min_length=1, max_length=32, pattern=r"^[a-z][a-z0-9_]*$")
    name: str = Field(min_length=1, max_length=100)
    discount_factor: Decimal = Field(default=Decimal("1.000000"), ge=0, le=1, max_digits=7, decimal_places=6)
    level_rank: int = Field(gt=0)
    sort_order: int | None = Field(default=None, ge=0)
    is_active: bool = True


class MemberLevelUpdate(MemberLevelCreate):
    revision: int = Field(gt=0)


class MemberLevelRead(MemberLevelCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    revision: int
    created_at: datetime
    updated_at: datetime


QualificationMetric = Literal["consumption", "invite_count", "points"]
QualificationAggregation = Literal["single", "cumulative"]


class MemberLevelConditionCreate(MembershipInput):
    level_id: UUID
    metric: QualificationMetric
    aggregation: QualificationAggregation
    amount_threshold: Money | None = Field(default=None, ge=0, max_digits=15, decimal_places=2)
    count_threshold: int | None = Field(default=None, ge=0)
    is_active: bool = True
    effective_at: datetime

    @model_validator(mode="after")
    def validate_threshold(self) -> Self:
        if self.metric == "consumption":
            if self.amount_threshold is None or self.count_threshold is not None:
                raise ValueError("消费条件必须且只能提供金额门槛")
        elif self.count_threshold is None or self.amount_threshold is not None:
            raise ValueError("邀请或积分条件必须且只能提供数量门槛")
        return self


class MemberLevelConditionUpdate(MemberLevelConditionCreate):
    revision: int = Field(gt=0)


class MemberLevelConditionRead(MemberLevelConditionCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    updated_by_id: UUID | None
    revision: int
    created_at: datetime
    updated_at: datetime


class MembershipQualificationEventRead(MembershipInput):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    user_id: UUID
    metric: QualificationMetric
    source_type: str
    source_id: UUID
    order_id: UUID | None
    amount_delta: Money | None
    count_delta: int | None
    reverses_event_id: UUID | None
    occurred_at: datetime
    idempotency_key: str
    created_at: datetime
    updated_at: datetime


class MemberLevelEventRead(MembershipInput):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    user_id: UUID
    from_level_id: UUID | None
    to_level_id: UUID | None
    trigger_type: str
    trigger_id: UUID | None
    qualification_snapshot: dict[str, object]
    profile_revision: int
    operator_id: UUID | None
    idempotency_key: str
    created_at: datetime
    updated_at: datetime


class PointsAccountRead(MembershipInput):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    user_id: UUID
    available_points: int
    frozen_points: int
    debt_points: int
    revision: int
    created_at: datetime
    updated_at: datetime


class PointsLedgerRead(MembershipInput):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    account_id: UUID
    entry_type: str
    available_delta: int
    frozen_delta: int
    debt_delta: int
    source_type: str
    source_id: UUID
    reverses_ledger_id: UUID | None
    idempotency_key: str
    note: str | None
    created_at: datetime
    updated_at: datetime


class PointsManualAdjustment(MembershipInput):
    user_id: UUID
    points: int = Field(gt=0)
    operation: Literal["grant", "reverse"]
    idempotency_key: str = Field(min_length=1, max_length=160)
    reverses_ledger_id: UUID | None = None
    note: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def validate_reversal(self) -> Self:
        if (self.operation == "reverse") != (self.reverses_ledger_id is not None):
            raise ValueError("冲销必须且只能指定原积分流水")
        return self


ScopeType = Literal["sku", "product", "category"]
PriceMode = Literal["fixed", "discount", "exclude"]


class MemberPriceRuleCreate(MembershipInput):
    member_level_id: UUID
    scope_type: ScopeType
    sku_id: UUID | None = None
    product_id: UUID | None = None
    category_id: UUID | None = None
    price_mode: PriceMode
    fixed_price: Money | None = Field(default=None, ge=0, max_digits=15, decimal_places=2)
    discount_factor: Decimal | None = Field(default=None, ge=0, le=1, max_digits=7, decimal_places=6)
    is_active: bool = True

    @model_validator(mode="after")
    def validate_scope_and_price(self) -> Self:
        targets = {"sku": self.sku_id, "product": self.product_id, "category": self.category_id}
        if targets[self.scope_type] is None or sum(value is not None for value in targets.values()) != 1:
            raise ValueError("规则范围必须且只能指定一个对应对象")
        if self.scope_type == "category" and self.price_mode == "fixed":
            raise ValueError("分类规则只允许折扣或排除会员价")
        if self.price_mode == "fixed" and (self.fixed_price is None or self.discount_factor is not None):
            raise ValueError("一口价规则必须提供 fixed_price")
        if self.price_mode == "discount" and (self.discount_factor is None or self.fixed_price is not None):
            raise ValueError("折扣规则必须提供 discount_factor")
        if self.price_mode == "exclude" and (self.fixed_price is not None or self.discount_factor is not None):
            raise ValueError("排除规则不能提供价格参数")
        return self


class MemberPriceRuleUpdate(MemberPriceRuleCreate):
    revision: int = Field(gt=0)


class MemberPriceRuleRead(MemberPriceRuleCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    revision: int
    updated_by_id: UUID | None
    created_at: datetime
    updated_at: datetime


class ShippingRuleValue(MembershipInput):
    free_shipping_threshold: Money | None = Field(default=None, ge=0, max_digits=15, decimal_places=2)
    fixed_fee: Money = Field(ge=0, max_digits=15, decimal_places=2)


class ShippingRegionRule(ShippingRuleValue):
    id: UUID
    name: str = Field(min_length=1, max_length=100)
    province_codes: list[str] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_province_codes(self) -> Self:
        if len(set(self.province_codes)) != len(self.province_codes) or any(
            len(code) != 6 or not code.isdigit() for code in self.province_codes
        ):
            raise ValueError("省级行政编码必须为不重复的六位数字")
        return self


class OrderShippingSettingValue(MembershipInput):
    schema_version: Literal[1] = 1
    region_level: Literal["province"] = "province"
    default_rule: ShippingRuleValue
    region_rules: list[ShippingRegionRule] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_unique_regions(self) -> Self:
        codes = [code for rule in self.region_rules for code in rule.province_codes]
        if len(set(codes)) != len(codes):
            raise ValueError("特殊地区规则之间不能重叠")
        return self


class OrderShippingSettingUpdate(OrderShippingSettingValue):
    revision: int = Field(gt=0)


class OrderShippingSettingRead(OrderShippingSettingValue):
    revision: int
    updated_at: datetime
    updated_by_id: UUID | None


class QuoteItemInput(MembershipInput):
    sku_id: UUID
    quantity: int = Field(ge=1, le=999)


class CommerceQuoteRequest(MembershipInput):
    items: list[QuoteItemInput] = Field(min_length=1, max_length=100)
    province_code: str | None = Field(default=None, pattern=r"^\d{6}$")


class QuoteLineRead(MembershipInput):
    sku_id: UUID
    product_id: UUID
    product_name: str
    quantity: int
    base_unit_price: Money
    unit_price: Money
    line_amount: Money
    price_source: str
    pricing_snapshot: dict[str, object]


class CommerceQuoteRead(MembershipInput):
    items: list[QuoteLineRead]
    items_amount: Money
    freight_amount: Money
    total_amount: Money
    buyer_level_id: UUID | None
    buyer_level_state: Literal["none", "active", "disabled"]
    buyer_level_snapshot: dict[str, object]
    shipping_rule_id: UUID | None
    shipping_snapshot: dict[str, object]
    fingerprint: str


__all__ = [
    "CommerceQuoteRead",
    "CommerceQuoteRequest",
    "MemberLevelCreate",
    "MemberLevelConditionCreate",
    "MemberLevelConditionRead",
    "MemberLevelConditionUpdate",
    "MemberLevelEventRead",
    "MemberLevelRead",
    "MemberLevelUpdate",
    "MemberPriceRuleCreate",
    "MemberPriceRuleRead",
    "MemberPriceRuleUpdate",
    "OrderShippingSettingRead",
    "OrderShippingSettingUpdate",
    "OrderShippingSettingValue",
    "MembershipQualificationEventRead",
    "PointsAccountRead",
    "PointsLedgerRead",
    "PointsManualAdjustment",
]
