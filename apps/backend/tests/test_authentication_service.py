"""Admin authentication and security-event boundary regressions."""

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import Settings
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.core.identifiers import new_uuid7
from app.core.request_metadata import RequestMetadata
from app.core.security import new_opaque_token, token_digest
from app.domains.admin.schemas import AdminLoginIn
from app.services.authentication import AdminAuthService
from app.services.security_events import SecurityEventWriter, login_event
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


def _fake_admin(*, is_active: bool = True, credential_version: int = 1) -> MagicMock:
    admin = MagicMock()
    admin.id = new_uuid7()
    admin.username = "admin-user"
    admin.is_active = is_active
    admin.credential_version = credential_version
    admin.password_hash = "hashed"
    return admin


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
    svc = _admin_service()
    raw = new_opaque_token()
    key = svc.hmac_key
    good_digest = token_digest(raw, key)
    svc._verify_session_csrf(raw, good_digest, key)  # no exception

    with pytest.raises(AppException) as exc:
        svc._verify_session_csrf("wrong-token", good_digest, key)
    assert exc.value.code == ErrorCode.CSRF_REJECTED
    assert exc.value.status_code == 403


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_security_event_writer_fails_closed_on_storage_error() -> None:
    """安全事件无法写入时，应返回服务不可用并保留失败关闭语义。"""
    session = AsyncMock()
    session_context = AsyncMock()
    session_context.__aenter__.return_value = session
    session_factory = MagicMock(return_value=session_context)
    writer = SecurityEventWriter(session_factory)
    event = login_event(
        principal_type="user",
        principal_id=None,
        identifier_digest="a" * 64,
        event_type="login",
        succeeded=False,
        reason_code="INVALID_CREDENTIALS",
        metadata=_meta(),
    )

    with patch("app.services.security_events.SecurityRepository.add_login_event", side_effect=RuntimeError("db")):
        with pytest.raises(AppException) as exc:
            await writer.record_login(event)

    assert exc.value.code == ErrorCode.SERVICE_UNAVAILABLE
    assert exc.value.status_code == 503


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


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
