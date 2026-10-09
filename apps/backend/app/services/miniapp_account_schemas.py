"""Consumer account security views; credentials and raw network metadata stay private."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.pagination import PageResult

SessionState = Literal["active", "expired", "revoked", "not_found"]
ClosureCheckKey = Literal[
    "orders", "payments", "refunds", "refund_execution", "withdrawals", "commissions", "wallets", "points"
]


class MiniappLoginSessionRead(BaseModel):
    id: UUID
    device_name: str | None
    ip_masked: str | None
    created_at: datetime
    last_seen_at: datetime
    idle_expires_at: datetime
    absolute_expires_at: datetime
    revoked_at: datetime | None
    is_current: bool
    state: Literal["active", "expired", "revoked"]


class MiniappLoginSessionsRead(PageResult[MiniappLoginSessionRead]):
    other_active_total: int = Field(ge=0)
    other_active_ids: list[UUID] = Field(max_length=100)


class MiniappSessionTargets(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_ids: list[UUID] = Field(min_length=1, max_length=100)

    @field_validator("session_ids")
    @classmethod
    def unique_targets(cls, values: list[UUID]) -> list[UUID]:
        if len(values) != len(set(values)):
            raise ValueError("会话标识不能重复")
        return values


class MiniappSessionStateRead(BaseModel):
    id: UUID
    state: SessionState


class MiniappSessionRevocationRead(BaseModel):
    sessions: list[MiniappSessionStateRead] = Field(min_length=1, max_length=100)


class MiniappClosureCheckRead(BaseModel):
    key: ClosureCheckKey
    needs_review: bool


class MiniappClosurePrecheckRead(BaseModel):
    self_service_enabled: Literal[False] = False
    checked_at: datetime
    wallet_state: Literal["not_opened", "opened"]
    points_state: Literal["not_opened", "opened"]
    checks: list[MiniappClosureCheckRead]
