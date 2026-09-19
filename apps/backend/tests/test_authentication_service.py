"""
authentication.py 服务层边界路径测试。

使用 Mock 隔离数据库和 Redis，专注覆盖高风险的认证流程边界：
  - CSRF 校验失败
  - 注册：注册关闭、邮箱冲突、并发 IntegrityError
  - Web 登录：账户禁用、锁定后二次检查失败、密码哈希升级
  - Web 刷新：并发锁冲突、Token 不存在、重放撤销 Session Family、
             已撤销、已过期、账户禁用
  - Web 登出：Token 不存在
  - Admin 登录：账户禁用、锁定后二次检查失败、密码哈希升级
  - Admin 刷新：并发锁冲突、Token 不存在、重放撤销 Session Family、
               已撤销、已过期、账户禁用
  - Admin 登出：Token 不存在
"""

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.core.identifiers import new_uuid7
from app.core.request_metadata import RequestMetadata
from app.core.security import new_opaque_token, token_digest
from app.domains.admin.schemas import AdminLoginIn
from app.domains.auth.schemas import UserLoginIn, UserRegisterIn
from app.services.authentication import AdminAuthService, WebAuthService
from tests.conftest import TEST_SECRETS

DATABASE_URL = "postgresql+asyncpg://u:p@localhost:5432/app"


def _settings(**extra: object) -> Settings:
    return Settings(ENVIRONMENT="local", DATABASE_URL=DATABASE_URL, **TEST_SECRETS, **extra)  # type: ignore[arg-type]


def _meta() -> RequestMetadata:
    return RequestMetadata(
        request_id=str(uuid.uuid7()),
        trace_id=str(uuid.uuid7()),
        ip_address="127.0.0.1",
        user_agent_summary="pytest",
        release_version="test",
    )


def _web_service(
    session: object = None,
    redis: object = None,
    password_manager: object = None,
) -> WebAuthService:
    return WebAuthService(
        session=session or MagicMock(),
        session_factory=MagicMock(),
        redis=redis,  # type: ignore[arg-type]
        settings=_settings(),
        password_manager=password_manager or MagicMock(),
        metadata=_meta(),
    )


def _admin_service(
    session: object = None,
    redis: object = None,
    password_manager: object = None,
) -> AdminAuthService:
    return AdminAuthService(
        session=session or MagicMock(),
        session_factory=MagicMock(),
        redis=redis,  # type: ignore[arg-type]
        settings=_settings(),
        password_manager=password_manager or MagicMock(),
        metadata=_meta(),
    )


def _fake_user(
    *,
    is_active: bool = True,
    deleted_at: datetime | None = None,
    credential_version: int = 1,
) -> MagicMock:
    user = MagicMock()
    user.id = new_uuid7()
    user.username = "browser-user"
    user.is_active = is_active
    user.deleted_at = deleted_at
    user.credential_version = credential_version
    user.password_hash = "hashed"
    return user


def _fake_admin(*, is_active: bool = True, credential_version: int = 1) -> MagicMock:
    admin = MagicMock()
    admin.id = new_uuid7()
    admin.username = "admin-user"
    admin.is_active = is_active
    admin.credential_version = credential_version
    admin.password_hash = "hashed"
    return admin


def _fake_web_session(
    *,
    now: datetime | None = None,
    consumed_at: datetime | None = None,
    revoked_at: datetime | None = None,
    token_revoked_at: datetime | None = None,
    absolute_expires_at: datetime | None = None,
    idle_expires_at: datetime | None = None,
    user_active: bool = True,
    user_deleted: bool = False,
) -> MagicMock:
    _now = now or datetime.now(UTC)
    token = MagicMock()
    token.consumed_at = consumed_at
    token.revoked_at = token_revoked_at
    token.expires_at = idle_expires_at or (_now + timedelta(days=7))
    user = _fake_user(is_active=user_active, deleted_at=_now if user_deleted else None)
    session = MagicMock()
    session.id = new_uuid7()
    session.user_id = user.id
    session.user = user
    session.revoked_at = revoked_at
    session.csrf_digest = "any"
    session.absolute_expires_at = absolute_expires_at or (_now + timedelta(days=30))
    session.idle_expires_at = idle_expires_at or (_now + timedelta(days=7))
    token.session = session
    token.session_id = session.id
    return token


