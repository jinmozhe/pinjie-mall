from dataclasses import dataclass
from typing import Protocol

from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException


@dataclass(frozen=True, slots=True)
class TrustedExternalIdentity:
    provider: str
    app_id: str
    subject_id: str
    union_id: str | None


class ExternalIdentityProvider(Protocol):
    async def exchange(self, authorization_code: str) -> TrustedExternalIdentity: ...


class UnavailableExternalIdentityProvider:
    """渠道密钥与可信换码流程未配置时的显式边界。"""

    async def exchange(self, authorization_code: str) -> TrustedExternalIdentity:
        del authorization_code
        raise AppException(
            status_code=503,
            code=ErrorCode.EXTERNAL_IDENTITY_UNAVAILABLE,
            message="外部身份渠道尚未接入",
        )


__all__ = ["ExternalIdentityProvider", "TrustedExternalIdentity", "UnavailableExternalIdentityProvider"]
