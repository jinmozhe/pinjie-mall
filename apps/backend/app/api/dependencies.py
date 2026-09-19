import hmac
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, cast

from fastapi import Cookie, Depends, Request
from jwt import InvalidTokenError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.cookies import ADMIN_COOKIES, WEB_COOKIES
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.core.request_metadata import request_metadata
from app.core.resources import AppResources
from app.core.security import decode_access_token, token_digest
from app.db.models import Admin, AdminSession, User, UserSession
from app.db.repositories import SessionRepository
from app.db.session import session_scope
from app.domains.admin.permissions import PERMISSION_CODES, PermissionCode
from app.domains.assets.schemas import UploaderType
from app.services.accounts import AdminAccountService, UserAccountService
from app.services.admin_management import AdminManagementService
from app.services.assets import AssetService, AssetUploader
from app.services.authentication import AdminAuthService, WebAuthService
from app.services.settings_media import SettingsMediaStore
from app.services.storage import StorageProvider
from app.services.system_settings import SystemSettingsService


@dataclass(frozen=True, slots=True)
class CurrentUser:
    user: User
    login_session: UserSession


@dataclass(frozen=True, slots=True)
class CurrentAdmin:
    admin: Admin
    login_session: AdminSession
    permissions: frozenset[str]


def get_resources(request: Request) -> AppResources:
    resources = getattr(request.app.state, "resources", None)
    if resources is None:
        raise AppException(
            status_code=503,
            code=ErrorCode.SERVICE_UNAVAILABLE,
            message="服务尚未就绪",
        )
    return cast(AppResources, resources)


def get_request_settings(request: Request) -> Settings:
    settings = getattr(request.app.state, "settings", None)
    if settings is None:
        raise AppException(
            status_code=503,
            code=ErrorCode.SERVICE_UNAVAILABLE,
            message="服务尚未就绪",
        )
    return cast(Settings, settings)


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    resources = get_resources(request)
    async with session_scope(resources.session_factory) as session:
        yield session


DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]


def require_admin_access_token(
    access_token: Annotated[str | None, Cookie(alias=ADMIN_COOKIES.access)] = None,
) -> str:
    if not access_token:
        raise AppException(
            status_code=401,
            code=ErrorCode.AUTH_REQUIRED,
            message="需要管理员身份认证",
            headers={"WWW-Authenticate": "Cookie"},
        )
    return access_token


AdminAccessToken = Annotated[str, Depends(require_admin_access_token)]


def get_web_auth_service(request: Request, session: DatabaseSession) -> WebAuthService:
    resources = get_resources(request)
    return WebAuthService(
        session=session,
        session_factory=resources.session_factory,
        redis=resources.redis,
        settings=get_request_settings(request),
        password_manager=resources.password_manager,
        metadata=request_metadata(request),
    )


def get_admin_auth_service(request: Request, session: DatabaseSession) -> AdminAuthService:
    resources = get_resources(request)
    return AdminAuthService(
        session=session,
        session_factory=resources.session_factory,
        redis=resources.redis,
        settings=get_request_settings(request),
        password_manager=resources.password_manager,
        metadata=request_metadata(request),
    )


def get_user_account_service(request: Request, session: DatabaseSession) -> UserAccountService:
    resources = get_resources(request)
    return UserAccountService(
        session=session,
        settings=get_request_settings(request),
        password_manager=resources.password_manager,
        metadata=request_metadata(request),
    )


def get_admin_account_service(request: Request, session: DatabaseSession) -> AdminAccountService:
    resources = get_resources(request)
    return AdminAccountService(
        session=session,
        session_factory=resources.session_factory,
        redis=resources.redis,
        settings=get_request_settings(request),
        password_manager=resources.password_manager,
        metadata=request_metadata(request),
    )


WebAuthServiceDependency = Annotated[WebAuthService, Depends(get_web_auth_service)]
AdminAuthServiceDependency = Annotated[AdminAuthService, Depends(get_admin_auth_service)]
UserAccountServiceDependency = Annotated[UserAccountService, Depends(get_user_account_service)]
AdminAccountServiceDependency = Annotated[AdminAccountService, Depends(get_admin_account_service)]


def get_storage_provider(request: Request) -> StorageProvider:
    provider = getattr(request.app.state, "storage_provider", None)
    if provider is None:
        raise AppException(
            status_code=503,
            code=ErrorCode.SERVICE_UNAVAILABLE,
            message="文件存储服务尚未就绪",
        )
    return cast(StorageProvider, provider)


def get_asset_service(request: Request, session: DatabaseSession) -> AssetService:
    resources = get_resources(request)
    return AssetService(
        session=session,
        session_factory=resources.session_factory,
        settings=get_request_settings(request),
        storage=get_storage_provider(request),
        metadata=request_metadata(request),
    )


