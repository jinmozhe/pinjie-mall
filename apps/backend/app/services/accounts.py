import uuid
from datetime import UTC, datetime, timedelta

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.core.identifiers import new_uuid7
from app.core.request_metadata import RequestMetadata
from app.core.security import (
    PasswordManager,
    create_access_token,
    new_opaque_token,
    token_digest,
)
from app.db.models import Admin, AdminRefreshToken, AdminSession, User, UserRefreshToken, UserSession
from app.db.repositories import AdminRepository, AssetRepository, SecurityRepository, SessionRepository, UserRepository
from app.db.transaction import transaction_scope
from app.domains.admin.schemas import AdminConfirmIn, AdminConfirmOut, AdminProfileUpdateIn
from app.domains.assets.schemas import UploaderType, UploadScene
from app.domains.users.schemas import AccountDeleteIn, PasswordChangeIn, UserAvatarUpdateIn, UserUpdateIn
from app.services.assets import resolve_admin_avatar
from app.services.authentication import SessionArtifacts
from app.services.security_events import login_event


class UserAccountService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        settings: Settings,
        password_manager: PasswordManager,
        metadata: RequestMetadata,
    ) -> None:
        self.session = session
        self.settings = settings
        self.password_manager = password_manager
        self.metadata = metadata
        self.users = UserRepository(session)
        self.assets = AssetRepository(session)
        self.sessions = SessionRepository(session)
        web_secret, _, web_hmac, _ = settings.authentication_secrets()
        self.jwt_secret = web_secret
        self.hmac_key = web_hmac

    async def update_profile(self, user_id: uuid.UUID, payload: UserUpdateIn) -> User:
        async with transaction_scope(self.session):
            user = await self.users.get(user_id, for_update=True)
            if user is None or user.deleted_at is not None:
                raise AppException(status_code=404, code=ErrorCode.USER_NOT_FOUND, message="用户不存在")
            if "email" in payload.model_fields_set and payload.email:
                existing = await self.users.get_by_email(payload.email)
                if existing is not None and existing.id != user.id:
                    raise AppException(
                        status_code=409,
                        code=ErrorCode.STATE_CONFLICT,
                        message="邮箱已被使用",
                    )
            if "display_name" in payload.model_fields_set:
                user.display_name = payload.display_name.strip() if payload.display_name else None
            if "email" in payload.model_fields_set:
                user.email = payload.email
        return user

    async def update_avatar(self, user_id: uuid.UUID, payload: UserAvatarUpdateIn) -> User:
        async with transaction_scope(self.session):
            user = await self.users.get(user_id, for_update=True)
            if user is None or user.deleted_at is not None:
                raise AppException(status_code=404, code=ErrorCode.USER_NOT_FOUND, message="用户不存在")
            if payload.asset_id is None:
                user.avatar = None
                return user
            asset = await self.assets.get(payload.asset_id, for_update=True)
            if asset is None:
                raise AppException(status_code=404, code=ErrorCode.ASSET_NOT_FOUND, message="头像资产不存在")
            if (
                asset.uploader_type != UploaderType.USER.value
                or asset.uploader_id != user.id
                or asset.scene != UploadScene.AVATAR.value
                or not asset.url.startswith(self.settings.upload_base_url.rstrip("/") + "/")
            ):
                raise AppException(status_code=403, code=ErrorCode.PERMISSION_DENIED, message="无权使用该头像资产")
            user.avatar = asset.url
        return user

    async def change_password(
        self,
        *,
        user: User,
        login_session: UserSession,
        payload: PasswordChangeIn,
    ) -> SessionArtifacts:
        if not await self.password_manager.verify(payload.current_password, user.password_hash):
            raise AppException(
                status_code=401,
                code=ErrorCode.AUTH_INVALID_CREDENTIALS,
                message="当前密码错误",
            )
        new_hash = await self.password_manager.hash(payload.new_password)
        new_refresh = new_opaque_token()
        new_csrf = new_opaque_token()
        now = datetime.now(UTC)
        async with transaction_scope(self.session):
            locked = await self.users.get(user.id, for_update=True)
            current_session = await self.sessions.get_web(login_session.id, for_update=True)
            if locked is None or current_session is None or current_session.revoked_at is not None:
                raise AppException(
                    status_code=401,
                    code=ErrorCode.AUTH_SESSION_REVOKED,
                    message="身份认证会话已失效",
                )
            locked.password_hash = new_hash
            locked.credential_version += 1
            await self.sessions.revoke_web_for_user(locked.id, reason="password_changed", except_id=current_session.id)
            await self.sessions.revoke_web_refresh_tokens(current_session.id, reason="password_changed", now=now)
            idle = min(now + timedelta(days=self.settings.refresh_idle_ttl_days), current_session.absolute_expires_at)
            current_session.csrf_digest = token_digest(new_csrf, self.hmac_key)
            current_session.last_seen_at = now
            current_session.idle_expires_at = idle
            self.session.add(
                UserRefreshToken(
                    id=new_uuid7(),
                    session_id=current_session.id,
                    token_digest=token_digest(new_refresh, self.hmac_key),
                    issued_at=now,
                    expires_at=idle,
                    consumed_at=None,
                    revoked_at=None,
                    revoke_reason=None,
                    replaced_by_id=None,
                )
            )
            SecurityRepository(self.session).add_login_event(
                login_event(
                    principal_type="user",
                    principal_id=locked.id,
                    identifier_digest=None,
                    event_type="password_change",
                    succeeded=True,
                    reason_code="PASSWORD_CHANGED",
                    metadata=self.metadata,
                    now=now,
                )
            )
            credential_version = locked.credential_version
            absolute = current_session.absolute_expires_at
        access, access_expires = create_access_token(
            subject_id=user.id,
            session_id=login_session.id,
            credential_version=credential_version,
            audience="pinjie-web",
            issuer=self.settings.jwt_issuer,
            secret=self.jwt_secret,
            ttl_seconds=self.settings.web_access_ttl_seconds,
        )
        return SessionArtifacts(
            session_id=login_session.id,
            access_token=access,
            refresh_token=new_refresh,
            csrf_token=new_csrf,
            access_expires_at=access_expires,
            idle_expires_at=idle,
            absolute_expires_at=absolute,
        )

    async def revoke_session(self, *, user_id: uuid.UUID, session_id: uuid.UUID) -> bool:
        async with transaction_scope(self.session):
            target = await self.sessions.get_web_for_user(session_id, user_id)
            if target is None:
                raise AppException(status_code=404, code=ErrorCode.NOT_FOUND, message="会话不存在")
            return await self.sessions.revoke_web_session(session_id, reason="user_revoked")

    async def list_sessions(self, user_id: uuid.UUID, *, page: int, page_size: int) -> tuple[list[UserSession], int]:
        return await self.sessions.list_web(user_id, page=page, page_size=page_size)

    async def revoke_other_sessions(self, *, user_id: uuid.UUID, current_session_id: uuid.UUID) -> None:
        async with transaction_scope(self.session):
            await self.sessions.revoke_web_for_user(user_id, reason="user_revoked_others", except_id=current_session_id)

    async def delete_account(self, *, user: User, payload: AccountDeleteIn) -> None:
        if not await self.password_manager.verify(payload.current_password, user.password_hash):
            raise AppException(
                status_code=401,
                code=ErrorCode.AUTH_INVALID_CREDENTIALS,
                message="当前密码错误",
            )
        replacement_hash = await self.password_manager.hash(new_opaque_token())
        now = datetime.now(UTC)
        async with transaction_scope(self.session):
            locked = await self.users.get(user.id, for_update=True)
            if locked is None or locked.deleted_at is not None:
                raise AppException(status_code=404, code=ErrorCode.USER_NOT_FOUND, message="用户不存在")
            locked.password_hash = replacement_hash
            locked.is_active = False
            locked.credential_version += 1
            locked.deleted_at = now
            locked.deleted_by_id = locked.id
            locked.deleted_by_type = "user"
            locked.deletion_reason = None
            await self.sessions.revoke_web_for_user(locked.id, reason="account_deleted")


