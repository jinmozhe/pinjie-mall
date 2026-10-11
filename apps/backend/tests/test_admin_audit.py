from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid7

import pytest

from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.domains.admin.permissions import PermissionCode
from app.services.admin_audit import AdminAuditCoordinator
from app.services.security_events import AuditSuccess


def coordinator(*, permission: PermissionCode | None = None):
    actor_id = UUID(int=9)
    calls = []

    async def audit_operation(**kwargs):
        calls.append("transaction")
        return await kwargs["operation"]()

    async def lock_graph():
        calls.append("graph")

    async def role_admins(role_ids):
        calls.append(("roles", role_ids))
        return [UUID(int=3), actor_id]

    async def lock_admins(admin_ids, *, for_update):
        assert for_update
        calls.append(("admins", admin_ids))
        return []

    actor = SimpleNamespace(
        is_active=True,
        is_superuser=permission is None,
        roles=[SimpleNamespace(is_active=True, permissions=[SimpleNamespace(is_active=True, code=permission.value)])]
        if permission
        else [],
    )
    login = SimpleNamespace(
        admin_id=actor_id,
        revoked_at=None,
        idle_expires_at=datetime.now(UTC) + timedelta(hours=1),
        absolute_expires_at=datetime.now(UTC) + timedelta(days=1),
    )

    async def lock_actor(_actor_id):
        calls.append("actor")
        return actor

    async def lock_session(_session_id, *, for_update):
        assert for_update
        calls.append("session")
        return login

    audit = SimpleNamespace(execute=AsyncMock(side_effect=audit_operation))
    service = AdminAuditCoordinator(audit=audit, session=None, actor_id=actor_id, session_id=uuid7())
    service._admins = SimpleNamespace(
        lock_management_guard=AsyncMock(side_effect=lock_graph),
        admin_ids_for_roles=AsyncMock(side_effect=role_admins),
        get_many=AsyncMock(side_effect=lock_admins),
    )
    service._access = SimpleNamespace(get_admin_for_update=AsyncMock(side_effect=lock_actor))
    service._sessions = SimpleNamespace(get_admin=AsyncMock(side_effect=lock_session))
    return service, actor, login, calls, audit


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid",
    [
        "missing_id",
        "wrong_owner",
        "revoked",
        "idle",
        "absolute",
        "disabled",
        "permission",
        "role",
        "inactive_permission",
    ],
)
async def test_denial_prevents_business_side_effects(invalid):
    service, actor, login, _, audit = coordinator(permission=PermissionCode.POINTS_ADJUST)
    if invalid == "missing_id":
        service._session_id = None
    elif invalid == "wrong_owner":
        login.admin_id = uuid7()
    elif invalid == "revoked":
        login.revoked_at = datetime.now(UTC)
    elif invalid in {"idle", "absolute"}:
        setattr(login, f"{invalid}_expires_at", datetime.now(UTC) - timedelta(seconds=1))
    elif invalid == "disabled":
        actor.is_active = False
    elif invalid == "permission":
        actor.roles = []
    elif invalid == "role":
        actor.roles[0].is_active = False
    else:
        actor.roles[0].permissions[0].is_active = False
    operation = AsyncMock()
    with pytest.raises(AppException) as error:
        await service.execute(
            action="points.adjust", target_type="points", target_id=uuid7(), changed_fields={}, operation=operation
        )
    assert error.value.code == ErrorCode.PERMISSION_DENIED
    operation.assert_not_awaited()
    audit.execute.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("action", "create", "update"),
    [
        ("member-levels.write", PermissionCode.MEMBER_LEVELS_CREATE, PermissionCode.MEMBER_LEVELS_UPDATE),
        (
            "member-level-conditions.write",
            PermissionCode.MEMBER_LEVEL_CONDITIONS_CREATE,
            PermissionCode.MEMBER_LEVEL_CONDITIONS_UPDATE,
        ),
        (
            "member-price-rules.write",
            PermissionCode.MEMBER_PRICE_RULES_CREATE,
            PermissionCode.MEMBER_PRICE_RULES_UPDATE,
        ),
    ],
)
@pytest.mark.parametrize("is_create", [True, False])
async def test_membership_requires_exact_create_or_update_permission(action, create, update, is_create):
    service, actor, _, _, _ = coordinator(permission=update if is_create else create)
    operation = AsyncMock(return_value="saved")
    target_id = None if is_create else uuid7()
    with pytest.raises(AppException):
        await service.execute(
            action=action, target_type="member", target_id=target_id, changed_fields={}, operation=operation
        )
    operation.assert_not_awaited()
    actor.roles[0].permissions[0].code = (create if is_create else update).value
    assert (
        await service.execute(
            action=action, target_type="member", target_id=target_id, changed_fields={}, operation=operation
        )
        == "saved"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "action",
    [
        "admins:update",
        "admins:status:update",
        "admins:credentials:reset",
        "admins:roles:assign",
        "admins:sessions:revoke-all",
    ],
)
async def test_admin_targets_locked_before_actor_and_session(action):
    service, _, _, calls, _ = coordinator()
    service._admins.admin_ids_for_roles.return_value = []
    service._admins.admin_ids_for_roles.side_effect = None
    await service.execute(
        action=action, target_type="admin", target_id=UUID(int=1), changed_fields={}, operation=AsyncMock()
    )
    assert calls == ["transaction", "graph", ("admins", [UUID(int=1), UUID(int=9)]), "actor", "session"]


