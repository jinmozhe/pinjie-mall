"""Consumer whitelist; never return operational identities or raw financial snapshots."""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

WalletType = Literal["commission", "consumption"]


class ConsumerMemberRead(BaseModel):
    state: Literal["not_opened", "no_level", "active", "inactive"]
    level_name: str | None
    level_changed_at: datetime | None
    created_at: datetime | None
    referral_bound: bool
    bound_at: datetime | None


class ConsumerWalletRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    wallet_type: WalletType
    available_amount: Decimal
    frozen_amount: Decimal
    debt_amount: Decimal
    revision: int
    updated_at: datetime


class ConsumerWalletBalanceRead(BaseModel):
    available_amount: Decimal = Field(ge=0)
    frozen_amount: Decimal = Field(ge=0)
    debt_amount: Decimal = Field(ge=0)


class ConsumerWalletLedgerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    entry_type: Literal[
        "commission_settlement", "commission_recovery", "withdrawal_freeze", "withdrawal_release", "withdrawal_paid"
    ]
    amount: Decimal
    frozen_delta: Decimal
    debt_delta: Decimal
    wallet_revision: int
    balance_after: ConsumerWalletBalanceRead
    created_at: datetime


class ConsumerCommissionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    level: int
    base_amount: Decimal
    rate: Decimal | None
    amount: Decimal
    recovered_amount: Decimal
    status: Literal["frozen", "settled", "recovered"]
    frozen_at: datetime
    settle_after: datetime | None
    settled_at: datetime | None
    recovered_at: datetime | None


class ConsumerWithdrawalRead(BaseModel):
    id: UUID
    amount: Decimal
    currency: Literal["CNY"]
    status: Literal["requested", "approved", "rejected", "processing", "succeeded", "unknown"]
    reviewed_at: datetime | None
    funds_status: Literal["not_confirmed", "manual_confirmed", "channel_confirmed"]
    confirmed_at: datetime | None
    created_at: datetime
    updated_at: datetime