def _fake_admin_session(
    *,
    now: datetime | None = None,
    consumed_at: datetime | None = None,
    revoked_at: datetime | None = None,
    token_revoked_at: datetime | None = None,
    absolute_expires_at: datetime | None = None,
    idle_expires_at: datetime | None = None,
    admin_active: bool = True,
) -> MagicMock:
    _now = now or datetime.now(UTC)
    token = MagicMock()
    token.consumed_at = consumed_at
    token.revoked_at = token_revoked_at
    token.expires_at = idle_expires_at or (_now + timedelta(days=7))
    admin = _fake_admin(is_active=admin_active)
    session = MagicMock()
    session.id = new_uuid7()
    session.admin_id = admin.id
    session.admin = admin
    session.revoked_at = revoked_at
    session.csrf_digest = "any"
    session.absolute_expires_at = absolute_expires_at or (_now + timedelta(days=30))
    session.idle_expires_at = idle_expires_at or (_now + timedelta(days=7))
    token.session = session
    token.session_id = session.id
    return token


# ---------------------------------------------------------------------------
# _AuthBase._verify_session_csrf
# ---------------------------------------------------------------------------


def test_verify_session_csrf_raises_on_mismatch() -> None:
    svc = _web_service()
    raw = new_opaque_token()
    key = svc.hmac_key
    good_digest = token_digest(raw, key)
    svc._verify_session_csrf(raw, good_digest, key)  # no exception

    with pytest.raises(AppException) as exc:
        svc._verify_session_csrf("wrong-token", good_digest, key)
    assert exc.value.code == ErrorCode.CSRF_REJECTED
    assert exc.value.status_code == 403


# ---------------------------------------------------------------------------
# WebAuthService.register -- edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_web_register_raises_when_registration_setting_unavailable() -> None:
    """注册设置读取出现 SQLAlchemyError 时应返回 503。"""
    from sqlalchemy.exc import SQLAlchemyError

    with (
        patch("app.services.authentication.enforce_rate_limit", new=AsyncMock()),
        patch("app.services.authentication.SystemSettingRepository") as mock_repo,
        patch("app.services.authentication.transaction_scope") as mock_txn,
    ):
        mock_txn.return_value.__aenter__ = AsyncMock()
        mock_txn.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_repo.return_value.get = AsyncMock(side_effect=SQLAlchemyError("db error"))

        pm = MagicMock()
        pm.hash = AsyncMock(return_value="hashed")
        svc = _web_service(password_manager=pm)
        with pytest.raises(AppException) as exc:
            await svc.register(UserRegisterIn(username="newuser", password="password-12345678", display_name=None))
        assert exc.value.status_code == 503
        assert exc.value.code == ErrorCode.SERVICE_UNAVAILABLE


@pytest.mark.asyncio
async def test_web_register_raises_when_registration_closed() -> None:
    """注册功能关闭时应返回 403 REGISTRATION_CLOSED。"""
    with (
        patch("app.services.authentication.enforce_rate_limit", new=AsyncMock()),
        patch("app.services.authentication.SystemSettingRepository") as mock_repo,
        patch("app.services.authentication.transaction_scope") as mock_txn,
    ):
        mock_txn.return_value.__aenter__ = AsyncMock()
        mock_txn.return_value.__aexit__ = AsyncMock(return_value=False)
        reg_obj = MagicMock()
        reg_obj.setting_value = {"enabled": False}
        mock_repo.return_value.get = AsyncMock(return_value=reg_obj)

        pm = MagicMock()
        pm.hash = AsyncMock(return_value="hashed")
        svc = _web_service(password_manager=pm)
        with pytest.raises(AppException) as exc:
            await svc.register(UserRegisterIn(username="newuser", password="password-12345678", display_name=None))
        assert exc.value.code == ErrorCode.REGISTRATION_CLOSED
        assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_web_register_raises_on_email_conflict() -> None:
    """邮箱已被占用时应返回 409 STATE_CONFLICT。"""
    with (
        patch("app.services.authentication.enforce_rate_limit", new=AsyncMock()),
        patch("app.services.authentication.SystemSettingRepository") as mock_repo,
        patch("app.services.authentication.transaction_scope") as mock_txn,
    ):
        mock_txn.return_value.__aenter__ = AsyncMock()
        mock_txn.return_value.__aexit__ = AsyncMock(return_value=False)
        reg_obj = MagicMock()
        reg_obj.setting_value = {"enabled": True}
        mock_repo.return_value.get = AsyncMock(return_value=reg_obj)

        pm = MagicMock()
        pm.hash = AsyncMock(return_value="hashed")
        svc = _web_service(password_manager=pm)
        svc.users.get_by_username = AsyncMock(return_value=None)
        svc.users.get_by_email = AsyncMock(return_value=MagicMock())

        with pytest.raises(AppException) as exc:
            await svc.register(
                UserRegisterIn(
                    username="newuser",
                    email="taken@example.com",
                    password="password-12345678",
                    display_name=None,
                )
            )
        assert exc.value.code == ErrorCode.STATE_CONFLICT
        assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_web_register_maps_integrity_error_to_409() -> None:
    """并发注册导致 IntegrityError 时应映射为 409 USER_USERNAME_CONFLICT。"""
    with (
        patch("app.services.authentication.enforce_rate_limit", new=AsyncMock()),
        patch("app.services.authentication.SystemSettingRepository") as mock_repo,
        patch("app.services.authentication.transaction_scope") as mock_txn,
    ):
        mock_txn.return_value.__aenter__ = AsyncMock()
        mock_txn.return_value.__aexit__ = AsyncMock(side_effect=IntegrityError("unique", {}, None))

        reg_obj = MagicMock()
        reg_obj.setting_value = {"enabled": True}
        mock_repo.return_value.get = AsyncMock(return_value=reg_obj)

        pm = MagicMock()
        pm.hash = AsyncMock(return_value="hashed")
        svc = _web_service(password_manager=pm)
        svc.users.get_by_username = AsyncMock(return_value=None)
        svc.users.get_by_email = AsyncMock(return_value=None)
        svc.users.add = MagicMock()
        svc.sessions.add_web = MagicMock()

        with pytest.raises(AppException) as exc:
            await svc.register(UserRegisterIn(username="newuser", password="password-12345678", display_name=None))
        assert exc.value.code == ErrorCode.USER_USERNAME_CONFLICT
        assert exc.value.status_code == 409


