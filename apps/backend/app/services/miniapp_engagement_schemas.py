"""Owner-only referral and points projections, independent of operational DTOs."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, PlainSerializer

# PostgreSQL BIGINT exceeds JavaScript's safe integer range. JSON uses exact strings.
PointsValue = Annotated[int, PlainSerializer(str, return_type=str, when_used="json")]


class MiniappReferralRead(BaseModel):
    state: Literal["not_opened", "unbound", "bound"]
    invitation_code: str | None
    bound_at: datetime | None
    matches_invitation: bool | None


class MiniappPointsAccountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    available_points: PointsValue
    frozen_points: PointsValue
    debt_points: PointsValue
    revision: int
    updated_at: datetime


class MiniappPointsRead(BaseModel):
    state: Literal["not_opened", "opened"]
    account: MiniappPointsAccountRead | None


class MiniappPointsLedgerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    entry_type: Literal["grant", "spend", "freeze", "release", "reverse", "expire"]
    available_delta: PointsValue
    frozen_delta: PointsValue
    debt_delta: PointsValue
    source_type: Literal["invite", "order", "refund", "redemption", "manual"]
    created_at: datetime