class AdminAccountService:
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
        self.session = session
        self.session_factory = session_factory
        self.redis = redis
        self.settings = settings
        self.password_manager = password_manager
        self.metadata = metadata
        self.admins = AdminRepository(session)
        self.sessions = SessionRepository(session)
        _, admin_secret, _, admin_hmac = settings.authentication_secrets()
        self.jwt_secret = admin_secret
        self.hmac_key = admin_hmac

    async def update_profile(
        self,
        *,
        admin: Admin,
        payload: AdminProfileUpdateIn,
    ) -> Admin:
        async with transaction_scope(self.session):
            locked = await self.admins.get(admin.id, for_update=True)
            if locked is None or not locked.is_active:
                raise AppException(status_code=404, code=ErrorCode.ADMIN_NOT_FOUND, message="管理员不存在或已停用")
            if "display_name" in payload.model_fields_set:
                locked.display_name = payload.display_name.strip() if payload.display_name else None
            if "avatar" in payload.model_fields_set:
                locked.avatar = await resolve_admin_avatar(
                    session=self.session, settings=self.settings, avatar=payload.avatar
                )
        return locked

    async def change_password(
        self,
        *,
        admin: Admin,
        login_session: AdminSession,
        payload: PasswordChangeIn,
    ) -> SessionArtifacts:
        if not await self.password_manager.verify(payload.current_password, admin.password_hash):
            raise AppException(
                status_code=401,
                code=ErrorCode.AUTH_INVALID_CREDENTIALS,
                message="当前密码错误",
            )
        new_hash = await self.password_manager.hash(payload.new_password)
        new_refresh = new_opaque_token()
        new_csrf = new_opaque_token()
        now = datetime.now(UTC)
        async with transaction_scope(self.session):
            locked = await self.admins.get(admin.id, for_update=True)
            current_session = await self.sessions.get_admin(login_session.id, for_update=True)
            if locked is None or current_session is None or current_session.revoked_at is not None:
                raise AppException(
                    status_code=401,
                    code=ErrorCode.AUTH_SESSION_REVOKED,
                    message="管理员会话已失效",
                )
            locked.password_hash = new_hash
            locked.credential_version += 1
            await self.sessions.revoke_admin_for_admin(
                locked.id, reason="password_changed", except_id=current_session.id
            )
            await self.sessions.revoke_admin_refresh_tokens(current_session.id, reason="password_changed", now=now)
            idle = min(now + timedelta(days=self.settings.refresh_idle_ttl_days), current_session.absolute_expires_at)
            current_session.csrf_digest = token_digest(new_csrf, self.hmac_key)
            current_session.last_seen_at = now
            current_session.idle_expires_at = idle
            self.session.add(
                AdminRefreshToken(
                    id=new_uuid7(),
                    session_id=current_session.id,
                    token_digest=token_digest(new_refresh, self.hmac_key),
                    issued_at=now,
                    expires_at=idle,
                    consumed_at=None,
                    revoked_at=None,
                    revoke_reason=None,
                    replaced_by_id=None,
                )
            )
            SecurityRepository(self.session).add_login_event(
                login_event(
                    principal_type="admin",
                    principal_id=locked.id,
                    identifier_digest=None,
                    event_type="password_change",
                    succeeded=True,
                    reason_code="PASSWORD_CHANGED",
                    metadata=self.metadata,
                    now=now,
                )
            )
            credential_version = locked.credential_version
            absolute = current_session.absolute_expires_at
        access, access_expires = create_access_token(
            subject_id=admin.id,
            session_id=login_session.id,
            credential_version=credential_version,
            audience="pinjie-admin",
            issuer=self.settings.jwt_issuer,
            secret=self.jwt_secret,
            ttl_seconds=self.settings.admin_access_ttl_seconds,
        )
        return SessionArtifacts(
            session_id=login_session.id,
            access_token=access,
            refresh_token=new_refresh,
            csrf_token=new_csrf,
            access_expires_at=access_expires,
            idle_expires_at=idle,
            absolute_expires_at=absolute,
        )

    async def create_confirmation_compatibility(
        self,
        *,
        admin: Admin,
        payload: AdminConfirmIn,
    ) -> AdminConfirmOut:
        # 设计说明：本方法为前端兼容性占位实现。
        # confirmation_token 仅用于客户端 UI 流程标识，服务端不持久化、不验证该 token。
        # 安全边界：本次操作仅验证当前密码（下方 verify），敏感操作的最终授权由
        # 各业务端点独立进行密码/权限校验，而非依赖此 token 作为二次确认凭据。
        # 若未来需要真正的服务端 token 确认机制，必须将 token 摘要与 action、
        # 过期时间一同持久化到数据库或 Redis，并在对应接口查库验证后再放行。
        if not await self.password_manager.verify(payload.current_password, admin.password_hash):
            raise AppException(
                status_code=401,
                code=ErrorCode.AUTH_INVALID_CREDENTIALS,
                message="当前密码错误",
            )
        return AdminConfirmOut(
            confirmation_token=new_opaque_token(),
            action=payload.action,
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )


__all__ = ["AdminAccountService", "UserAccountService"]