# ---------------------------------------------------------------------------
# WebAuthService.login -- edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_web_login_raises_when_account_disabled() -> None:
    """is_active=False 的用户登录应返回 403 AUTH_ACCOUNT_DISABLED。"""
    user = _fake_user(is_active=False)
    pm = MagicMock()
    pm.verify_and_update = AsyncMock(return_value=(True, None))
    svc = _web_service(password_manager=pm)
    svc.users.get_by_username = AsyncMock(return_value=user)

    with (
        patch("app.services.authentication.enforce_rate_limit", new=AsyncMock()),
        patch.object(svc.event_writer, "record_login", new=AsyncMock()),
    ):
        with pytest.raises(AppException) as exc:
            await svc.login(UserLoginIn(username="browser-user", password="password"))
        assert exc.value.code == ErrorCode.AUTH_ACCOUNT_DISABLED
        assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_web_login_raises_when_account_soft_deleted() -> None:
    """deleted_at 非空的用户登录应返回 403 AUTH_ACCOUNT_DISABLED。"""
    user = _fake_user(deleted_at=datetime.now(UTC))
    pm = MagicMock()
    pm.verify_and_update = AsyncMock(return_value=(True, None))
    svc = _web_service(password_manager=pm)
    svc.users.get_by_username = AsyncMock(return_value=user)

    with (
        patch("app.services.authentication.enforce_rate_limit", new=AsyncMock()),
        patch.object(svc.event_writer, "record_login", new=AsyncMock()),
    ):
        with pytest.raises(AppException) as exc:
            await svc.login(UserLoginIn(username="browser-user", password="password"))
        assert exc.value.code == ErrorCode.AUTH_ACCOUNT_DISABLED


@pytest.mark.asyncio
async def test_web_login_raises_when_locked_user_becomes_disabled_before_commit() -> None:
    """获取锁后用户被禁用（locked 返回 None）应返回 403。"""
    user = _fake_user(is_active=True)
    pm = MagicMock()
    pm.verify_and_update = AsyncMock(return_value=(True, None))
    svc = _web_service(password_manager=pm)
    svc.users.get_by_username = AsyncMock(return_value=user)
    svc.users.get = AsyncMock(return_value=None)

    with (
        patch("app.services.authentication.enforce_rate_limit", new=AsyncMock()),
        patch("app.services.authentication.transaction_scope") as mock_txn,
        patch.object(svc.event_writer, "record_login", new=AsyncMock()),
    ):
        mock_txn.return_value.__aenter__ = AsyncMock()
        mock_txn.return_value.__aexit__ = AsyncMock(return_value=False)

        with pytest.raises(AppException) as exc:
            await svc.login(UserLoginIn(username="browser-user", password="password"))
        assert exc.value.code == ErrorCode.AUTH_ACCOUNT_DISABLED


