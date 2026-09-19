import hmac
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from pydantic import ValidationError
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.cache_keys import CacheKeys, cache_keys
from app.core.client_identity import session_device_name
from app.core.config import Settings
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.core.identifiers import new_uuid7
from app.core.rate_limit import acquire_refresh_lock, enforce_rate_limit, release_refresh_lock
from app.core.request_metadata import RequestMetadata
from app.core.security import PasswordManager, create_access_token, new_opaque_token, token_digest
from app.db.models import Admin, AdminRefreshToken, AdminSession, User, UserRefreshToken, UserSession
from app.db.repositories import (
    AdminRepository,
    SecurityRepository,
    SessionRepository,
    SystemSettingRepository,
    UserRepository,
)
from app.db.transaction import transaction_scope
from app.domains.admin.schemas import AdminLoginIn
from app.domains.auth.schemas import UserLoginIn, UserRegisterIn
from app.domains.settings.schemas import RegistrationSettingValue
from app.services.security_events import SecurityEventWriter, login_event


@dataclass(frozen=True, slots=True)
class SessionArtifacts:
    session_id: uuid.UUID
    access_token: str
    refresh_token: str
    csrf_token: str
    access_expires_at: datetime
    idle_expires_at: datetime
    absolute_expires_at: datetime


def _auth_error(code: ErrorCode = ErrorCode.AUTH_INVALID_CREDENTIALS) -> AppException:
    return AppException(
        status_code=401,
        code=code,
        message="身份认证凭据无效",
        headers={"WWW-Authenticate": "Cookie"},
    )


class _AuthBase:
    def __init__(
        self,
        *,
        session: AsyncSession,
        session_factory: async_sessionmaker[AsyncSession],
        redis: Redis | None,
        settings: Settings,
        password_manager: PasswordManager,
        metadata: RequestMetadata,
        admin: bool,
    ) -> None:
        self.session = session
        self.session_factory = session_factory
        self.redis = redis
        self.settings = settings
        self.password_manager = password_manager
        self.metadata = metadata
        self.admin = admin
        self.keys: CacheKeys = cache_keys(settings)
        web_secret, admin_secret, web_hmac, admin_hmac = settings.authentication_secrets()
        self.jwt_secret = admin_secret if admin else web_secret
        self.hmac_key = admin_hmac if admin else web_hmac
        self.event_writer = SecurityEventWriter(session_factory)

    async def enforce_login_limit(self, identifier: str) -> None:
        identifier_key = self.keys.login_identifier(token_digest(identifier, self.hmac_key), admin=self.admin)
        ip_key = self.keys.login_ip(
            token_digest(self.metadata.ip_address or "unknown", self.hmac_key), admin=self.admin
        )
        limit = self.settings.admin_login_limit if self.admin else self.settings.web_login_limit
        await enforce_rate_limit(
            self.redis,
            key=identifier_key,
            limit=limit,
            window_seconds=self.settings.login_window_seconds,
        )
        await enforce_rate_limit(
            self.redis,
            key=ip_key,
            limit=max(limit * 4, 20),
            window_seconds=self.settings.login_window_seconds,
        )

    async def clear_login_limit(self, identifier: str) -> None:
        from loguru import logger

        if self.redis is None:
            logger.bind(
                auth_profile="admin" if self.admin else "web",
                request_id=self.metadata.request_id,
            ).warning("login rate-limit cleanup skipped because Redis is unavailable")
            return
        keys = (
            self.keys.login_identifier(token_digest(identifier, self.hmac_key), admin=self.admin),
            self.keys.login_ip(token_digest(self.metadata.ip_address or "unknown", self.hmac_key), admin=self.admin),
        )
        try:
            await self.redis.delete(*keys)
        except RedisError as exc:
            logger.bind(
                auth_profile="admin" if self.admin else "web",
                request_id=self.metadata.request_id,
            ).opt(exception=exc).warning("login rate-limit cleanup failed after authentication succeeded")

    async def record_failure(
        self,
        *,
        identifier: str,
        event_type: str,
        reason_code: str,
        principal_id: uuid.UUID | None = None,
    ) -> None:
        await self.event_writer.record_login(
            login_event(
                principal_type="admin" if self.admin else "user",
                principal_id=principal_id,
                identifier_digest=token_digest(identifier, self.hmac_key),
                event_type=event_type,
                succeeded=False,
                reason_code=reason_code,
                metadata=self.metadata,
            )
        )

    def _session_times(self, now: datetime) -> tuple[datetime, datetime]:
        absolute = now + timedelta(days=self.settings.session_absolute_ttl_days)
        idle = min(now + timedelta(days=self.settings.refresh_idle_ttl_days), absolute)
        return idle, absolute

    def _access_token(
        self, *, subject_id: uuid.UUID, session_id: uuid.UUID, credential_version: int
    ) -> tuple[str, datetime]:
        return create_access_token(
            subject_id=subject_id,
            session_id=session_id,
            credential_version=credential_version,
            audience="pinjie-admin" if self.admin else "pinjie-web",
            issuer=self.settings.jwt_issuer,
            secret=self.jwt_secret,
            ttl_seconds=self.settings.admin_access_ttl_seconds if self.admin else self.settings.web_access_ttl_seconds,
        )

    @staticmethod
    def _verify_session_csrf(csrf_token: str, csrf_digest: str, key: str) -> None:
        if not hmac.compare_digest(token_digest(csrf_token, key), csrf_digest):
            raise AppException(status_code=403, code=ErrorCode.CSRF_REJECTED, message="CSRF 校验失败")