AssetServiceDependency = Annotated[AssetService, Depends(get_asset_service)]


def _require_browser_origin(request: Request, *, allowed_origins: list[str]) -> None:
    origin = request.headers.get("origin")
    allowed = set(allowed_origins)
    if origin is None or origin not in allowed:
        raise AppException(status_code=403, code=ErrorCode.CSRF_REJECTED, message="请求来源不在允许范围内")


def require_web_origin(request: Request) -> None:
    _require_browser_origin(request, allowed_origins=get_request_settings(request).web_origins)


def require_admin_origin(request: Request) -> None:
    _require_browser_origin(request, allowed_origins=get_request_settings(request).admin_origins)


def _csrf_pair(request: Request, *, cookie_name: str, allowed_origins: list[str]) -> str:
    _require_browser_origin(request, allowed_origins=allowed_origins)
    header_token = request.headers.get("x-csrf-token")
    cookie_token = request.cookies.get(cookie_name)
    if not header_token or not cookie_token or not hmac.compare_digest(header_token, cookie_token):
        raise AppException(status_code=403, code=ErrorCode.CSRF_REJECTED, message="CSRF 校验失败")
    return header_token


def require_web_csrf_pair(request: Request) -> str:
    return _csrf_pair(
        request,
        cookie_name=WEB_COOKIES.csrf,
        allowed_origins=get_request_settings(request).web_origins,
    )


def require_admin_csrf_pair(request: Request) -> str:
    return _csrf_pair(
        request,
        cookie_name=ADMIN_COOKIES.csrf,
        allowed_origins=get_request_settings(request).admin_origins,
    )


async def get_current_user(
    request: Request,
    session: DatabaseSession,
    access_token: Annotated[str | None, Cookie(alias=WEB_COOKIES.access)] = None,
) -> CurrentUser:
    if not access_token:
        raise AppException(
            status_code=401,
            code=ErrorCode.AUTH_REQUIRED,
            message="需要用户身份认证",
            headers={"WWW-Authenticate": "Cookie"},
        )
    settings = get_request_settings(request)
    resources = get_resources(request)
    if resources.redis is None:
        raise AppException(
            status_code=503,
            code=ErrorCode.SERVICE_UNAVAILABLE,
            message="认证服务暂时不可用",
        )
    web_secret, _, _, _ = settings.authentication_secrets()
    try:
        claims = decode_access_token(
            access_token,
            audience="pinjie-web",
            issuer=settings.jwt_issuer,
            secret=web_secret,
        )
        login_session = await SessionRepository(session).get_web(claims.session_id)
    except InvalidTokenError as exc:
        request.state.clear_auth_profile = "web"
        raise AppException(
            status_code=401,
            code=ErrorCode.AUTH_TOKEN_INVALID,
            message="身份认证令牌无效",
            headers={"WWW-Authenticate": "Cookie"},
        ) from exc
    except SQLAlchemyError as exc:
        raise AppException(
            status_code=503,
            code=ErrorCode.SERVICE_UNAVAILABLE,
            message="认证服务暂时不可用",
        ) from exc
    if login_session is None or login_session.user_id != claims.subject_id:
        request.state.clear_auth_profile = "web"
        raise AppException(
            status_code=401,
            code=ErrorCode.AUTH_SESSION_REVOKED,
            message="身份认证会话已失效",
            headers={"WWW-Authenticate": "Cookie"},
        )
    now = datetime.now(UTC)
    if login_session.revoked_at is not None:
        request.state.clear_auth_profile = "web"
        raise AppException(
            status_code=401,
            code=ErrorCode.AUTH_SESSION_REVOKED,
            message="身份认证会话已失效",
            headers={"WWW-Authenticate": "Cookie"},
        )
    if login_session.idle_expires_at <= now or login_session.absolute_expires_at <= now:
        request.state.clear_auth_profile = "web"
        raise AppException(
            status_code=401,
            code=ErrorCode.AUTH_SESSION_EXPIRED,
            message="身份认证会话已过期",
            headers={"WWW-Authenticate": "Cookie"},
        )
    user = login_session.user
    if claims.credential_version != user.credential_version:
        request.state.clear_auth_profile = "web"
        raise AppException(
            status_code=401,
            code=ErrorCode.AUTH_SESSION_REVOKED,
            message="身份认证会话已失效",
            headers={"WWW-Authenticate": "Cookie"},
        )
    if not user.is_active or user.deleted_at is not None:
        raise AppException(status_code=403, code=ErrorCode.AUTH_ACCOUNT_DISABLED, message="账户已停用")
    request.state.current_user_id = str(user.id)
    request.state.current_session_id = str(login_session.id)
    return CurrentUser(user=user, login_session=login_session)