@pytest.mark.asyncio
async def test_web_login_updates_password_hash_when_rehash_needed() -> None:
    """verify_and_update 返回新 hash 时应写入 locked.password_hash。"""
    user = _fake_user()
    locked = _fake_user()
    locked.is_active = True
    locked.deleted_at = None
    new_hash = "upgraded-hash"
    pm = MagicMock()
    pm.verify_and_update = AsyncMock(return_value=(True, new_hash))
    svc = _web_service(password_manager=pm)
    svc.users.get_by_username = AsyncMock(return_value=user)
    svc.users.get = AsyncMock(return_value=locked)
    svc.sessions.add_web = MagicMock()

    with (
        patch("app.services.authentication.enforce_rate_limit", new=AsyncMock()),
        patch("app.services.authentication.transaction_scope") as mock_txn,
        patch("app.services.authentication.SecurityRepository"),
        patch.object(svc, "clear_login_limit", new=AsyncMock()),
    ):
        mock_txn.return_value.__aenter__ = AsyncMock()
        mock_txn.return_value.__aexit__ = AsyncMock(return_value=False)

        await svc.login(UserLoginIn(username="browser-user", password="password"))
        assert locked.password_hash == new_hash


@pytest.mark.asyncio
async def test_web_login_rejects_password_changed_after_verification() -> None:
    user = _fake_user(credential_version=1)
    locked = _fake_user(credential_version=2)
    locked.id = user.id
    locked.password_hash = "newer-password-hash"
    pm = MagicMock()
    pm.verify_and_update = AsyncMock(return_value=(True, None))
    svc = _web_service(password_manager=pm)
    svc.users.get_by_username = AsyncMock(return_value=user)
    svc.users.get = AsyncMock(return_value=locked)
    svc.sessions.add_web = MagicMock()

    with (
        patch("app.services.authentication.enforce_rate_limit", new=AsyncMock()),
        patch("app.services.authentication.transaction_scope") as mock_txn,
    ):
        mock_txn.return_value.__aenter__ = AsyncMock()
        mock_txn.return_value.__aexit__ = AsyncMock(return_value=False)

        with pytest.raises(AppException) as exc_info:
            await svc.login(UserLoginIn(username="browser-user", password="password"))

    assert exc_info.value.code == ErrorCode.AUTH_INVALID_CREDENTIALS
    svc.sessions.add_web.assert_not_called()


# ---------------------------------------------------------------------------
# WebAuthService.refresh -- edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_web_refresh_raises_429_when_lock_is_held() -> None:
    """已有并发刷新持有锁时应返回 429 RATE_LIMITED。"""
    lock = SimpleNamespace(set=AsyncMock(return_value=None))
    svc = _web_service(redis=lock)  # type: ignore[arg-type]
    with pytest.raises(AppException) as exc:
        await svc.refresh("refresh-token", "csrf-token")
    assert exc.value.status_code == 429
    assert exc.value.code == ErrorCode.RATE_LIMITED


@pytest.mark.asyncio
async def test_web_refresh_raises_when_token_not_found() -> None:
    """数据库中不存在 Refresh Token 时应返回 401 AUTH_TOKEN_INVALID。"""
    lock = SimpleNamespace(set=AsyncMock(return_value="OK"), eval=AsyncMock(return_value=1))
    svc = _web_service(redis=lock)  # type: ignore[arg-type]

    with patch("app.services.authentication.transaction_scope") as mock_txn:
        mock_txn.return_value.__aenter__ = AsyncMock()
        mock_txn.return_value.__aexit__ = AsyncMock(return_value=False)
        svc.sessions.get_web_refresh_for_update = AsyncMock(return_value=None)

        with pytest.raises(AppException) as exc:
            await svc.refresh("refresh-token", "csrf-token")
        assert exc.value.code == ErrorCode.AUTH_TOKEN_INVALID
        assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_web_refresh_raises_and_revokes_session_on_token_reuse() -> None:
    """已消费 Token 再次使用时应撤销会话并返回 401 AUTH_REFRESH_REUSE_DETECTED。"""
    now = datetime.now(UTC)
    fake_token = _fake_web_session(now=now, consumed_at=now - timedelta(minutes=1))
    lock = SimpleNamespace(set=AsyncMock(return_value="OK"), eval=AsyncMock(return_value=1))
    svc = _web_service(redis=lock)  # type: ignore[arg-type]

    with (
        patch("app.services.authentication.transaction_scope") as mock_txn,
        patch("app.services.authentication.SecurityRepository"),
    ):
        mock_txn.return_value.__aenter__ = AsyncMock()
        mock_txn.return_value.__aexit__ = AsyncMock(return_value=False)
        svc.sessions.get_web_refresh_for_update = AsyncMock(return_value=fake_token)

        with pytest.raises(AppException) as exc:
            await svc.refresh("refresh-token", "csrf-token")
        assert exc.value.code == ErrorCode.AUTH_REFRESH_REUSE_DETECTED
        assert fake_token.session.revoke_reason == "refresh_reuse"