class WebAuthService(_AuthBase):
    def __init__(
        self,
        *,
        session: AsyncSession,
        session_factory: async_sessionmaker[AsyncSession],
        redis: Redis | None,
        settings: Settings,
        password_manager: PasswordManager,
        metadata: RequestMetadata,
    ) -> None:
        super().__init__(
            session=session,
            session_factory=session_factory,
            redis=redis,
            settings=settings,
            password_manager=password_manager,
            metadata=metadata,
            admin=False,
        )
        self.users = UserRepository(session)
        self.sessions = SessionRepository(session)

    async def register(self, payload: UserRegisterIn) -> tuple[User, SessionArtifacts]:
        await self.enforce_login_limit(payload.username)
        password_hash = await self.password_manager.hash(payload.password)
        now = datetime.now(UTC)
        user = User(
            id=new_uuid7(),
            username=payload.username,
            email=payload.email,
            display_name=payload.display_name.strip() if payload.display_name else None,
            password_hash=password_hash,
            is_active=True,
            credential_version=1,
            deleted_at=None,
        )
        artifacts, login_session, refresh = self._new_session(user, now)
        event = login_event(
            principal_type="user",
            principal_id=user.id,
            identifier_digest=token_digest(payload.username, self.hmac_key),
            event_type="register",
            succeeded=True,
            reason_code="REGISTERED",
            metadata=self.metadata,
            now=now,
        )
        try:
            async with transaction_scope(self.session):
                try:
                    registration = await SystemSettingRepository(self.session).get("registration", for_share=True)
                    registration_value = (
                        RegistrationSettingValue.model_validate(registration.setting_value)
                        if registration is not None
                        else None
                    )
                except (SQLAlchemyError, ValidationError, TypeError) as exc:
                    raise AppException(
                        status_code=503,
                        code=ErrorCode.SERVICE_UNAVAILABLE,
                        message="注册服务暂时不可用",
                    ) from exc
                if registration_value is None or not registration_value.enabled:
                    raise AppException(
                        status_code=403,
                        code=ErrorCode.REGISTRATION_CLOSED,
                        message="用户注册功能已关闭",
                    )
                if await self.users.get_by_username(payload.username) is not None:
                    raise AppException(
                        status_code=409,
                        code=ErrorCode.USER_USERNAME_CONFLICT,
                        message="用户名已被注册",
                    )
                if payload.email and await self.users.get_by_email(payload.email) is not None:
                    raise AppException(
                        status_code=409,
                        code=ErrorCode.STATE_CONFLICT,
                        message="邮箱已被使用",
                    )
                self.users.add(user)
                self.sessions.add_web(login_session, refresh)
                SecurityRepository(self.session).add_login_event(event)
        except IntegrityError as exc:
            raise AppException(
                status_code=409,
                code=ErrorCode.USER_USERNAME_CONFLICT,
                message="用户名或邮箱已被注册",
            ) from exc
        await self.clear_login_limit(payload.username)
        return user, artifacts

    async def login(self, payload: UserLoginIn) -> tuple[User, SessionArtifacts]:
        await self.enforce_login_limit(payload.username)
        user = await self.users.get_by_username(payload.username)
        if user is None:
            await self.password_manager.verify_unknown_user(payload.password)
            await self.record_failure(
                identifier=payload.username,
                event_type="login",
                reason_code="INVALID_CREDENTIALS",
            )
            raise _auth_error()
        verified_password_hash = user.password_hash
        verified_credential_version = user.credential_version
        verified, updated_hash = await self.password_manager.verify_and_update(payload.password, verified_password_hash)
        # 账户状态检查在密码验证之前拒绝，防止通过响应差异泄露"密码正确但已禁用"的信息。
        if not user.is_active or user.deleted_at is not None:
            await self.record_failure(
                identifier=payload.username,
                event_type="login",
                reason_code="ACCOUNT_DISABLED",
                principal_id=user.id,
            )
            raise AppException(status_code=403, code=ErrorCode.AUTH_ACCOUNT_DISABLED, message="账户已停用")
        if not verified:
            await self.record_failure(
                identifier=payload.username,
                event_type="login",
                reason_code="INVALID_CREDENTIALS",
                principal_id=user.id,
            )
            raise _auth_error()

        now = datetime.now(UTC)
        artifacts, login_session, refresh = self._new_session(user, now)
        event = login_event(
            principal_type="user",
            principal_id=user.id,
            identifier_digest=token_digest(payload.username, self.hmac_key),
            event_type="login",
            succeeded=True,
            reason_code="AUTHENTICATED",
            metadata=self.metadata,
            now=now,
        )
        async with transaction_scope(self.session):
            locked = await self.users.get(user.id, for_update=True)
            if locked is None or not locked.is_active or locked.deleted_at is not None:
                raise AppException(status_code=403, code=ErrorCode.AUTH_ACCOUNT_DISABLED, message="账户已停用")
            if (
                locked.password_hash != verified_password_hash
                or locked.credential_version != verified_credential_version
            ):
                raise _auth_error()
            if updated_hash is not None:
                locked.password_hash = updated_hash
            self.sessions.add_web(login_session, refresh)
            SecurityRepository(self.session).add_login_event(event)
        await self.clear_login_limit(payload.username)
        return user, artifacts

    def _new_session(self, user: User, now: datetime) -> tuple[SessionArtifacts, UserSession, UserRefreshToken]:
        idle, absolute = self._session_times(now)
        session_id = new_uuid7()
        refresh_id = new_uuid7()
        csrf_token = new_opaque_token()
        refresh_token = new_opaque_token()
        login_session = UserSession(
            id=session_id,
            user_id=user.id,
            family_id=new_uuid7(),
            credential_profile="browser_cookie",
            client_id="pinjie-web",
            csrf_digest=token_digest(csrf_token, self.hmac_key),
            ip_address=self.metadata.ip_address,
            user_agent_summary=self.metadata.user_agent_summary,
            device_name=session_device_name(self.metadata.user_agent_summary),
            last_seen_at=now,
            idle_expires_at=idle,
            absolute_expires_at=absolute,
            revoked_at=None,
            revoke_reason=None,
        )
        refresh = UserRefreshToken(
            id=refresh_id,
            session_id=session_id,
            token_digest=token_digest(refresh_token, self.hmac_key),
            issued_at=now,
            expires_at=idle,
            consumed_at=None,
            revoked_at=None,
            revoke_reason=None,
            replaced_by_id=None,
        )
        access_token, access_expires_at = self._access_token(
            subject_id=user.id,
            session_id=session_id,
            credential_version=user.credential_version,
        )
        return (
            SessionArtifacts(
                session_id=session_id,
                access_token=access_token,
                refresh_token=refresh_token,
                csrf_token=csrf_token,
                access_expires_at=access_expires_at,
                idle_expires_at=idle,
                absolute_expires_at=absolute,
            ),
            login_session,
            refresh,
        )

    async def refresh(self, refresh_token: str, csrf_token: str) -> SessionArtifacts:
        digest = token_digest(refresh_token, self.hmac_key)
        lock_key = self.keys.refresh_lock(digest)
        owner = str(new_uuid7())
        if not await acquire_refresh_lock(self.redis, key=lock_key, owner=owner):
            raise AppException(
                status_code=429,
                code=ErrorCode.RATE_LIMITED,
                message="会话刷新正在进行中",
                details={"retry_after": 1},
                headers={"Retry-After": "1"},
            )
        terminal_error: ErrorCode | None = None
        artifacts: SessionArtifacts | None = None
        try:
            async with transaction_scope(self.session):
                current = await self.sessions.get_web_refresh_for_update(digest)
                if current is None:
                    raise _auth_error(ErrorCode.AUTH_TOKEN_INVALID)
                login_session = current.session
                now = datetime.now(UTC)
                if current.consumed_at is not None:
                    login_session.revoked_at = login_session.revoked_at or now
                    login_session.revoke_reason = "refresh_reuse"
                    SecurityRepository(self.session).add_login_event(
                        login_event(
                            principal_type="user",
                            principal_id=login_session.user_id,
                            identifier_digest=None,
                            event_type="refresh_reuse",
                            succeeded=False,
                            reason_code="REFRESH_REUSE_DETECTED",
                            metadata=self.metadata,
                            now=now,
                        )
                    )
                    terminal_error = ErrorCode.AUTH_REFRESH_REUSE_DETECTED
                else:
                    self._verify_session_csrf(csrf_token, login_session.csrf_digest, self.hmac_key)
                    if current.revoked_at is not None or login_session.revoked_at is not None:
                        raise _auth_error(ErrorCode.AUTH_SESSION_REVOKED)
                    if current.expires_at <= now or login_session.absolute_expires_at <= now:
                        login_session.revoked_at = now
                        login_session.revoke_reason = "expired"
                        terminal_error = ErrorCode.AUTH_SESSION_EXPIRED
                    elif not login_session.user.is_active or login_session.user.deleted_at is not None:
                        raise AppException(
                            status_code=403,
                            code=ErrorCode.AUTH_ACCOUNT_DISABLED,
                            message="账户已停用",
                        )
                    else:
                        new_refresh_token = new_opaque_token()
                        new_csrf_token = new_opaque_token()
                        idle = min(
                            now + timedelta(days=self.settings.refresh_idle_ttl_days), login_session.absolute_expires_at
                        )
                        replacement = UserRefreshToken(
                            id=new_uuid7(),
                            session_id=login_session.id,
                            token_digest=token_digest(new_refresh_token, self.hmac_key),
                            issued_at=now,
                            expires_at=idle,
                            consumed_at=None,
                            revoked_at=None,
                            revoke_reason=None,
                            replaced_by_id=None,
                        )
                        self.session.add(replacement)
                        await self.session.flush()
                        current.consumed_at = now
                        current.replaced_by_id = replacement.id
                        login_session.csrf_digest = token_digest(new_csrf_token, self.hmac_key)
                        login_session.last_seen_at = now
                        login_session.idle_expires_at = idle
                        SecurityRepository(self.session).add_login_event(
                            login_event(
                                principal_type="user",
                                principal_id=login_session.user_id,
                                identifier_digest=None,
                                event_type="refresh",
                                succeeded=True,
                                reason_code="ROTATED",
                                metadata=self.metadata,
                                now=now,
                            )
                        )
                        access_token, access_expires_at = self._access_token(
                            subject_id=login_session.user_id,
                            session_id=login_session.id,
                            credential_version=login_session.user.credential_version,
                        )
                        artifacts = SessionArtifacts(
                            session_id=login_session.id,
                            access_token=access_token,
                            refresh_token=new_refresh_token,
                            csrf_token=new_csrf_token,
                            access_expires_at=access_expires_at,
                            idle_expires_at=idle,
                            absolute_expires_at=login_session.absolute_expires_at,
                        )
            if terminal_error is not None:
                raise _auth_error(terminal_error)
            if artifacts is None:
                raise AppException(
                    status_code=500,
                    code=ErrorCode.INTERNAL_ERROR,
                    message="身份认证会话刷新未产生结果",
                )
            return artifacts
        finally:
            await release_refresh_lock(self.redis, key=lock_key, owner=owner)

    async def logout(self, refresh_token: str, csrf_token: str) -> None:
        digest = token_digest(refresh_token, self.hmac_key)
        async with transaction_scope(self.session):
            current = await self.sessions.get_web_refresh_for_update(digest)
            if current is None:
                raise _auth_error(ErrorCode.AUTH_TOKEN_INVALID)
            self._verify_session_csrf(csrf_token, current.session.csrf_digest, self.hmac_key)
            now = datetime.now(UTC)
            current.session.revoked_at = current.session.revoked_at or now
            current.session.revoke_reason = "logout"
            await self.sessions.revoke_web_refresh_tokens(current.session_id, reason="logout", now=now)
            SecurityRepository(self.session).add_login_event(
                login_event(
                    principal_type="user",
                    principal_id=current.session.user_id,
                    identifier_digest=None,
                    event_type="logout",
                    succeeded=True,
                    reason_code="LOGGED_OUT",
                    metadata=self.metadata,
                    now=now,
                )
            )


