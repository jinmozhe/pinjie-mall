from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid7

import pytest
from starlette.requests import Request
from starlette.responses import Response

from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.domains.auth.router import refresh as web_refresh
from app.services.admin_management import ManagementAuditCoordinator
from app.services.commerce_reporting import CommerceReportingService, SelectedCommerceIds


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/auth/refresh",
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 80),
            "client": ("127.0.0.1", 1234),
            "scheme": "http",
            "app": SimpleNamespace(state=SimpleNamespace(settings=SimpleNamespace())),
        }
    )


@pytest.mark.asyncio
async def test_refresh_lock_conflict_does_not_mark_cookies_for_deletion() -> None:
    service = SimpleNamespace(
        refresh=AsyncMock(
            side_effect=AppException(
                status_code=429,
                code=ErrorCode.RATE_LIMITED,
                message="会话刷新正在进行中",
            )
        )
    )
    request = _request()
    response = Response()

    with pytest.raises(AppException) as exc_info:
        await web_refresh(request, response, service, "csrf", "refresh")

    assert exc_info.value.code == ErrorCode.RATE_LIMITED
    assert getattr(request.state, "clear_auth_profile", None) is None
    assert "set-cookie" not in response.headers


@pytest.mark.asyncio
async def test_management_write_rechecks_revoked_actor_session() -> None:
    async def run_audit(**kwargs):
        return await kwargs["operation"]()

    audit = SimpleNamespace(execute=AsyncMock(side_effect=run_audit))
    coordinator = ManagementAuditCoordinator(
        audit=audit,
        session=SimpleNamespace(),
        actor_id=uuid7(),
        session_id=uuid7(),
    )
    coordinator._access = SimpleNamespace(
        get_admin_for_update=AsyncMock(return_value=SimpleNamespace(is_active=True, is_superuser=True, roles=[]))
    )
    coordinator._sessions = SimpleNamespace(
        get_admin=AsyncMock(return_value=SimpleNamespace(revoked_at=datetime.now(UTC)))
    )
    operation = AsyncMock()

    with pytest.raises(AppException) as exc_info:
        await coordinator.execute(
            action="users:credentials:reset",
            target_type="user",
            target_id=uuid7(),
            changed_fields={"password": "reset"},
            operation=operation,
        )

    assert exc_info.value.code == ErrorCode.PERMISSION_DENIED
    operation.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "actor_session",
    [
        None,
        SimpleNamespace(
            admin_id=uuid7(),
            revoked_at=None,
            idle_expires_at=datetime.now(UTC) + timedelta(hours=1),
            absolute_expires_at=datetime.now(UTC) + timedelta(hours=1),
        ),
        SimpleNamespace(
            admin_id=None,
            revoked_at=None,
            idle_expires_at=datetime.now(UTC) - timedelta(seconds=1),
            absolute_expires_at=datetime.now(UTC) + timedelta(hours=1),
        ),
        SimpleNamespace(
            admin_id=None,
            revoked_at=None,
            idle_expires_at=datetime.now(UTC) + timedelta(hours=1),
            absolute_expires_at=datetime.now(UTC) - timedelta(seconds=1),
        ),
    ],
)
async def test_management_write_rechecks_actor_session_validity(actor_session: SimpleNamespace | None) -> None:
    async def run_audit(**kwargs):
        return await kwargs["operation"]()

    actor_id = uuid7()
    if actor_session is not None and actor_session.admin_id is None:
        actor_session.admin_id = actor_id
    audit = SimpleNamespace(execute=AsyncMock(side_effect=run_audit))
    coordinator = ManagementAuditCoordinator(
        audit=audit,
        session=SimpleNamespace(),
        actor_id=actor_id,
        session_id=uuid7(),
    )
    coordinator._access = SimpleNamespace(
        get_admin_for_update=AsyncMock(return_value=SimpleNamespace(is_active=True, is_superuser=True, roles=[]))
    )
    coordinator._sessions = SimpleNamespace(get_admin=AsyncMock(return_value=actor_session))
    operation = AsyncMock()

    with pytest.raises(AppException, match="权限已失效"):
        await coordinator.execute(
            action="users:credentials:reset",
            target_type="user",
            target_id=uuid7(),
            changed_fields={"password": "reset"},
            operation=operation,
        )

    operation.assert_not_awaited()


@pytest.mark.asyncio
async def test_commerce_export_records_audit_scope_without_export_values() -> None:
    session = SimpleNamespace(scalars=AsyncMock(return_value=[]))

    async def run_audit(**kwargs):
        return await kwargs["operation"]()

    audit = SimpleNamespace(execute=AsyncMock(side_effect=run_audit))
    service = CommerceReportingService(session, audit)

    with pytest.raises(AppException) as exc_info:
        await service.export("orders", SelectedCommerceIds(ids=[uuid7()]))

    assert exc_info.value.code == ErrorCode.STATE_CONFLICT
    audit_input = audit.execute.await_args.kwargs
    assert audit_input["action"] == "commerce.orders.export"
    assert audit_input["changed_fields"]["record_count"] == 1
    assert "password" not in str(audit_input["changed_fields"])