@pytest.mark.asyncio
async def test_web_refresh_raises_when_token_revoked() -> None:
    """Refresh Token 本身已撤销时应返回 401 AUTH_SESSION_REVOKED。"""
    now = datetime.now(UTC)
    fake_token = _fake_web_session(now=now, consumed_at=None, token_revoked_at=now - timedelta(minutes=5))
    settings = _settings()
    _, _, web_hmac, _ = settings.authentication_secrets()
    csrf_raw = new_opaque_token()
    fake_token.session.csrf_digest = token_digest(csrf_raw, web_hmac)

    lock = SimpleNamespace(set=AsyncMock(return_value="OK"), eval=AsyncMock(return_value=1))
    svc = _web_service(redis=lock)  # type: ignore[arg-type]

    with patch("app.services.authentication.transaction_scope") as mock_txn:
        mock_txn.return_value.__aenter__ = AsyncMock()
        mock_txn.return_value.__aexit__ = AsyncMock(return_value=False)
        svc.sessions.get_web_refresh_for_update = AsyncMock(return_value=fake_token)

        with pytest.raises(AppException) as exc:
            await svc.refresh(new_opaque_token(), csrf_raw)
        assert exc.value.code == ErrorCode.AUTH_SESSION_REVOKED


@pytest.mark.asyncio
async def test_web_refresh_raises_when_session_revoked() -> None:
    """Session 被撤销时应返回 401 AUTH_SESSION_REVOKED。"""
    now = datetime.now(UTC)
    fake_token = _fake_web_session(now=now, consumed_at=None, revoked_at=now - timedelta(minutes=1))
    settings = _settings()
    _, _, web_hmac, _ = settings.authentication_secrets()
    csrf_raw = new_opaque_token()
    fake_token.session.csrf_digest = token_digest(csrf_raw, web_hmac)

    lock = SimpleNamespace(set=AsyncMock(return_value="OK"), eval=AsyncMock(return_value=1))
    svc = _web_service(redis=lock)  # type: ignore[arg-type]

    with patch("app.services.authentication.transaction_scope") as mock_txn:
        mock_txn.return_value.__aenter__ = AsyncMock()
        mock_txn.return_value.__aexit__ = AsyncMock(return_value=False)
        svc.sessions.get_web_refresh_for_update = AsyncMock(return_value=fake_token)

        with pytest.raises(AppException) as exc:
            await svc.refresh(new_opaque_token(), csrf_raw)
        assert exc.value.code == ErrorCode.AUTH_SESSION_REVOKED


@pytest.mark.asyncio
async def test_web_refresh_raises_when_token_expired() -> None:
    """Token expires_at 已过期应撤销会话并返回 401 AUTH_SESSION_EXPIRED。"""
    past = datetime.now(UTC) - timedelta(days=1)
    now = datetime.now(UTC)
    fake_token = _fake_web_session(now=now, consumed_at=None, idle_expires_at=past)
    settings = _settings()
    _, _, web_hmac, _ = settings.authentication_secrets()
    csrf_raw = new_opaque_token()
    fake_token.session.csrf_digest = token_digest(csrf_raw, web_hmac)

    lock = SimpleNamespace(set=AsyncMock(return_value="OK"), eval=AsyncMock(return_value=1))
    svc = _web_service(redis=lock)  # type: ignore[arg-type]

    with (
        patch("app.services.authentication.transaction_scope") as mock_txn,
        patch("app.services.authentication.SecurityRepository"),
    ):
        mock_txn.return_value.__aenter__ = AsyncMock()
        mock_txn.return_value.__aexit__ = AsyncMock(return_value=False)
        svc.sessions.get_web_refresh_for_update = AsyncMock(return_value=fake_token)

        with pytest.raises(AppException) as exc:
            await svc.refresh(new_opaque_token(), csrf_raw)
        assert exc.value.code == ErrorCode.AUTH_SESSION_EXPIRED
        assert fake_token.session.revoke_reason == "expired"


