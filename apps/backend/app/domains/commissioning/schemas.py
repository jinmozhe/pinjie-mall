from datetime import datetime
from decimal import Decimal
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CommissionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


CommissionMode = Literal["fixed_amount", "percentage", "disabled"]
AllocationMode = Literal["fixed_amount", "percentage"]


class CommissionControlValue(CommissionInput):
    schema_version: Literal[1] = 1
    commissions_enabled: bool


class CommissionControlUpdate(CommissionControlValue):
    revision: int = Field(gt=0)


class CommissionControlRead(CommissionControlValue):
    revision: int
    updated_at: datetime
    updated_by_id: UUID | None


class CommissionPolicyWrite(CommissionInput):
    name: str = Field(min_length=1, max_length=100)
    default_mode: CommissionMode | None = None
    default_amount_per_unit: Decimal | None = Field(default=None, ge=0, max_digits=15, decimal_places=2)
    default_percentage_rate: Decimal | None = Field(default=None, ge=0, le=1, max_digits=7, decimal_places=6)
    max_depth: int = Field(default=3, ge=1, le=3)
    settle_delay_days: int = Field(default=7, ge=0)

    @model_validator(mode="after")
    def validate_default(self) -> Self:
        if self.default_mode is None:
            if self.default_amount_per_unit is not None or self.default_percentage_rate is not None:
                raise ValueError("未配置默认来源时不能提供佣金参数")
        elif self.default_mode == "fixed_amount":
            if self.default_amount_per_unit is None or self.default_percentage_rate is not None:
                raise ValueError("固定默认来源必须且只能提供 amount_per_unit")
        elif self.default_mode == "percentage":
            if self.default_percentage_rate is None or self.default_amount_per_unit is not None:
                raise ValueError("比例默认来源必须且只能提供 percentage_rate")
        elif self.default_amount_per_unit is not None or self.default_percentage_rate is not None:
            raise ValueError("禁佣默认来源不能提供佣金参数")
        return self


class CommissionPolicyCreate(CommissionPolicyWrite):
    pass


class CommissionPolicyUpdate(CommissionPolicyWrite):
    revision: int = Field(gt=0)


class CommissionPolicyRead(CommissionPolicyWrite):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: Literal["draft", "active", "retired"]
    activated_at: datetime | None
    content_version: int
    revision: int
    updated_by_id: UUID | None
    created_at: datetime
    updated_at: datetime


class CommissionAmountRuleWrite(CommissionInput):
    buyer_scope: Literal["any", "level"] = "any"
    buyer_level_id: UUID | None = None
    product_id: UUID | None = None
    sku_id: UUID | None = None
    rule_mode: CommissionMode
    amount_per_unit: Decimal | None = Field(default=None, ge=0, max_digits=15, decimal_places=2)
    percentage_rate: Decimal | None = Field(default=None, ge=0, le=1, max_digits=7, decimal_places=6)

    @model_validator(mode="after")
    def validate_rule(self) -> Self:
        if (self.buyer_scope == "any") != (self.buyer_level_id is None):
            raise ValueError("通用买家范围不能指定等级，等级范围必须指定等级")
        if (self.product_id is None) == (self.sku_id is None):
            raise ValueError("佣金来源必须且只能指定商品或 SKU")
        if self.rule_mode == "fixed_amount":
            if self.amount_per_unit is None or self.percentage_rate is not None:
                raise ValueError("固定来源必须且只能提供 amount_per_unit")
        elif self.rule_mode == "percentage":
            if self.percentage_rate is None or self.amount_per_unit is not None:
                raise ValueError("比例来源必须且只能提供 percentage_rate")
        elif self.amount_per_unit is not None or self.percentage_rate is not None:
            raise ValueError("禁佣来源不能提供佣金参数")
        return self


class CommissionAmountRuleCreate(CommissionAmountRuleWrite):
    pass


class CommissionAmountRuleRead(CommissionAmountRuleWrite):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    policy_id: UUID
    created_at: datetime
    updated_at: datetime


class CommissionDistributionRuleWrite(CommissionInput):
    buyer_level_id: UUID
    ancestor_depth: int = Field(ge=1, le=3)
    beneficiary_level_id: UUID
    allocation_mode: AllocationMode
    rate: Decimal | None = Field(default=None, ge=0, le=1, max_digits=7, decimal_places=6)
    amount_per_unit: Decimal | None = Field(default=None, ge=0, max_digits=15, decimal_places=2)

    @model_validator(mode="after")
    def validate_allocation(self) -> Self:
        if self.allocation_mode == "percentage":
            if self.rate is None or self.amount_per_unit is not None:
                raise ValueError("比例分配必须且只能提供 rate")
        elif self.amount_per_unit is None or self.rate is not None:
            raise ValueError("固定分配必须且只能提供 amount_per_unit")
        return self


class CommissionDistributionRuleCreate(CommissionDistributionRuleWrite):
    pass


class CommissionDistributionRuleRead(CommissionDistributionRuleWrite):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    policy_id: UUID
    created_at: datetime
    updated_at: datetime


class CommissionDecisionContext(CommissionInput):
    """冻结成交佣金时使用的已锁定规则快照。"""

    control_id: UUID
    control: CommissionControlRead
    policy: CommissionPolicyRead | None
    amount_rules: list[CommissionAmountRuleRead]
    distribution_rules: list[CommissionDistributionRuleRead]


class CommissionPolicyPublish(CommissionInput):
    revision: int = Field(gt=0)


__all__ = [
    "CommissionAmountRuleCreate",
    "CommissionAmountRuleRead",
    "CommissionControlRead",
    "CommissionControlUpdate",
    "CommissionControlValue",
    "CommissionDecisionContext",
    "CommissionDistributionRuleCreate",
    "CommissionDistributionRuleRead",
    "CommissionPolicyCreate",
    "CommissionPolicyPublish",
    "CommissionPolicyRead",
    "CommissionPolicyUpdate",
]
