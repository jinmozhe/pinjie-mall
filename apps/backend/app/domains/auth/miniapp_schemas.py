from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class MiniappLoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=1, max_length=256, repr=False, description="微信一次性登录 code，不接受客户端 OpenID")


class MiniappRefreshIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    refresh_token: str = Field(min_length=64, max_length=64, repr=False)


class MiniappUserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    display_name: str | None
    avatar: str | None


class MiniappSessionRead(BaseModel):
    user: MiniappUserRead
    session_id: UUID
    access_token: str = Field(repr=False)
    refresh_token: str = Field(repr=False)
    access_expires_at: datetime
    idle_expires_at: datetime
    absolute_expires_at: datetime


class MiniappCapabilitiesRead(BaseModel):
    login_enabled: bool