@pytest.mark.asyncio
@pytest.mark.parametrize("batch", [True, False])
async def test_role_changes_lock_all_affected_admins_before_role_operation(batch):
    service, _, _, calls, _ = coordinator()
    role_ids = [UUID(int=8), UUID(int=2)] if batch else [UUID(int=2)]
    await service.execute(
        action="roles:status:update-bulk" if batch else "roles:permissions:assign",
        target_type="role_batch" if batch else "role",
        target_id=None if batch else role_ids[0],
        role_ids=role_ids if batch else (),
        changed_fields={},
        operation=AsyncMock(),
    )
    assert calls == [
        "transaction",
        "graph",
        ("roles", sorted(role_ids)),
        ("admins", [UUID(int=3), UUID(int=9)]),
        "actor",
        "session",
    ]


@pytest.mark.asyncio
async def test_admin_batch_sorts_and_deduplicates_actor_with_targets():
    service, _, _, calls, _ = coordinator()
    service._admins.admin_ids_for_roles.side_effect = None
    service._admins.admin_ids_for_roles.return_value = []
    await service.execute(
        action="admins:status:update-bulk",
        target_type="admin_batch",
        target_id=None,
        admin_ids=[UUID(int=12), UUID(int=9), UUID(int=1)],
        changed_fields={},
        operation=AsyncMock(),
    )
    assert calls[2] == ("admins", [UUID(int=1), UUID(int=9), UUID(int=12)])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("action", "target_type"), [("admins:status:update-bulk", "admin_batch"), ("roles:delete-bulk", "role_batch")]
)
async def test_batch_without_explicit_targets_fails_closed(action, target_type):
    service, _, _, _, _ = coordinator()
    operation = AsyncMock()
    with pytest.raises(ValueError, match="explicit lock targets"):
        await service.execute(
            action=action, target_type=target_type, target_id=None, changed_fields={}, operation=operation
        )
    operation.assert_not_awaited()


@pytest.mark.asyncio
async def test_withdrawal_requires_exact_permission_and_preserves_audit_metadata():
    service, actor, _, calls, audit = coordinator(permission=PermissionCode.WITHDRAWALS_REVIEW)
    target_id = uuid7()

    def event(result):
        return AuditSuccess("withdrawal.state_changed", target_id, 4, {"to_status": result})

    operation = AsyncMock(return_value="succeeded")
    args = dict(
        action="withdrawal.state_changed",
        target_type="withdrawal_request",
        target_id=target_id,
        target_revision=4,
        changed_fields={"from_status": "approved"},
        operation=operation,
        permission=PermissionCode.WITHDRAWALS_COMPLETE_MANUAL,
        success_event=event,
    )
    with pytest.raises(AppException):
        await service.execute(**args)
    operation.assert_not_awaited()
    actor.roles[0].permissions[0].code = PermissionCode.WITHDRAWALS_COMPLETE_MANUAL.value
    assert await service.execute(**args) == "succeeded"
    assert "graph" not in calls
    assert audit.execute.await_args.kwargs["target_revision"] == 4
    assert audit.execute.await_args.kwargs["success_event"] is event


@pytest.mark.asyncio
async def test_unknown_action_does_not_default_to_a_general_permission():
    service, _, _, _, audit = coordinator()
    with pytest.raises(ValueError):
        await service.execute(
            action="unknown.write", target_type="unknown", target_id=None, changed_fields={}, operation=AsyncMock()
        )
    audit.execute.assert_not_awaited()