async def get_current_admin(
    request: Request,
    access_token: AdminAccessToken,
    session: DatabaseSession,
) -> CurrentAdmin:
    settings = get_request_settings(request)
    resources = get_resources(request)
    if resources.redis is None:
        raise AppException(
            status_code=503,
            code=ErrorCode.SERVICE_UNAVAILABLE,
            message="认证服务暂时不可用",
        )
    _, admin_secret, _, _ = settings.authentication_secrets()
    try:
        claims = decode_access_token(
            access_token,
            audience="pinjie-admin",
            issuer=settings.jwt_issuer,
            secret=admin_secret,
        )
        login_session = await SessionRepository(session).get_admin(claims.session_id)
    except InvalidTokenError as exc:
        request.state.clear_auth_profile = "admin"
        raise AppException(
            status_code=401,
            code=ErrorCode.AUTH_TOKEN_INVALID,
            message="管理员身份认证令牌无效",
            headers={"WWW-Authenticate": "Cookie"},
        ) from exc
    except SQLAlchemyError as exc:
        raise AppException(
            status_code=503,
            code=ErrorCode.SERVICE_UNAVAILABLE,
            message="认证服务暂时不可用",
        ) from exc
    if login_session is None or login_session.admin_id != claims.subject_id:
        request.state.clear_auth_profile = "admin"
        raise AppException(
            status_code=401,
            code=ErrorCode.AUTH_SESSION_REVOKED,
            message="管理员会话已失效",
            headers={"WWW-Authenticate": "Cookie"},
        )
    now = datetime.now(UTC)
    if login_session.revoked_at is not None:
        request.state.clear_auth_profile = "admin"
        raise AppException(
            status_code=401,
            code=ErrorCode.AUTH_SESSION_REVOKED,
            message="管理员会话已失效",
            headers={"WWW-Authenticate": "Cookie"},
        )
    if login_session.idle_expires_at <= now or login_session.absolute_expires_at <= now:
        request.state.clear_auth_profile = "admin"
        raise AppException(
            status_code=401,
            code=ErrorCode.AUTH_SESSION_EXPIRED,
            message="管理员会话已过期",
            headers={"WWW-Authenticate": "Cookie"},
        )
    admin = login_session.admin
    if claims.credential_version != admin.credential_version:
        request.state.clear_auth_profile = "admin"
        raise AppException(
            status_code=401,
            code=ErrorCode.AUTH_SESSION_REVOKED,
            message="管理员会话已失效",
            headers={"WWW-Authenticate": "Cookie"},
        )
    if not admin.is_active:
        raise AppException(status_code=403, code=ErrorCode.AUTH_ACCOUNT_DISABLED, message="账户已停用")
    if admin.is_superuser:
        permissions = frozenset(PERMISSION_CODES)
    else:
        permissions = frozenset(
            permission.code
            for role in admin.roles
            if role.is_active
            for permission in role.permissions
            if permission.is_active and permission.code in PERMISSION_CODES
        )
    request.state.current_admin_id = str(admin.id)
    request.state.current_session_id = str(login_session.id)
    return CurrentAdmin(admin=admin, login_session=login_session, permissions=permissions)


async def get_asset_uploader(
    request: Request,
    session: DatabaseSession,
    web_access_token: Annotated[str | None, Cookie(alias=WEB_COOKIES.access)] = None,
    admin_access_token: Annotated[str | None, Cookie(alias=ADMIN_COOKIES.access)] = None,
) -> AssetUploader:
    settings = get_request_settings(request)
    origin = request.headers.get("origin")
    if origin in settings.web_origins and web_access_token:
        current_user = await get_current_user(request, session, web_access_token)
        require_web_csrf(request, current_user)
        return AssetUploader(type=UploaderType.USER, id=current_user.user.id)
    if origin in settings.admin_origins and admin_access_token:
        current_admin = await get_current_admin(
            request=request,
            access_token=admin_access_token,
            session=session,
        )
        require_admin_csrf(request, current_admin)
        return AssetUploader(type=UploaderType.ADMIN, id=current_admin.admin.id)
    raise AppException(
        status_code=401 if not web_access_token and not admin_access_token else 403,
        code=ErrorCode.AUTH_REQUIRED if not web_access_token and not admin_access_token else ErrorCode.CSRF_REJECTED,
        message="需要匹配当前来源的已认证上传会话",
        headers={"WWW-Authenticate": "Cookie"} if not web_access_token and not admin_access_token else None,
    )


AssetUploaderDependency = Annotated[AssetUploader, Depends(get_asset_uploader)]