class AdminAuthService(_AuthBase):
    def __init__(
        self,
        *,
        session: AsyncSession,
        session_factory: async_sessionmaker[AsyncSession],
        redis: Redis | None,
        settings: Settings,
        password_manager: PasswordManager,
        metadata: RequestMetadata,
    ) -> None:
        super().__init__(
            session=session,
            session_factory=session_factory,
            redis=redis,
            settings=settings,
            password_manager=password_manager,
            metadata=metadata,
            admin=True,
        )
        self.admins = AdminRepository(session)
        self.sessions = SessionRepository(session)

    async def login(self, payload: AdminLoginIn) -> tuple[Admin, SessionArtifacts]:
        await self.enforce_login_limit(payload.username)
        admin = await self.admins.get_by_username(payload.username)
        if admin is None:
            await self.password_manager.verify_unknown_user(payload.password)
            await self.record_failure(
                identifier=payload.username, event_type="login", reason_code="INVALID_CREDENTIALS"
            )
            raise _auth_error()
        verified_password_hash = admin.password_hash
        verified_credential_version = admin.credential_version
        verified, updated_hash = await self.password_manager.verify_and_update(payload.password, verified_password_hash)
        # 账户状态检查在密码验证之前拒绝，防止通过响应差异泄露"密码正确但已禁用"的信息。
        if not admin.is_active:
            await self.record_failure(
                identifier=payload.username,
                event_type="login",
                reason_code="ACCOUNT_DISABLED",
                principal_id=admin.id,
            )
            raise AppException(status_code=403, code=ErrorCode.AUTH_ACCOUNT_DISABLED, message="账户已停用")
        if not verified:
            await self.record_failure(
                identifier=payload.username,
                event_type="login",
                reason_code="INVALID_CREDENTIALS",
                principal_id=admin.id,
            )
            raise _auth_error()
        now = datetime.now(UTC)
        artifacts, login_session, refresh = self._new_session(admin, now)
        async with transaction_scope(self.session):
            locked = await self.admins.get(admin.id, for_update=True)
            if locked is None or not locked.is_active:
                raise AppException(status_code=403, code=ErrorCode.AUTH_ACCOUNT_DISABLED, message="账户已停用")
            if (
                locked.password_hash != verified_password_hash
                or locked.credential_version != verified_credential_version
            ):
                raise _auth_error()
            if updated_hash is not None:
                locked.password_hash = updated_hash
            self.sessions.add_admin(login_session, refresh)
            SecurityRepository(self.session).add_login_event(
                login_event(
                    principal_type="admin",
                    principal_id=admin.id,
                    identifier_digest=token_digest(payload.username, self.hmac_key),
                    event_type="login",
                    succeeded=True,
                    reason_code="AUTHENTICATED",
                    metadata=self.metadata,
                    now=now,
                )
            )
        await self.clear_login_limit(payload.username)
        return admin, artifacts

    def _new_session(self, admin: Admin, now: datetime) -> tuple[SessionArtifacts, AdminSession, AdminRefreshToken]:
        idle, absolute = self._session_times(now)
        session_id = new_uuid7()
        csrf_token = new_opaque_token()
        refresh_token = new_opaque_token()
        login_session = AdminSession(
            id=session_id,
            admin_id=admin.id,
            family_id=new_uuid7(),
            credential_profile="browser_cookie",
            client_id="pinjie-admin",
            csrf_digest=token_digest(csrf_token, self.hmac_key),
            ip_address=self.metadata.ip_address,
            user_agent_summary=self.metadata.user_agent_summary,
            device_name=session_device_name(self.metadata.user_agent_summary),
            last_seen_at=now,
            idle_expires_at=idle,
            absolute_expires_at=absolute,
            revoked_at=None,
            revoke_reason=None,
        )
        refresh = AdminRefreshToken(
            id=new_uuid7(),
            session_id=session_id,
            token_digest=token_digest(refresh_token, self.hmac_key),
            issued_at=now,
            expires_at=idle,
            consumed_at=None,
            revoked_at=None,
            revoke_reason=None,
            replaced_by_id=None,
        )
        access_token, access_expires_at = self._access_token(
            subject_id=admin.id,
            session_id=session_id,
            credential_version=admin.credential_version,
        )
        return (
            SessionArtifacts(
                session_id=session_id,
                access_token=access_token,
                refresh_token=refresh_token,
                csrf_token=csrf_token,
                access_expires_at=access_expires_at,
                idle_expires_at=idle,
                absolute_expires_at=absolute,
            ),
            login_session,
            refresh,
        )

    async def refresh(self, refresh_token: str, csrf_token: str) -> SessionArtifacts:
        digest = token_digest(refresh_token, self.hmac_key)
        lock_key = self.keys.refresh_lock(digest, admin=True)
        owner = str(new_uuid7())
        if not await acquire_refresh_lock(self.redis, key=lock_key, owner=owner):
            raise AppException(
                status_code=429,
                code=ErrorCode.RATE_LIMITED,
                message="会话刷新正在进行中",
                details={"retry_after": 1},
                headers={"Retry-After": "1"},
            )
        terminal_error: ErrorCode | None = None
        artifacts: SessionArtifacts | None = None
        try:
            async with transaction_scope(self.session):
                current = await self.sessions.get_admin_refresh_for_update(digest)
                if current is None:
                    raise _auth_error(ErrorCode.AUTH_TOKEN_INVALID)
                login_session = current.session
                now = datetime.now(UTC)
                if current.consumed_at is not None:
                    login_session.revoked_at = login_session.revoked_at or now
                    login_session.revoke_reason = "refresh_reuse"
                    SecurityRepository(self.session).add_login_event(
                        login_event(
                            principal_type="admin",
                            principal_id=login_session.admin_id,
                            identifier_digest=None,
                            event_type="refresh_reuse",
                            succeeded=False,
                            reason_code="REFRESH_REUSE_DETECTED",
                            metadata=self.metadata,
                            now=now,
                        )
                    )
                    terminal_error = ErrorCode.AUTH_REFRESH_REUSE_DETECTED
                else:
                    self._verify_session_csrf(csrf_token, login_session.csrf_digest, self.hmac_key)
                    if current.revoked_at is not None or login_session.revoked_at is not None:
                        raise _auth_error(ErrorCode.AUTH_SESSION_REVOKED)
                    if current.expires_at <= now or login_session.absolute_expires_at <= now:
                        login_session.revoked_at = now
                        login_session.revoke_reason = "expired"
                        terminal_error = ErrorCode.AUTH_SESSION_EXPIRED
                    elif not login_session.admin.is_active:
                        raise AppException(
                            status_code=403,
                            code=ErrorCode.AUTH_ACCOUNT_DISABLED,
                            message="账户已停用",
                        )
                    else:
                        new_refresh_token = new_opaque_token()
                        new_csrf_token = new_opaque_token()
                        idle = min(
                            now + timedelta(days=self.settings.refresh_idle_ttl_days), login_session.absolute_expires_at
                        )
                        replacement = AdminRefreshToken(
                            id=new_uuid7(),
                            session_id=login_session.id,
                            token_digest=token_digest(new_refresh_token, self.hmac_key),
                            issued_at=now,
                            expires_at=idle,
                            consumed_at=None,
                            revoked_at=None,
                            revoke_reason=None,
                            replaced_by_id=None,
                        )
                        self.session.add(replacement)
                        await self.session.flush()
                        current.consumed_at = now
                        current.replaced_by_id = replacement.id
                        login_session.csrf_digest = token_digest(new_csrf_token, self.hmac_key)
                        login_session.last_seen_at = now
                        login_session.idle_expires_at = idle
                        SecurityRepository(self.session).add_login_event(
                            login_event(
                                principal_type="admin",
                                principal_id=login_session.admin_id,
                                identifier_digest=None,
                                event_type="refresh",
                                succeeded=True,
                                reason_code="ROTATED",
                                metadata=self.metadata,
                                now=now,
                            )
                        )
                        access_token, access_expires_at = self._access_token(
                            subject_id=login_session.admin_id,
                            session_id=login_session.id,
                            credential_version=login_session.admin.credential_version,
                        )
                        artifacts = SessionArtifacts(
                            session_id=login_session.id,
                            access_token=access_token,
                            refresh_token=new_refresh_token,
                            csrf_token=new_csrf_token,
                            access_expires_at=access_expires_at,
                            idle_expires_at=idle,
                            absolute_expires_at=login_session.absolute_expires_at,
                        )
            if terminal_error is not None:
                raise _auth_error(terminal_error)
            if artifacts is None:
                raise AppException(
                    status_code=500,
                    code=ErrorCode.INTERNAL_ERROR,
                    message="身份认证会话刷新未产生结果",
                )
            return artifacts
        finally:
            await release_refresh_lock(self.redis, key=lock_key, owner=owner)

    async def logout(self, refresh_token: str, csrf_token: str) -> None:
        digest = token_digest(refresh_token, self.hmac_key)
        async with transaction_scope(self.session):
            current = await self.sessions.get_admin_refresh_for_update(digest)
            if current is None:
                raise _auth_error(ErrorCode.AUTH_TOKEN_INVALID)
            self._verify_session_csrf(csrf_token, current.session.csrf_digest, self.hmac_key)
            now = datetime.now(UTC)
            current.session.revoked_at = current.session.revoked_at or now
            current.session.revoke_reason = "logout"
            await self.sessions.revoke_admin_refresh_tokens(current.session_id, reason="logout", now=now)
            SecurityRepository(self.session).add_login_event(
                login_event(
                    principal_type="admin",
                    principal_id=current.session.admin_id,
                    identifier_digest=None,
                    event_type="logout",
                    succeeded=True,
                    reason_code="LOGGED_OUT",
                    metadata=self.metadata,
                    now=now,
                )
            )


__all__ = ["AdminAuthService", "SessionArtifacts", "WebAuthService"]
