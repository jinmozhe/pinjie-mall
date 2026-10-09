from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError

from app.api.dependencies import CurrentUser, DatabaseSession, get_request_settings, get_resources
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.core.request_metadata import request_metadata
from app.core.security import decode_access_token
from app.db.repositories import SessionRepository
from app.db.repositories.commerce_access import CommerceAccessRepository
from app.domains.addresses.repository import AddressRepository
from app.domains.addresses.service import AddressService
from app.services.commerce import AddressApplicationService
from app.services.miniapp_auth import MiniappAuthService, bearer_error


def require_miniapp_profile(request: Request, response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    if request.headers.get("cookie"):
        raise AppException(status_code=400, code=ErrorCode.VALIDATION_ERROR, message="小程序接口不接受浏览器 Cookie")


async def current_miniapp_user(
    request: Request,
    session: DatabaseSession,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(HTTPBearer(auto_error=False, scheme_name="MiniappBearer"))
    ],
    profile: Annotated[None, Depends(require_miniapp_profile)],
) -> CurrentUser:
    settings = get_request_settings(request)
    if not settings.miniapp_login_enabled:
        raise AppException(status_code=503, code=ErrorCode.SERVICE_UNAVAILABLE, message="微信登录尚未开放")
    if get_resources(request).redis is None:
        raise AppException(status_code=503, code=ErrorCode.SERVICE_UNAVAILABLE, message="认证服务暂时不可用")
    if credentials is None or credentials.scheme.lower() != "bearer" or len(credentials.credentials) > 4096:
        raise bearer_error(ErrorCode.AUTH_REQUIRED)
    secret, _ = settings.miniapp_secrets()
    try:
        claims = decode_access_token(
            credentials.credentials, audience="pinjie-miniapp", issuer=settings.jwt_issuer, secret=secret
        )
    except InvalidTokenError:
        raise bearer_error() from None
    current = await SessionRepository(session).get_web(claims.session_id)
    if (
        current is None
        or current.user_id != claims.subject_id
        or current.credential_profile != "miniapp_bearer"
        or current.client_id != "pinjie-miniapp"
        or current.csrf_digest is not None
    ):
        raise bearer_error()
    now = datetime.now(UTC)
    if current.revoked_at is not None or claims.credential_version != current.user.credential_version:
        raise bearer_error(ErrorCode.AUTH_SESSION_REVOKED)
    if current.idle_expires_at <= now or current.absolute_expires_at <= now:
        raise bearer_error(ErrorCode.AUTH_SESSION_EXPIRED)
    if not current.user.is_active or current.user.deleted_at is not None:
        raise AppException(status_code=403, code=ErrorCode.AUTH_ACCOUNT_DISABLED, message="账户已停用")
    request.state.current_user_id, request.state.current_session_id = str(current.user_id), str(current.id)
    return CurrentUser(user=current.user, login_session=current)


MiniappPrincipal = Annotated[CurrentUser, Depends(current_miniapp_user)]


def miniapp_auth(request: Request, session: DatabaseSession) -> MiniappAuthService:
    resources = get_resources(request)
    return MiniappAuthService(
        session=session,
        session_factory=resources.session_factory,
        redis=resources.redis,
        settings=get_request_settings(request),
        http=resources.wechat_http,
        metadata=request_metadata(request),
    )


def miniapp_addresses(session: DatabaseSession, current: MiniappPrincipal) -> AddressApplicationService:
    return AddressApplicationService(
        session, AddressService(AddressRepository(session)), CommerceAccessRepository(session), current.user.id
    )


MiniappAuth = Annotated[MiniappAuthService, Depends(miniapp_auth)]
MiniappAddresses = Annotated[AddressApplicationService, Depends(miniapp_addresses)]