def get_admin_management_service(
    request: Request,
    session: DatabaseSession,
    current: Annotated[CurrentAdmin, Depends(get_current_admin)],
) -> AdminManagementService:
    resources = get_resources(request)
    started_at = getattr(request.app.state, "started_at", None)
    return AdminManagementService(
        session=session,
        session_factory=resources.session_factory,
        settings=get_request_settings(request),
        password_manager=resources.password_manager,
        metadata=request_metadata(request),
        actor_id=current.admin.id,
        actor_session_id=current.login_session.id,
        resources=resources,
        started_at=started_at,
    )


AdminManagementServiceDependency = Annotated[AdminManagementService, Depends(get_admin_management_service)]


def get_settings_media_store(request: Request) -> SettingsMediaStore:
    store = getattr(request.app.state, "settings_media_store", None)
    if store is None:
        raise AppException(
            status_code=503,
            code=ErrorCode.SERVICE_UNAVAILABLE,
            message="站点媒体服务尚未就绪",
        )
    return cast(SettingsMediaStore, store)


def get_public_system_settings_service(request: Request, session: DatabaseSession) -> SystemSettingsService:
    resources = get_resources(request)
    return SystemSettingsService(
        session=session,
        session_factory=resources.session_factory,
        settings=get_request_settings(request),
        metadata=request_metadata(request),
        media=get_settings_media_store(request),
    )


def get_admin_system_settings_service(
    request: Request,
    session: DatabaseSession,
    current: Annotated[CurrentAdmin, Depends(get_current_admin)],
) -> SystemSettingsService:
    resources = get_resources(request)
    return SystemSettingsService(
        session=session,
        session_factory=resources.session_factory,
        settings=get_request_settings(request),
        metadata=request_metadata(request),
        actor_id=current.admin.id,
        media=get_settings_media_store(request),
    )


PublicSystemSettingsServiceDependency = Annotated[SystemSettingsService, Depends(get_public_system_settings_service)]
AdminSystemSettingsServiceDependency = Annotated[SystemSettingsService, Depends(get_admin_system_settings_service)]


def require_web_csrf(
    request: Request,
    current: Annotated[CurrentUser, Depends(get_current_user)],
) -> CurrentUser:
    token = require_web_csrf_pair(request)
    settings = get_request_settings(request)
    _, _, web_hmac, _ = settings.authentication_secrets()
    if not hmac.compare_digest(token_digest(token, web_hmac), current.login_session.csrf_digest):
        raise AppException(status_code=403, code=ErrorCode.CSRF_REJECTED, message="CSRF 校验失败")
    return current


def require_admin_csrf(
    request: Request,
    current: Annotated[CurrentAdmin, Depends(get_current_admin)],
) -> CurrentAdmin:
    token = require_admin_csrf_pair(request)
    settings = get_request_settings(request)
    _, _, _, admin_hmac = settings.authentication_secrets()
    if not hmac.compare_digest(token_digest(token, admin_hmac), current.login_session.csrf_digest):
        raise AppException(status_code=403, code=ErrorCode.CSRF_REJECTED, message="CSRF 校验失败")
    return current


def require_superuser(
    current: Annotated[CurrentAdmin, Depends(get_current_admin)],
) -> CurrentAdmin:
    if not current.admin.is_superuser:
        raise AppException(status_code=403, code=ErrorCode.PERMISSION_DENIED, message="仅超级管理员可执行此操作")
    return current


def require_permission(code: PermissionCode) -> Callable[[CurrentAdmin], Awaitable[CurrentAdmin]]:
    async def dependency(current: Annotated[CurrentAdmin, Depends(get_current_admin)]) -> CurrentAdmin:
        if code.value not in current.permissions:
            raise AppException(status_code=403, code=ErrorCode.PERMISSION_DENIED, message="权限不足")
        return current

    return dependency


__all__ = [
    "CurrentAdmin",
    "CurrentUser",
    "AdminAccountServiceDependency",
    "AssetServiceDependency",
    "AssetUploaderDependency",
    "AdminAuthServiceDependency",
    "AdminManagementServiceDependency",
    "AdminSystemSettingsServiceDependency",
    "DatabaseSession",
    "get_current_admin",
    "require_superuser",
    "get_current_user",
    "get_db_session",
    "get_request_settings",
    "get_resources",
    "PublicSystemSettingsServiceDependency",
    "require_admin_csrf",
    "require_admin_csrf_pair",
    "require_admin_access_token",
    "require_admin_origin",
    "require_permission",
    "require_web_csrf",
    "require_web_csrf_pair",
    "require_web_origin",
    "UserAccountServiceDependency",
    "WebAuthServiceDependency",
]
