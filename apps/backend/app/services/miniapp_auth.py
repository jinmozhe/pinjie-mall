import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.cache_keys import cache_keys
from app.core.config import Settings
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.core.identifiers import new_uuid7
from app.core.rate_limit import acquire_refresh_lock, enforce_rate_limit, release_refresh_lock
from app.core.request_metadata import RequestMetadata
from app.core.security import create_access_token, new_opaque_token, token_digest
from app.db.models import User, UserRefreshToken, UserSession
from app.db.repositories import SecurityRepository, SessionRepository, SystemSettingRepository, UserRepository
from app.db.repositories.miniapp import MiniappIdentityRepository
from app.db.transaction import transaction_scope
from app.domains.auth.miniapp_schemas import MiniappSessionRead, MiniappUserRead
from app.domains.settings.schemas import MiniappRegistrationValue
from app.services.security_events import SecurityEventWriter, login_event

_EXCHANGE_FAILURES = (httpx.HTTPError, TimeoutError, ValueError)


def bearer_error(code: ErrorCode = ErrorCode.AUTH_TOKEN_INVALID) -> AppException:
    return AppException(
        status_code=401, code=code, message="登录状态已失效，请重新登录", headers={"WWW-Authenticate": "Bearer"}
    )


class WechatIdentity(BaseModel):
    model_config = ConfigDict(extra="ignore")
    openid: str = Field(min_length=1, max_length=128, repr=False)
    unionid: str | None = Field(default=None, min_length=1, max_length=128, repr=False)