@pytest.mark.asyncio
async def test_web_refresh_raises_when_user_disabled_at_refresh_time() -> None:
    """刷新时用户 is_active=False 应返回 403 AUTH_ACCOUNT_DISABLED。"""
    now = datetime.now(UTC)
    fake_token = _fake_web_session(now=now, consumed_at=None, user_active=False)
    settings = _settings()
    _, _, web_hmac, _ = settings.authentication_secrets()
    csrf_raw = new_opaque_token()
    fake_token.session.csrf_digest = token_digest(csrf_raw, web_hmac)

    lock = SimpleNamespace(set=AsyncMock(return_value="OK"), eval=AsyncMock(return_value=1))
    svc = _web_service(redis=lock)  # type: ignore[arg-type]

    with patch("app.services.authentication.transaction_scope") as mock_txn:
        mock_txn.return_value.__aenter__ = AsyncMock()
        mock_txn.return_value.__aexit__ = AsyncMock(return_value=False)
        svc.sessions.get_web_refresh_for_update = AsyncMock(return_value=fake_token)

        with pytest.raises(AppException) as exc:
            await svc.refresh(new_opaque_token(), csrf_raw)
        assert exc.value.code == ErrorCode.AUTH_ACCOUNT_DISABLED
        assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_web_refresh_raises_when_user_soft_deleted_at_refresh_time() -> None:
    """刷新时用户 deleted_at 非空应返回 403 AUTH_ACCOUNT_DISABLED。"""
    now = datetime.now(UTC)
    fake_token = _fake_web_session(now=now, consumed_at=None, user_deleted=True)
    settings = _settings()
    _, _, web_hmac, _ = settings.authentication_secrets()
    csrf_raw = new_opaque_token()
    fake_token.session.csrf_digest = token_digest(csrf_raw, web_hmac)

    lock = SimpleNamespace(set=AsyncMock(return_value="OK"), eval=AsyncMock(return_value=1))
    svc = _web_service(redis=lock)  # type: ignore[arg-type]

    with patch("app.services.authentication.transaction_scope") as mock_txn:
        mock_txn.return_value.__aenter__ = AsyncMock()
        mock_txn.return_value.__aexit__ = AsyncMock(return_value=False)
        svc.sessions.get_web_refresh_for_update = AsyncMock(return_value=fake_token)

        with pytest.raises(AppException) as exc:
            await svc.refresh(new_opaque_token(), csrf_raw)
        assert exc.value.code == ErrorCode.AUTH_ACCOUNT_DISABLED


# ---------------------------------------------------------------------------
# WebAuthService.logout -- edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_web_logout_raises_when_token_not_found() -> None:
    """登出时 Refresh Token 不存在应返回 401 AUTH_TOKEN_INVALID。"""
    svc = _web_service()
    with patch("app.services.authentication.transaction_scope") as mock_txn:
        mock_txn.return_value.__aenter__ = AsyncMock()
        mock_txn.return_value.__aexit__ = AsyncMock(return_value=False)
        svc.sessions.get_web_refresh_for_update = AsyncMock(return_value=None)

        with pytest.raises(AppException) as exc:
            await svc.logout("bad-token", "csrf")
        assert exc.value.code == ErrorCode.AUTH_TOKEN_INVALID


# ---------------------------------------------------------------------------
# AdminAuthService.login -- edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_login_raises_when_account_disabled() -> None:
    """is_active=False 的管理员登录应返回 403 AUTH_ACCOUNT_DISABLED。"""
    admin = _fake_admin(is_active=False)
    pm = MagicMock()
    pm.verify_and_update = AsyncMock(return_value=(True, None))
    svc = _admin_service(password_manager=pm)
    svc.admins.get_by_username = AsyncMock(return_value=admin)

    with (
        patch("app.services.authentication.enforce_rate_limit", new=AsyncMock()),
        patch.object(svc.event_writer, "record_login", new=AsyncMock()),
    ):
        with pytest.raises(AppException) as exc:
            await svc.login(AdminLoginIn(username="admin-user", password="password"))
        assert exc.value.code == ErrorCode.AUTH_ACCOUNT_DISABLED
        assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_admin_login_raises_when_locked_admin_becomes_disabled_before_commit() -> None:
    """获取锁后管理员被禁用应返回 403。"""
    admin = _fake_admin(is_active=True)
    locked = _fake_admin(is_active=False)
    pm = MagicMock()
    pm.verify_and_update = AsyncMock(return_value=(True, None))
    svc = _admin_service(password_manager=pm)
    svc.admins.get_by_username = AsyncMock(return_value=admin)
    svc.admins.get = AsyncMock(return_value=locked)

    with (
        patch("app.services.authentication.enforce_rate_limit", new=AsyncMock()),
        patch("app.services.authentication.transaction_scope") as mock_txn,
    ):
        mock_txn.return_value.__aenter__ = AsyncMock()
        mock_txn.return_value.__aexit__ = AsyncMock(return_value=False)

        with pytest.raises(AppException) as exc:
            await svc.login(AdminLoginIn(username="admin-user", password="password"))
        assert exc.value.code == ErrorCode.AUTH_ACCOUNT_DISABLED


