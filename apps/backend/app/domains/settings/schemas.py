from __future__ import annotations

import unicodedata
import uuid
from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator, model_validator


def _trim(value: str) -> str:
    return unicodedata.normalize("NFC", value).strip()


TrimmedSiteName = Annotated[str, AfterValidator(_trim), Field(min_length=1, max_length=100)]
TrimmedSiteTitle = Annotated[str, AfterValidator(_trim), Field(min_length=1, max_length=150)]
TrimmedDescription = Annotated[str, AfterValidator(_trim), Field(max_length=500)]


class SiteLogoValue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(pattern=r"^site/logo(?:-[0-9a-f]{32})?\.(?:png|jpg|webp)$", description="配置媒体相对路径")
    mime_type: str = Field(pattern=r"^image/(?:png|jpeg|webp)$", description="服务端确认的图片 MIME")
    file_size: int = Field(gt=0, le=2 * 1024 * 1024, description="LOGO 文件大小，单位为字节")
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$", description="LOGO 文件 SHA-256 摘要")


class SiteSettingValue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: TrimmedSiteName
    logo: SiteLogoValue | None
    title: TrimmedSiteTitle
    keywords: list[str] = Field(max_length=20)
    description: TrimmedDescription

    @field_validator("keywords")
    @classmethod
    def normalize_keywords(cls, values: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            normalized = _trim(value)
            if not normalized:
                continue
            if len(normalized) > 64:
                raise ValueError("keyword must contain at most 64 characters")
            if normalized not in seen:
                seen.add(normalized)
                result.append(normalized)
        if len(result) > 20:
            raise ValueError("keywords must contain at most 20 items")
        return result


class RegistrationSettingValue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(strict=True, description="是否允许 Web 公开注册普通用户")


class AdminSummaryRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID = Field(description="最后修改管理员唯一标识")
    display_name: str | None = Field(description="最后修改管理员显示名称")


class SiteLogoRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str = Field(description="带修订号缓存参数的站点 LOGO 公开路径")
    mime_type: str = Field(description="站点 LOGO 的真实 MIME 类型")
    file_size: int = Field(description="站点 LOGO 文件大小，单位为字节")


class AdminSiteSettingRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Web 公共站点名称")
    logo: SiteLogoRead | None = Field(description="站点 LOGO 公开信息")
    title: str = Field(description="Web 默认页面标题")
    keywords: list[str] = Field(description="Web Metadata 关键词")
    description: str = Field(description="Web 默认站点描述")
    revision: int = Field(gt=0, description="当前设置修订号")
    updated_at: datetime = Field(description="最近更新时间")
    updated_by: AdminSummaryRead | None = Field(description="最后修改管理员摘要")


class SiteSettingPatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision: int = Field(gt=0, description="读取设置时获得的修订号")
    name: TrimmedSiteName | None = Field(default=None, description="Web 公共站点名称")
    title: TrimmedSiteTitle | None = Field(default=None, description="Web 默认页面标题")
    keywords: list[str] | None = Field(default=None, max_length=20, description="Web Metadata 关键词")
    description: TrimmedDescription | None = Field(default=None, description="Web 默认站点描述")

    @field_validator("keywords")
    @classmethod
    def normalize_optional_keywords(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        return SiteSettingValue.normalize_keywords(values)

    @model_validator(mode="after")
    def require_update_field(self) -> SiteSettingPatchIn:
        if not (self.model_fields_set - {"revision"}):
            raise ValueError("at least one setting field is required")
        return self


class RegistrationSettingPatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision: int = Field(gt=0, description="读取设置时获得的修订号")
    enabled: bool = Field(strict=True, description="是否允许 Web 公开注册普通用户")


class AdminRegistrationSettingRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(description="是否允许 Web 公开注册普通用户")
    revision: int = Field(gt=0, description="当前设置修订号")
    updated_at: datetime = Field(description="最近更新时间")
    updated_by: AdminSummaryRead | None = Field(description="最后修改管理员摘要")


class SiteProfileRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Web 公共站点名称")
    logo_url: str | None = Field(description="站点 LOGO 公开路径，未配置时为空")
    title: str = Field(description="Web 默认页面标题")
    keywords: list[str] = Field(description="Web Metadata 关键词")
    description: str = Field(description="Web 默认站点描述")


__all__ = [
    "AdminRegistrationSettingRead",
    "AdminSiteSettingRead",
    "AdminSummaryRead",
    "RegistrationSettingPatchIn",
    "RegistrationSettingValue",
    "SiteLogoRead",
    "SiteLogoValue",
    "SiteProfileRead",
    "SiteSettingPatchIn",
    "SiteSettingValue",
]
