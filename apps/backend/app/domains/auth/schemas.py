import re
import uuid
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

_USERNAME_PATTERN = re.compile(r"^[a-z0-9._-]{3,50}$")


def normalize_username(value: str) -> str:
    normalized = value.strip().lower()
    if not _USERNAME_PATTERN.fullmatch(normalized):
        raise ValueError("username must be 3-50 lowercase letters, digits, dot, underscore, or hyphen")
    return normalized


class UserPrincipalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: uuid.UUID
    username: str
    display_name: str | None
    email: str | None
    avatar: str | None = Field(default=None, description="用户头像站内资源路径")
    is_active: bool
    created_at: datetime
    updated_at: datetime


class RefreshSessionOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: uuid.UUID
    access_expires_at: datetime
    idle_expires_at: datetime
    absolute_expires_at: datetime


class WechatLoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=1, max_length=256, repr=False, description="微信一次性登录 code，不接受客户端 OpenID")


class ConsumerRefreshIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    refresh_token: str = Field(min_length=64, max_length=64, repr=False)


class ConsumerUserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    display_name: str | None
    avatar: str | None


class ConsumerSessionRead(BaseModel):
    user: ConsumerUserRead
    session_id: UUID
    access_token: str = Field(repr=False)
    refresh_token: str = Field(repr=False)
    access_expires_at: datetime
    idle_expires_at: datetime
    absolute_expires_at: datetime


class ConsumerCapabilitiesRead(BaseModel):
    login_enabled: bool
