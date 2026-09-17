from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.pagination import PageResult


class MemberProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: UUID
    invitation_code: str
    level_code: str
    inviter_id: UUID | None
    bound_at: datetime | None
    created_at: datetime


class ReferralBindIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    invitation_code: str = Field(min_length=8, max_length=16, description="推荐人邀请码")

    @field_validator("invitation_code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.strip().upper()


class WalletAccountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    wallet_type: str
    available_amount: Decimal
    frozen_amount: Decimal
    debt_amount: Decimal
    revision: int
    updated_at: datetime


class CommissionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    order_id: UUID
    source_user_id: UUID
    beneficiary_user_id: UUID
    level: int
    base_amount: Decimal
    rate: Decimal
    amount: Decimal
    recovered_amount: Decimal
    status: str
    frozen_at: datetime
    settle_after: datetime | None
    settled_at: datetime | None
    recovered_at: datetime | None


class WithdrawalCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    request_id: UUID
    amount: Decimal = Field(gt=Decimal("0"), max_digits=15, decimal_places=2)
    destination_reference: str = Field(min_length=1, max_length=180, description="脱敏收款目标引用")

    @field_validator("destination_reference")
    @classmethod
    def normalize_destination(cls, value: str) -> str:
        return value.strip()


class WithdrawalReview(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    revision: int = Field(ge=1)
    note: str = Field(min_length=1, max_length=300)


class WithdrawalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    amount: Decimal
    currency: str
    destination_reference: str
    status: str
    review_note: str | None
    reviewed_by_id: UUID | None
    reviewed_at: datetime | None
    channel_reference: str | None
    confirmed_at: datetime | None
    revision: int
    created_at: datetime
    updated_at: datetime


CommissionPage = PageResult[CommissionRead]
WithdrawalPage = PageResult[WithdrawalRead]


__all__ = [
    "CommissionPage",
    "CommissionRead",
    "MemberProfileRead",
    "ReferralBindIn",
    "WalletAccountRead",
    "WithdrawalCreate",
    "WithdrawalPage",
    "WithdrawalRead",
    "WithdrawalReview",
]
