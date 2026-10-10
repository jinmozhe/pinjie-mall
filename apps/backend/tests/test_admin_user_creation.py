import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.config import Settings
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.domains.admin.schemas import AdminUserCreateIn
from app.services.admin_management import AdminManagementService


def _service() -> AdminManagementService:
    password_manager = SimpleNamespace(hash=AsyncMock(return_value="hashed-initial-password"))
    service = AdminManagementService(
        session=AsyncMock(),
        session_factory=AsyncMock(),
        settings=Settings.model_construct(environment="test", redis_mode="disabled"),
        password_manager=password_manager,
        metadata=AsyncMock(),
        actor_id=uuid.uuid7(),
    )
    service.users.get_by_username = AsyncMock(return_value=None)
    service.users.get_by_email = AsyncMock(return_value=None)
    service.users.add = MagicMock()

    async def execute(**kwargs):
        user = await kwargs["operation"]()
        now = datetime.now(UTC)
        user.created_at = now
        user.updated_at = now
        return user

    service.audit.execute = AsyncMock(side_effect=execute)
    return service


def test_admin_user_create_input_normalizes_optional_profile_fields() -> None:
    payload = AdminUserCreateIn(
        username="  New-User  ",
        initial_password="initial-password",
        display_name="   ",
        email="  USER@EXAMPLE.COM ",
    )

    assert payload.username == "new-user"
    assert payload.display_name is None
    assert payload.email == "user@example.com"
    assert payload.is_active is True


@pytest.mark.asyncio
async def test_admin_create_user_hashes_password_without_creating_session() -> None:
    service = _service()
    payload = AdminUserCreateIn(
        username="managed-user",
        initial_password="initial-password",
        display_name="Managed User",
        email="managed@example.com",
        is_active=False,
    )

    result = await service.create_user(payload)

    service.password_manager.hash.assert_awaited_once_with("initial-password")
    service.users.add.assert_called_once()
    created_user = service.users.add.call_args.args[0]
    assert created_user.password_hash == "hashed-initial-password"
    assert created_user.is_active is False
    service.audit.execute.assert_awaited_once()
    audit_input = service.audit.execute.await_args.kwargs
    assert audit_input["action"] == "users:create"
    assert audit_input["changed_fields"] == {
        "created": True,
        "is_active": False,
        "has_display_name": True,
        "has_email": True,
    }
    assert "password" not in str(audit_input["changed_fields"])
    assert "managed@example.com" not in str(audit_input["changed_fields"])
    assert result.username == "managed-user"


@pytest.mark.asyncio
async def test_admin_create_user_rejects_soft_deleted_identifier_conflict() -> None:
    service = _service()
    service.users.get_by_username.return_value = SimpleNamespace(deleted_at=datetime.now(UTC))

    with pytest.raises(AppException) as error:
        await service.create_user(AdminUserCreateIn(username="managed-user", initial_password="initial-password"))

    assert error.value.status_code == 409
    assert error.value.code == ErrorCode.STATE_CONFLICT
    service.users.add.assert_not_called()


@pytest.mark.asyncio
async def test_admin_create_user_requires_authentication(client) -> None:
    response = await client.post(
        "/api/v1/admin/users",
        headers={"Origin": "http://localhost:3001"},
        json={"username": "managed-user", "initial_password": "initial-password"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_browser_registration_capability_is_retired(client) -> None:
    response = await client.get("/api/v1/system/capabilities")
    assert response.status_code == 404