@pytest.mark.asyncio
async def test_admin_login_updates_password_hash_when_rehash_needed() -> None:
    """verify_and_update 返回新 hash 时应写入 locked.password_hash。"""
    admin = _fake_admin()
    locked = _fake_admin(is_active=True)
    new_hash = "upgraded-admin-hash"
    pm = MagicMock()
    pm.verify_and_update = AsyncMock(return_value=(True, new_hash))
    svc = _admin_service(password_manager=pm)
    svc.admins.get_by_username = AsyncMock(return_value=admin)
    svc.admins.get = AsyncMock(return_value=locked)
    svc.sessions.add_admin = MagicMock()

    with (
        patch("app.services.authentication.enforce_rate_limit", new=AsyncMock()),
        patch("app.services.authentication.transaction_scope") as mock_txn,
        patch("app.services.authentication.SecurityRepository"),
        patch.object(svc, "clear_login_limit", new=AsyncMock()),
    ):
        mock_txn.return_value.__aenter__ = AsyncMock()
        mock_txn.return_value.__aexit__ = AsyncMock(return_value=False)

        await svc.login(AdminLoginIn(username="admin-user", password="password"))
        assert locked.password_hash == new_hash


@pytest.mark.asyncio
async def test_admin_login_rejects_password_changed_after_verification() -> None:
    admin = _fake_admin(credential_version=1)
    locked = _fake_admin(credential_version=2)
    locked.id = admin.id
    locked.password_hash = "newer-password-hash"
    pm = MagicMock()
    pm.verify_and_update = AsyncMock(return_value=(True, None))
    svc = _admin_service(password_manager=pm)
    svc.admins.get_by_username = AsyncMock(return_value=admin)
    svc.admins.get = AsyncMock(return_value=locked)
    svc.sessions.add_admin = MagicMock()

    with (
        patch("app.services.authentication.enforce_rate_limit", new=AsyncMock()),
        patch("app.services.authentication.transaction_scope") as mock_txn,
    ):
        mock_txn.return_value.__aenter__ = AsyncMock()
        mock_txn.return_value.__aexit__ = AsyncMock(return_value=False)

        with pytest.raises(AppException) as exc_info:
            await svc.login(AdminLoginIn(username="admin-user", password="password"))

    assert exc_info.value.code == ErrorCode.AUTH_INVALID_CREDENTIALS
    svc.sessions.add_admin.assert_not_called()


# ---------------------------------------------------------------------------
# AdminAuthService.refresh -- edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_refresh_raises_429_when_lock_is_held() -> None:
    lock = SimpleNamespace(set=AsyncMock(return_value=None))
    svc = _admin_service(redis=lock)  # type: ignore[arg-type]
    with pytest.raises(AppException) as exc:
        await svc.refresh("refresh-token", "csrf-token")
    assert exc.value.status_code == 429
    assert exc.value.code == ErrorCode.RATE_LIMITED


@pytest.mark.asyncio
async def test_admin_refresh_raises_when_token_not_found() -> None:
    lock = SimpleNamespace(set=AsyncMock(return_value="OK"), eval=AsyncMock(return_value=1))
    svc = _admin_service(redis=lock)  # type: ignore[arg-type]

    with patch("app.services.authentication.transaction_scope") as mock_txn:
        mock_txn.return_value.__aenter__ = AsyncMock()
        mock_txn.return_value.__aexit__ = AsyncMock(return_value=False)
        svc.sessions.get_admin_refresh_for_update = AsyncMock(return_value=None)

        with pytest.raises(AppException) as exc:
            await svc.refresh("refresh-token", "csrf-token")
        assert exc.value.code == ErrorCode.AUTH_TOKEN_INVALID


@pytest.mark.asyncio
async def test_admin_refresh_raises_and_revokes_session_on_token_reuse() -> None:
    now = datetime.now(UTC)
    fake_token = _fake_admin_session(now=now, consumed_at=now - timedelta(minutes=1))
    lock = SimpleNamespace(set=AsyncMock(return_value="OK"), eval=AsyncMock(return_value=1))
    svc = _admin_service(redis=lock)  # type: ignore[arg-type]

    with (
        patch("app.services.authentication.transaction_scope") as mock_txn,
        patch("app.services.authentication.SecurityRepository"),
    ):
        mock_txn.return_value.__aenter__ = AsyncMock()
        mock_txn.return_value.__aexit__ = AsyncMock(return_value=False)
        svc.sessions.get_admin_refresh_for_update = AsyncMock(return_value=fake_token)

        with pytest.raises(AppException) as exc:
            await svc.refresh("refresh-token", "csrf-token")
        assert exc.value.code == ErrorCode.AUTH_REFRESH_REUSE_DETECTED
        assert fake_token.session.revoke_reason == "refresh_reuse"


