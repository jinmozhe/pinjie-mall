import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.pagination import PageResult
from app.core.password_policy import PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH


class UserUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, max_length=100)
    email: str | None = Field(default=None, max_length=320)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str | None) -> str | None:
        return value.strip().lower() if value else None

    @model_validator(mode="after")
    def require_explicit_field(self) -> "UserUpdateIn":
        if not self.model_fields_set:
            raise ValueError("at least one field is required")
        return self


class UserAvatarUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: uuid.UUID | None = Field(default=None, description="本人上传的头像资产唯一标识，传 null 表示移除")


class PasswordChangeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: str = Field(min_length=1, max_length=PASSWORD_MAX_LENGTH, description="当前密码，最多 64 个字符")
    new_password: str = Field(
        min_length=PASSWORD_MIN_LENGTH,
        max_length=PASSWORD_MAX_LENGTH,
        description="新密码，长度为 6 至 64 个字符",
    )


class AccountDeleteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: str = Field(min_length=1, max_length=PASSWORD_MAX_LENGTH, description="当前密码，最多 64 个字符")


class SessionRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    device_name: str | None
    ip_masked: str | None
    user_agent_summary: str | None
    created_at: datetime
    last_seen_at: datetime
    idle_expires_at: datetime
    absolute_expires_at: datetime
    is_current: bool
    revoked_at: datetime | None


class ActionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    completed: bool = True


SessionPage = PageResult[SessionRead]


__all__ = [
    "AccountDeleteIn",
    "ActionResult",
    "PasswordChangeIn",
    "SessionPage",
    "SessionRead",
    "UserAvatarUpdateIn",
    "UserUpdateIn",
]


class ConsumerAvatarAssetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    url: str


class ConsumerAvatarUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asset_id: uuid.UUID | None


class ConsumerProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    display_name: str = Field(min_length=1, max_length=100)