class MiniappAuthService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        session_factory: async_sessionmaker[AsyncSession],
        redis: Redis | None,
        settings: Settings,
        http: httpx.AsyncClient | None,
        metadata: RequestMetadata,
    ) -> None:
        self.session, self.redis, self.settings, self.http, self.metadata = session, redis, settings, http, metadata
        self.sessions, self.users = SessionRepository(session), UserRepository(session)
        self.identities = MiniappIdentityRepository(session)
        self.events = SecurityEventWriter(session_factory)
        self.keys = cache_keys(settings)

    def _keys(self) -> tuple[str, str]:
        if not self.settings.miniapp_login_enabled:
            raise AppException(
                status_code=503, code=ErrorCode.SERVICE_UNAVAILABLE, message="微信登录尚未开放，可继续浏览商品"
            )
        return self.settings.miniapp_secrets()

    async def _exchange(self, code: str) -> WechatIdentity:
        if self.http is None:
            raise AppException(status_code=503, code=ErrorCode.SERVICE_UNAVAILABLE, message="微信登录服务暂时不可用")
        try:
            async with asyncio.timeout(8):
                response = await self.http.get(
                    "https://api.weixin.qq.com/sns/jscode2session",
                    params={
                        "appid": self.settings.wechat_app_id,
                        "secret": self.settings.wechat_app_secret,
                        "js_code": code,
                        "grant_type": "authorization_code",
                    },
                )
            if response.status_code != 200 or len(response.content) > 8192:
                raise AppException(
                    status_code=503, code=ErrorCode.SERVICE_UNAVAILABLE, message="微信登录响应不可用，请重新发起登录"
                )
            body = response.json()
        except _EXCHANGE_FAILURES:
            # Exceptions can contain the full secret-bearing URL; discard the external error and payload.
            raise AppException(
                status_code=503, code=ErrorCode.SERVICE_UNAVAILABLE, message="微信登录结果未确认，请重新发起登录"
            ) from None
        if not isinstance(body, dict):
            raise AppException(status_code=503, code=ErrorCode.SERVICE_UNAVAILABLE, message="微信登录响应无效")
        code_value = body.get("errcode", 0)
        if code_value != 0:
            if code_value in (40029, 40163):
                raise bearer_error(ErrorCode.AUTH_INVALID_CREDENTIALS)
            raise AppException(
                status_code=503, code=ErrorCode.SERVICE_UNAVAILABLE, message="微信登录暂时不可用，请稍后重新发起"
            )
        try:
            return WechatIdentity.model_validate(body)
        except ValidationError:
            raise AppException(
                status_code=503, code=ErrorCode.SERVICE_UNAVAILABLE, message="微信身份响应无效"
            ) from None

    def _event(self, user_id: UUID | None, event: str, reason: str, *, success: bool = True) -> None:
        SecurityRepository(self.session).add_login_event(
            login_event(
                principal_type="user",
                principal_id=user_id,
                identifier_digest=None,
                event_type=event,
                succeeded=success,
                reason_code=reason,
                metadata=self.metadata,
            )
        )

    def _artifacts(self, user: User, login_session: UserSession, raw_refresh: str) -> MiniappSessionRead:
        secret, _ = self._keys()
        access, expiry = create_access_token(
            subject_id=user.id,
            session_id=login_session.id,
            credential_version=user.credential_version,
            audience="pinjie-miniapp",
            issuer=self.settings.jwt_issuer,
            secret=secret,
            ttl_seconds=self.settings.web_access_ttl_seconds,
        )
        return MiniappSessionRead(
            user=MiniappUserRead.model_validate(user),
            session_id=login_session.id,
            access_token=access,
            refresh_token=raw_refresh,
            access_expires_at=expiry,
            idle_expires_at=login_session.idle_expires_at,
            absolute_expires_at=login_session.absolute_expires_at,
        )

    async def login(self, code: str) -> MiniappSessionRead:
        try:
            return await self._login(code)
        except AppException as exc:
            await self.events.record_login(
                login_event(
                    principal_type="user",
                    principal_id=None,
                    identifier_digest=None,
                    event_type="miniapp_login",
                    succeeded=False,
                    reason_code=exc.code,
                    metadata=self.metadata,
                )
            )
            raise

    async def _login(self, code: str) -> MiniappSessionRead:
        _, hmac_key = self._keys()
        await enforce_rate_limit(
            self.redis,
            key=self.keys.miniapp("login-ip", token_digest(self.metadata.ip_address or "unknown", hmac_key)),
            limit=self.settings.web_login_limit,
            window_seconds=self.settings.login_window_seconds,
        )
        identity = await self._exchange(code)
        app_id = self.settings.wechat_app_id
        if app_id is None:
            raise RuntimeError("Enabled WeChat login requires an app id")
        async with transaction_scope(self.session):
            await self.identities.lock_subject(app_id, identity.openid)
            binding = await self.identities.identity(app_id, identity.openid)
            if binding is None:
                setting = await SystemSettingRepository(self.session).get("miniapp_registration", for_share=True)
                if setting is None:
                    raise AppException(
                        status_code=503, code=ErrorCode.SERVICE_UNAVAILABLE, message="小程序建号设置不可用"
                    )
                try:
                    value = MiniappRegistrationValue.model_validate(setting.setting_value)
                except ValidationError:
                    raise AppException(
                        status_code=503, code=ErrorCode.SERVICE_UNAVAILABLE, message="小程序建号设置无效"
                    ) from None
                if not value.enabled:
                    raise AppException(
                        status_code=403,
                        code=ErrorCode.REGISTRATION_CLOSED,
                        message="小程序首次建号已关闭，已有账户仍可登录",
                    )
                user = User(
                    id=new_uuid7(),
                    username=f"wx_{new_uuid7().hex}",
                    password_hash=None,
                    display_name=None,
                    email=None,
                    avatar=None,
                    is_active=True,
                    credential_version=1,
                    deleted_at=None,
                )
                self.users.add(user)
                await self.session.flush()
                self.identities.add(user.id, app_id, identity.openid, identity.unionid)
            else:
                found = await self.users.get(binding.user_id, for_update=True)
                if found is None:
                    raise bearer_error()
                user = found
            if not user.is_active or user.deleted_at is not None:
                raise AppException(status_code=403, code=ErrorCode.AUTH_ACCOUNT_DISABLED, message="账户已停用")
            now = datetime.now(UTC)
            absolute = now + timedelta(days=self.settings.session_absolute_ttl_days)
            idle = min(now + timedelta(days=self.settings.refresh_idle_ttl_days), absolute)
            login_session = UserSession(
                id=new_uuid7(),
                user_id=user.id,
                family_id=new_uuid7(),
                credential_profile="miniapp_bearer",
                client_id="pinjie-miniapp",
                csrf_digest=None,
                ip_address=self.metadata.ip_address,
                user_agent_summary=self.metadata.user_agent_summary,
                device_name="微信小程序",
                last_seen_at=now,
                idle_expires_at=idle,
                absolute_expires_at=absolute,
            )
            raw = new_opaque_token()
            refresh = UserRefreshToken(
                id=new_uuid7(),
                session_id=login_session.id,
                token_digest=token_digest(raw, hmac_key),
                issued_at=now,
                expires_at=idle,
            )
            self.sessions.add_web(login_session, refresh)
            self._event(user.id, "miniapp_login", "AUTHENTICATED")
            result = self._artifacts(user, login_session, raw)
        return result

    async def refresh(self, raw_refresh: str) -> MiniappSessionRead:
        _, hmac_key = self._keys()
        digest = token_digest(raw_refresh, hmac_key)
        lock_key, owner = self.keys.miniapp("refresh-lock", digest), str(new_uuid7())
        if not await acquire_refresh_lock(self.redis, key=lock_key, owner=owner):
            raise AppException(
                status_code=429, code=ErrorCode.RATE_LIMITED, message="会话刷新正在进行中", headers={"Retry-After": "1"}
            )
        terminal: ErrorCode | None = None
        result: MiniappSessionRead | None = None
        try:
            async with transaction_scope(self.session):
                current = await self.sessions.get_web_refresh_for_update(digest)
                if current is None:
                    raise bearer_error()
                login_session = await self.sessions.get_web(current.session_id, for_update=True)
                if (
                    login_session is None
                    or login_session.credential_profile != "miniapp_bearer"
                    or login_session.client_id != "pinjie-miniapp"
                ):
                    raise bearer_error()
                now = datetime.now(UTC)
                if current.consumed_at is not None:
                    login_session.revoked_at = login_session.revoked_at or now
                    login_session.revoke_reason = "refresh_reuse"
                    await self.sessions.revoke_web_refresh_tokens(login_session.id, reason="refresh_reuse", now=now)
                    self._event(login_session.user_id, "miniapp_refresh_reuse", "REFRESH_REUSE_DETECTED", success=False)
                    terminal = ErrorCode.AUTH_REFRESH_REUSE_DETECTED
                elif current.revoked_at is not None or login_session.revoked_at is not None:
                    raise bearer_error(ErrorCode.AUTH_SESSION_REVOKED)
                elif (
                    current.expires_at <= now
                    or login_session.idle_expires_at <= now
                    or login_session.absolute_expires_at <= now
                ):
                    login_session.revoked_at, login_session.revoke_reason = now, "expired"
                    terminal = ErrorCode.AUTH_SESSION_EXPIRED
                elif not login_session.user.is_active or login_session.user.deleted_at is not None:
                    raise AppException(status_code=403, code=ErrorCode.AUTH_ACCOUNT_DISABLED, message="账户已停用")
                else:
                    raw = new_opaque_token()
                    idle = min(
                        now + timedelta(days=self.settings.refresh_idle_ttl_days), login_session.absolute_expires_at
                    )
                    replacement = UserRefreshToken(
                        id=new_uuid7(),
                        session_id=login_session.id,
                        token_digest=token_digest(raw, hmac_key),
                        issued_at=now,
                        expires_at=idle,
                    )
                    self.session.add(replacement)
                    await self.session.flush()
                    current.consumed_at, current.replaced_by_id = now, replacement.id
                    login_session.last_seen_at, login_session.idle_expires_at = now, idle
                    self._event(login_session.user_id, "miniapp_refresh", "ROTATED")
                    result = self._artifacts(login_session.user, login_session, raw)
            if terminal is not None:
                raise bearer_error(terminal)
            if result is None:
                raise RuntimeError("Miniapp refresh did not produce credentials")
            return result
        finally:
            await release_refresh_lock(self.redis, key=lock_key, owner=owner)

    async def logout(self, user_id: UUID, session_id: UUID) -> None:
        async with transaction_scope(self.session):
            current = await self.sessions.get_web(session_id, for_update=True)
            if current is None or current.user_id != user_id or current.credential_profile != "miniapp_bearer":
                raise bearer_error()
            now = datetime.now(UTC)
            current.revoked_at, current.revoke_reason = current.revoked_at or now, "logout"
            await self.sessions.revoke_web_refresh_tokens(session_id, reason="logout", now=now)
            self._event(user_id, "miniapp_logout", "LOGGED_OUT")