@pytest.mark.asyncio
async def test_admin_refresh_raises_when_token_revoked() -> None:
    now = datetime.now(UTC)
    fake_token = _fake_admin_session(now=now, consumed_at=None, token_revoked_at=now - timedelta(minutes=5))
    settings = _settings()
    _, _, _, admin_hmac = settings.authentication_secrets()
    csrf_raw = new_opaque_token()
    fake_token.session.csrf_digest = token_digest(csrf_raw, admin_hmac)

    lock = SimpleNamespace(set=AsyncMock(return_value="OK"), eval=AsyncMock(return_value=1))
    svc = _admin_service(redis=lock)  # type: ignore[arg-type]

    with patch("app.services.authentication.transaction_scope") as mock_txn:
        mock_txn.return_value.__aenter__ = AsyncMock()
        mock_txn.return_value.__aexit__ = AsyncMock(return_value=False)
        svc.sessions.get_admin_refresh_for_update = AsyncMock(return_value=fake_token)

        with pytest.raises(AppException) as exc:
            await svc.refresh(new_opaque_token(), csrf_raw)
        assert exc.value.code == ErrorCode.AUTH_SESSION_REVOKED


@pytest.mark.asyncio
async def test_admin_refresh_raises_when_expired() -> None:
    past = datetime.now(UTC) - timedelta(days=1)
    now = datetime.now(UTC)
    fake_token = _fake_admin_session(now=now, consumed_at=None, idle_expires_at=past)
    settings = _settings()
    _, _, _, admin_hmac = settings.authentication_secrets()
    csrf_raw = new_opaque_token()
    fake_token.session.csrf_digest = token_digest(csrf_raw, admin_hmac)

    lock = SimpleNamespace(set=AsyncMock(return_value="OK"), eval=AsyncMock(return_value=1))
    svc = _admin_service(redis=lock)  # type: ignore[arg-type]

    with (
        patch("app.services.authentication.transaction_scope") as mock_txn,
        patch("app.services.authentication.SecurityRepository"),
    ):
        mock_txn.return_value.__aenter__ = AsyncMock()
        mock_txn.return_value.__aexit__ = AsyncMock(return_value=False)
        svc.sessions.get_admin_refresh_for_update = AsyncMock(return_value=fake_token)

        with pytest.raises(AppException) as exc:
            await svc.refresh(new_opaque_token(), csrf_raw)
        assert exc.value.code == ErrorCode.AUTH_SESSION_EXPIRED
        assert fake_token.session.revoke_reason == "expired"


@pytest.mark.asyncio
async def test_admin_refresh_raises_when_admin_disabled_at_refresh_time() -> None:
    now = datetime.now(UTC)
    fake_token = _fake_admin_session(now=now, consumed_at=None, admin_active=False)
    settings = _settings()
    _, _, _, admin_hmac = settings.authentication_secrets()
    csrf_raw = new_opaque_token()
    fake_token.session.csrf_digest = token_digest(csrf_raw, admin_hmac)

    lock = SimpleNamespace(set=AsyncMock(return_value="OK"), eval=AsyncMock(return_value=1))
    svc = _admin_service(redis=lock)  # type: ignore[arg-type]

    with patch("app.services.authentication.transaction_scope") as mock_txn:
        mock_txn.return_value.__aenter__ = AsyncMock()
        mock_txn.return_value.__aexit__ = AsyncMock(return_value=False)
        svc.sessions.get_admin_refresh_for_update = AsyncMock(return_value=fake_token)

        with pytest.raises(AppException) as exc:
            await svc.refresh(new_opaque_token(), csrf_raw)
        assert exc.value.code == ErrorCode.AUTH_ACCOUNT_DISABLED
        assert exc.value.status_code == 403


# ---------------------------------------------------------------------------
# AdminAuthService.logout -- edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_logout_raises_when_token_not_found() -> None:
    svc = _admin_service()
    with patch("app.services.authentication.transaction_scope") as mock_txn:
        mock_txn.return_value.__aenter__ = AsyncMock()
        mock_txn.return_value.__aexit__ = AsyncMock(return_value=False)
        svc.sessions.get_admin_refresh_for_update = AsyncMock(return_value=None)

        with pytest.raises(AppException) as exc:
            await svc.logout("bad-token", "csrf")
        assert exc.value.code == ErrorCode.AUTH_TOKEN_INVALID
