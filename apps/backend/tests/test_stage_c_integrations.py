import asyncio
import os
import uuid
from argparse import Namespace
from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from urllib.parse import urlsplit

import pytest
from pydantic import ValidationError
from redis.exceptions import ResponseError
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache_keys import cache_keys
from app.core.config import Settings
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.core.identifiers import new_uuid7
from app.core.rate_limit import enforce_rate_limit
from app.core.request_metadata import RequestMetadata
from app.core.resources import create_resources
from app.db.models import (
    Admin,
    AdminRefreshToken,
    AdminSession,
    Asset,
    AuditEvent,
    Permission,
    RequestLog,
    Role,
    SecurityLoginEvent,
    User,
    UserRefreshToken,
    UserSession,
)
from app.db.repositories import SystemSettingRepository
from app.db.transaction import transaction_scope
from app.domains.admin.schemas import (
    AdminBulkStatusUpdateIn,
    AdminSuperuserUpdateIn,
    AdminUpdateIn,
    RoleBulkDeleteIn,
    RoleBulkStatusUpdateIn,
    RolePermissionAssignIn,
    UserBulkDeleteIn,
    UserBulkStatusUpdateIn,
    UserRestoreBatchIn,
)
from app.domains.auth.schemas import UserRegisterIn
from app.services.admin_management import AdminManagementService
from app.services.authentication import WebAuthService
from scripts.cleanup_security_logs import _run as run_retention_cleanup
from scripts.consume_request_logs import GROUP_NAME, _reclaim_pending
from tests.conftest import TEST_SECRETS


def _integration_settings() -> Settings:
    database_url = os.getenv("TEST_DATABASE_URL")
    redis_url = os.getenv("TEST_REDIS_URL")
    if not database_url:
        pytest.fail("TEST_DATABASE_URL is required for stage C integration tests")
    if not redis_url:
        pytest.fail("TEST_REDIS_URL is required for stage C integration tests")
    settings = Settings(
        ENVIRONMENT="test",
        DATABASE_URL=database_url,
        TEST_DATABASE_URL=database_url,
        REDIS_MODE="required",
        REDIS_URL=redis_url,
        **{key: value for key, value in TEST_SECRETS.items() if key not in {"REDIS_MODE", "REDIS_URL"}},
    )
    settings.validate_runtime()
    return settings


def _request_metadata() -> RequestMetadata:
    return RequestMetadata(
        request_id=str(uuid.uuid7()),
        trace_id=str(uuid.uuid7()),
        ip_address="127.0.0.1",
        user_agent_summary="pytest",
        release_version="test",
    )


def test_admin_bulk_status_rejects_duplicate_ids() -> None:
    admin_id = new_uuid7()

    with pytest.raises(ValidationError):
        AdminBulkStatusUpdateIn(admin_ids=[admin_id, admin_id], is_active=False)


@pytest.mark.parametrize(
    ("schema", "field_name"),
    [
        (UserBulkDeleteIn, "user_ids"),
        (UserBulkStatusUpdateIn, "user_ids"),
        (RoleBulkDeleteIn, "role_ids"),
        (RoleBulkStatusUpdateIn, "role_ids"),
    ],
)
def test_bulk_action_schemas_reject_duplicate_ids(schema, field_name: str) -> None:
    target_id = new_uuid7()
    payload: dict[str, object] = {field_name: [target_id, target_id]}
    if schema in {UserBulkStatusUpdateIn, RoleBulkStatusUpdateIn}:
        payload["is_active"] = False

    with pytest.raises(ValidationError):
        schema.model_validate(payload)


def test_user_bulk_delete_normalizes_blank_reason() -> None:
    payload = UserBulkDeleteIn(user_ids=[new_uuid7()], deletion_reason="   ")

    assert payload.deletion_reason is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_refresh_rotation_and_reuse_revokes_session_family() -> None:
    settings = _integration_settings()
    resources = create_resources(settings)
    user_id: uuid.UUID | None = None
    metadata = _request_metadata()
    username = f"rotation-{uuid.uuid7().hex[:16]}"
    try:
        async with resources.session_factory() as session, transaction_scope(session):
            registration = await SystemSettingRepository(session).get("registration", for_update=True)
            assert registration is not None
            registration.setting_value = {"enabled": True}
            registration.revision += 1
        async with resources.session_factory() as session:
            service = WebAuthService(
                session=session,
                session_factory=resources.session_factory,
                redis=resources.redis,
                settings=settings,
                password_manager=resources.password_manager,
                metadata=metadata,
            )
            user, initial = await service.register(
                UserRegisterIn(username=username, password="stage-c-test-password", display_name="Rotation Test")
            )
            user_id = user.id
        async with resources.session_factory() as session:
            rotated = await WebAuthService(
                session=session,
                session_factory=resources.session_factory,
                redis=resources.redis,
                settings=settings,
                password_manager=resources.password_manager,
                metadata=metadata,
            ).refresh(initial.refresh_token, initial.csrf_token)
            assert rotated.refresh_token != initial.refresh_token
            assert rotated.csrf_token != initial.csrf_token
        async with resources.session_factory() as session:
            with pytest.raises(AppException) as exc_info:
                await WebAuthService(
                    session=session,
                    session_factory=resources.session_factory,
                    redis=resources.redis,
                    settings=settings,
                    password_manager=resources.password_manager,
                    metadata=metadata,
                ).refresh(initial.refresh_token, initial.csrf_token)
            assert exc_info.value.code == ErrorCode.AUTH_REFRESH_REUSE_DETECTED
        async with resources.session_factory() as session:
            stored = await session.scalar(select(UserSession).where(UserSession.id == initial.session_id))
            assert stored is not None
            assert stored.revoked_at is not None
            assert stored.revoke_reason == "refresh_reuse"
    finally:
        if user_id is not None:
            async with resources.session_factory() as session, transaction_scope(session):
                session_ids = select(UserSession.id).where(UserSession.user_id == user_id)
                await session.execute(delete(UserRefreshToken).where(UserRefreshToken.session_id.in_(session_ids)))
                await session.execute(delete(UserSession).where(UserSession.user_id == user_id))
                await session.execute(delete(SecurityLoginEvent).where(SecurityLoginEvent.principal_id == user_id))
                await session.execute(delete(User).where(User.id == user_id))
        if resources.redis is not None:
            await resources.redis.flushdb()
        await resources.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_role_permission_change_revokes_admin_sessions_and_succeeds_audit() -> None:
    settings = _integration_settings()
    resources = create_resources(settings)
    metadata = _request_metadata()
    denied_metadata = _request_metadata()
    actor_id = new_uuid7()
    target_id = new_uuid7()
    role_id = new_uuid7()
    permission_id: uuid.UUID | None = None
    created_permission = False
    session_id = new_uuid7()
    now = datetime.now(UTC)
    try:
        async with resources.session_factory() as session, transaction_scope(session):
            actor = Admin(
                id=actor_id,
                username=f"audit-actor-{actor_id.hex[:12]}",
                display_name="Audit Actor",
                password_hash="not-used-by-this-test",
                is_active=True,
                is_superuser=True,
                credential_version=1,
            )
            target = Admin(
                id=target_id,
                username=f"rbac-target-{target_id.hex[:12]}",
                display_name="RBAC Target",
                password_hash="not-used-by-this-test",
                is_active=True,
                is_superuser=False,
                credential_version=1,
            )
            role = Role(
                id=role_id,
                code=f"rbac_{role_id.hex[:12]}",
                name="RBAC Integration",
                description="Integration test role",
                is_active=True,
            )
            permission = await session.scalar(select(Permission).where(Permission.code == "users:read"))
            if permission is None:
                permission = Permission(
                    id=new_uuid7(),
                    code="users:read",
                    name="查看用户",
                    description="查看用户列表和详情",
                    is_active=True,
                    catalog_version="integration-test",
                )
                permission_id = permission.id
                created_permission = True
            target.roles = [role]
            session.add_all([actor, target, permission])
            session.add(
                AdminSession(
                    id=session_id,
                    admin_id=target_id,
                    family_id=new_uuid7(),
                    credential_profile="browser_cookie",
                    client_id="pinjie-admin",
                    csrf_digest="0" * 64,
                    ip_address="127.0.0.1",
                    user_agent_summary="pytest",
                    device_name="integration",
                    last_seen_at=now,
                    idle_expires_at=now + timedelta(days=7),
                    absolute_expires_at=now + timedelta(days=30),
                    revoked_at=None,
                    revoke_reason=None,
                )
            )

        async with resources.session_factory() as session:
            service = AdminManagementService(
                session=session,
                session_factory=resources.session_factory,
                settings=settings,
                password_manager=resources.password_manager,
                metadata=metadata,
                actor_id=actor_id,
            )
            await service.assign_role_permissions(
                role_id,
                RolePermissionAssignIn(permission_codes=["users:read"]),
            )

        async with resources.session_factory() as session:
            denied_service = AdminManagementService(
                session=session,
                session_factory=resources.session_factory,
                settings=settings,
                password_manager=resources.password_manager,
                metadata=denied_metadata,
                actor_id=actor_id,
            )
            with pytest.raises(AppException) as exc_info:
                await denied_service.assign_role_permissions(
                    role_id,
                    RolePermissionAssignIn(permission_codes=["unknown:permission"]),
                )
            assert exc_info.value.code == ErrorCode.VALIDATION_ERROR

        async with resources.session_factory() as session:
            stored_admin = await session.scalar(select(Admin).where(Admin.id == target_id))
            stored_session = await session.scalar(select(AdminSession).where(AdminSession.id == session_id))
            stored_role = await session.scalar(select(Role).where(Role.id == role_id))
            audit = await session.scalar(select(AuditEvent).where(AuditEvent.request_id == metadata.request_id))
            denied_audit = await session.scalar(
                select(AuditEvent).where(AuditEvent.request_id == denied_metadata.request_id)
            )
            assert stored_admin is not None
            assert stored_admin.credential_version == 2
            assert stored_session is not None
            assert stored_session.revoked_at is not None
            assert stored_session.revoke_reason == "role_permissions_changed"
            assert stored_role is not None
            assert [item.code for item in stored_role.permissions] == ["users:read"]
            assert audit is not None
            assert audit.action == "roles:permissions:assign"
            assert audit.result == "succeeded"
            assert audit.changed_fields == {"permission_count": 1}
            assert audit.completed_at is not None
            assert denied_audit is not None
            assert denied_audit.action == "roles:permissions:assign"
            assert denied_audit.result == "denied"
            assert denied_audit.completed_at is not None
    finally:
        async with resources.session_factory() as session, transaction_scope(session):
            await session.execute(delete(AdminSession).where(AdminSession.id == session_id))
            await session.execute(delete(AuditEvent).where(AuditEvent.actor_id == actor_id))
            await session.execute(delete(Admin).where(Admin.id.in_([actor_id, target_id])))
            await session.execute(delete(Role).where(Role.id == role_id))
            if created_permission and permission_id is not None:
                await session.execute(delete(Permission).where(Permission.id == permission_id))
        await resources.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_denied_self_superuser_change_preserves_state_and_finishes_audit() -> None:
    settings = _integration_settings()
    resources = create_resources(settings)
    metadata = _request_metadata()
    actor_id = new_uuid7()
    try:
        async with resources.session_factory() as session, transaction_scope(session):
            session.add(
                Admin(
                    id=actor_id,
                    username=f"rollback-actor-{actor_id.hex[:12]}",
                    display_name="Original Name",
                    password_hash="not-used-by-this-test",
                    is_active=True,
                    is_superuser=True,
                    credential_version=1,
                )
            )

        async with resources.session_factory() as session:
            service = AdminManagementService(
                session=session,
                session_factory=resources.session_factory,
                settings=settings,
                password_manager=resources.password_manager,
                metadata=metadata,
                actor_id=actor_id,
            )
            with pytest.raises(AppException) as exc_info:
                await service.set_admin_superuser(
                    actor_id,
                    AdminSuperuserUpdateIn(is_superuser=False),
                )
            assert exc_info.value.code == ErrorCode.STATE_CONFLICT

        async with resources.session_factory() as session:
            stored_admin = await session.scalar(select(Admin).where(Admin.id == actor_id))
            audit = await session.scalar(select(AuditEvent).where(AuditEvent.request_id == metadata.request_id))
            assert stored_admin is not None
            assert stored_admin.display_name == "Original Name"
            assert stored_admin.is_superuser is True
            assert audit is not None
            assert audit.action == "admins:superuser:update"
            assert audit.result == "denied"
            assert audit.completed_at is not None
    finally:
        async with resources.session_factory() as session, transaction_scope(session):
            await session.execute(delete(AuditEvent).where(AuditEvent.request_id == metadata.request_id))
            await session.execute(delete(Admin).where(Admin.id == actor_id))
        await resources.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_admin_avatar_and_bulk_status_are_atomic_and_audited() -> None:
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.fail("TEST_DATABASE_URL is required for admin management integration tests")
    settings = Settings(
        ENVIRONMENT="local",
        DATABASE_URL=database_url,
        TEST_DATABASE_URL=database_url,
        REDIS_MODE="disabled",
        **{key: value for key, value in TEST_SECRETS.items() if "REDIS" not in key},
    )
    resources = create_resources(settings)
    actor_id = new_uuid7()
    target_ids = [new_uuid7(), new_uuid7()]
    protected_ids = [new_uuid7(), new_uuid7()]
    session_ids = [new_uuid7(), new_uuid7()]
    missing_id = new_uuid7()
    avatar_id = new_uuid7()
    avatar_key = f"avatar/{avatar_id.hex}.png"
    avatar_url = f"{settings.upload_base_url}/{avatar_key}"
    request_ids: list[str] = []
    existing_superusers: list[tuple[uuid.UUID, int, datetime]] = []
    now = datetime.now(UTC)

    def service(session: AsyncSession) -> AdminManagementService:
        metadata = _request_metadata()
        request_ids.append(metadata.request_id)
        return AdminManagementService(
            session=session,
            session_factory=resources.session_factory,
            settings=settings,
            password_manager=resources.password_manager,
            metadata=metadata,
            actor_id=actor_id,
        )

    try:
        async with resources.session_factory() as session, transaction_scope(session):
            existing_superusers = list(
                (
                    await session.execute(
                        select(Admin.id, Admin.credential_version, Admin.updated_at).where(
                            Admin.is_active.is_(True), Admin.is_superuser.is_(True)
                        )
                    )
                ).tuples()
            )
            if existing_superusers:
                await session.execute(
                    update(Admin)
                    .where(Admin.id.in_([item[0] for item in existing_superusers]))
                    .values(is_superuser=False)
                )
            session.add(
                Admin(
                    id=actor_id,
                    username=f"bulk-actor-{actor_id.hex[-12:]}",
                    display_name="Bulk Actor",
                    password_hash="not-used-by-this-test",
                    is_active=True,
                    is_superuser=True,
                    credential_version=1,
                )
            )
            for index, target_id in enumerate(target_ids):
                session.add(
                    Admin(
                        id=target_id,
                        username=f"bulk-target-{target_id.hex[-12:]}",
                        display_name=f"Bulk Target {index}",
                        password_hash="not-used-by-this-test",
                        is_active=True,
                        is_superuser=False,
                        credential_version=1,
                    )
                )
                session.add(
                    AdminSession(
                        id=session_ids[index],
                        admin_id=target_id,
                        family_id=new_uuid7(),
                        credential_profile="browser_cookie",
                        client_id="pinjie-admin",
                        csrf_digest="0" * 64,
                        ip_address="127.0.0.1",
                        user_agent_summary="pytest",
                        device_name="integration",
                        last_seen_at=now,
                        idle_expires_at=now + timedelta(days=7),
                        absolute_expires_at=now + timedelta(days=30),
                        revoked_at=None,
                        revoke_reason=None,
                    )
                )
            for protected_id in protected_ids:
                session.add(
                    Admin(
                        id=protected_id,
                        username=f"protected-target-{protected_id.hex[-12:]}",
                        display_name="Protected Superuser",
                        password_hash="not-used-by-this-test",
                        is_active=True,
                        is_superuser=True,
                        credential_version=1,
                    )
                )

        async with resources.session_factory() as session, transaction_scope(session):
            session.add(
                Asset(
                    id=avatar_id,
                    uploader_type="admin",
                    uploader_id=actor_id,
                    storage_driver="local",
                    file_key=avatar_key,
                    original_name="avatar.png",
                    mime_type="image/png",
                    file_size=16,
                    file_hash="a" * 64,
                    url=avatar_url,
                    scene="avatar",
                )
            )

        async with resources.session_factory() as current_session:
            updated = await service(current_session).update_admin(
                target_ids[0],
                AdminUpdateIn(display_name=" Updated Target ", avatar=f" {avatar_url} "),
            )
            assert updated.display_name == "Updated Target"
            assert updated.avatar == avatar_url

        async with resources.session_factory() as current_session:
            cleared = await service(current_session).update_admin(target_ids[0], AdminUpdateIn(avatar=None))
            assert cleared.avatar is None

        async with resources.session_factory() as current_session:
            disabled = await service(current_session).set_admin_status_bulk(
                AdminBulkStatusUpdateIn(admin_ids=list(reversed(target_ids)), is_active=False)
            )
            assert [admin.id for admin in disabled] == sorted(target_ids)

        async with resources.session_factory() as session:
            stored_targets = list(
                (await session.scalars(select(Admin).where(Admin.id.in_(target_ids)).order_by(Admin.id))).all()
            )
            stored_sessions = list(
                (await session.scalars(select(AdminSession).where(AdminSession.id.in_(session_ids)))).all()
            )
            bulk_audit = await session.scalar(select(AuditEvent).where(AuditEvent.request_id == request_ids[-1]))
            assert all(not admin.is_active and admin.credential_version == 2 for admin in stored_targets)
            assert all(
                item.revoked_at is not None and item.revoke_reason == "account_status_changed"
                for item in stored_sessions
            )
            assert bulk_audit is not None
            assert bulk_audit.action == "admins:status:update-bulk"
            assert bulk_audit.result == "succeeded"
            assert bulk_audit.changed_fields == {
                "admin_ids": [str(admin_id) for admin_id in reversed(target_ids)],
                "is_active": False,
            }

        async with resources.session_factory() as current_session:
            await service(current_session).set_admin_status_bulk(
                AdminBulkStatusUpdateIn(admin_ids=target_ids, is_active=True)
            )

        async with resources.session_factory() as current_session:
            with pytest.raises(AppException) as current_exc:
                await service(current_session).set_admin_status_bulk(
                    AdminBulkStatusUpdateIn(admin_ids=[target_ids[0], actor_id], is_active=False)
                )
            assert current_exc.value.code == ErrorCode.STATE_CONFLICT

        async with resources.session_factory() as current_session:
            with pytest.raises(AppException) as missing_exc:
                await service(current_session).set_admin_status_bulk(
                    AdminBulkStatusUpdateIn(admin_ids=[target_ids[0], missing_id], is_active=False)
                )
            assert missing_exc.value.code == ErrorCode.ADMIN_NOT_FOUND

        async with resources.session_factory() as current_session:
            disabled_superusers = await service(current_session).set_admin_status_bulk(
                AdminBulkStatusUpdateIn(admin_ids=protected_ids, is_active=False)
            )
            assert [admin.id for admin in disabled_superusers] == sorted(protected_ids)

        async with resources.session_factory() as session:
            unchanged_targets = list(
                (await session.scalars(select(Admin).where(Admin.id.in_(target_ids + protected_ids)))).all()
            )
            assert all(admin.is_active for admin in unchanged_targets if admin.id in target_ids)
            assert all(not admin.is_active for admin in unchanged_targets if admin.id in protected_ids)
            assert all(admin.credential_version == 3 for admin in unchanged_targets if admin.id in target_ids)
            assert all(admin.credential_version == 2 for admin in unchanged_targets if admin.id in protected_ids)
            recent_audits = list(
                (await session.scalars(select(AuditEvent).where(AuditEvent.request_id.in_(request_ids[-3:])))).all()
            )
            assert len(recent_audits) == 3
            assert {event.result for event in recent_audits} == {"denied", "succeeded"}
    finally:
        async with resources.session_factory() as session, transaction_scope(session):
            await session.execute(delete(AdminSession).where(AdminSession.id.in_(session_ids)))
            await session.execute(delete(AuditEvent).where(AuditEvent.actor_id == actor_id))
            await session.execute(delete(Asset).where(Asset.id == avatar_id))
            await session.execute(delete(Admin).where(Admin.id.in_([actor_id, *target_ids, *protected_ids])))
            for admin_id, credential_version, updated_at in existing_superusers:
                await session.execute(
                    update(Admin)
                    .where(Admin.id == admin_id)
                    .values(
                        is_superuser=True,
                        credential_version=credential_version,
                        updated_at=updated_at,
                    )
                )
        await resources.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_user_and_role_bulk_lifecycle_operations_are_atomic_and_audited() -> None:
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.fail("TEST_DATABASE_URL is required for admin management integration tests")
    settings = Settings(
        ENVIRONMENT="local",
        DATABASE_URL=database_url,
        TEST_DATABASE_URL=database_url,
        REDIS_MODE="disabled",
        **{key: value for key, value in TEST_SECRETS.items() if "REDIS" not in key},
    )
    resources = create_resources(settings)
    actor_id = new_uuid7()
    admin_id = new_uuid7()
    user_ids = [new_uuid7(), new_uuid7()]
    user_session_ids = [new_uuid7(), new_uuid7()]
    admin_session_id = new_uuid7()
    assigned_role_id = new_uuid7()
    unused_role_ids = [new_uuid7(), new_uuid7()]
    request_ids: list[str] = []
    now = datetime.now(UTC)

    def service(session: AsyncSession) -> AdminManagementService:
        metadata = _request_metadata()
        request_ids.append(metadata.request_id)
        return AdminManagementService(
            session=session,
            session_factory=resources.session_factory,
            settings=settings,
            password_manager=resources.password_manager,
            metadata=metadata,
            actor_id=actor_id,
        )

    try:
        async with resources.session_factory() as session, transaction_scope(session):
            assigned_role = Role(
                id=assigned_role_id,
                code=f"assigned-{assigned_role_id.hex[-12:]}",
                name="Assigned Role",
                is_active=True,
            )
            session.add_all(
                [
                    Admin(
                        id=actor_id,
                        username=f"lifecycle-actor-{actor_id.hex[-12:]}",
                        display_name="Lifecycle Actor",
                        password_hash="not-used-by-this-test",
                        is_active=True,
                        is_superuser=False,
                        credential_version=1,
                    ),
                    Admin(
                        id=admin_id,
                        username=f"lifecycle-admin-{admin_id.hex[-12:]}",
                        display_name="Lifecycle Admin",
                        password_hash="not-used-by-this-test",
                        is_active=True,
                        is_superuser=False,
                        credential_version=1,
                        roles=[assigned_role],
                    ),
                    assigned_role,
                    *[
                        Role(
                            id=role_id,
                            code=f"unused-{role_id.hex[-12:]}",
                            name=f"Unused Role {index}",
                            is_active=True,
                        )
                        for index, role_id in enumerate(unused_role_ids)
                    ],
                ]
            )
            for index, user_id in enumerate(user_ids):
                session.add(
                    User(
                        id=user_id,
                        username=f"lifecycle-user-{user_id.hex[-12:]}",
                        email=f"lifecycle-{user_id.hex[-12:]}@example.com",
                        display_name=f"Lifecycle User {index}",
                        password_hash="not-used-by-this-test",
                        is_active=True,
                        credential_version=1,
                    )
                )
                session.add(
                    UserSession(
                        id=user_session_ids[index],
                        user_id=user_id,
                        family_id=new_uuid7(),
                        credential_profile="browser_cookie",
                        client_id="pinjie-web",
                        csrf_digest="a" * 64,
                        last_seen_at=now,
                        idle_expires_at=now + timedelta(days=7),
                        absolute_expires_at=now + timedelta(days=30),
                    )
                )
            session.add(
                AdminSession(
                    id=admin_session_id,
                    admin_id=admin_id,
                    family_id=new_uuid7(),
                    credential_profile="browser_cookie",
                    client_id="pinjie-admin",
                    csrf_digest="b" * 64,
                    last_seen_at=now,
                    idle_expires_at=now + timedelta(days=7),
                    absolute_expires_at=now + timedelta(days=30),
                )
            )

        async with resources.session_factory() as current_session:
            result = await service(current_session).set_user_status_bulk(
                UserBulkStatusUpdateIn(user_ids=list(reversed(user_ids)), is_active=False)
            )
            assert result.completed_count == 2
            assert result.target_ids == sorted(user_ids)

        async with resources.session_factory() as session:
            stored_users = list((await session.scalars(select(User).where(User.id.in_(user_ids)))).all())
            stored_sessions = list(
                (await session.scalars(select(UserSession).where(UserSession.id.in_(user_session_ids)))).all()
            )
            assert all(not user.is_active and user.credential_version == 2 for user in stored_users)
            assert all(
                item.revoked_at is not None and item.revoke_reason == "account_status_changed"
                for item in stored_sessions
            )

        async with resources.session_factory() as current_session:
            result = await service(current_session).delete_users_bulk(
                UserBulkDeleteIn(user_ids=user_ids, deletion_reason="管理员批量清理")
            )
            assert result.completed_count == 2
            assert result.target_ids == sorted(user_ids)

        async with resources.session_factory() as session:
            deleted_users = list((await session.scalars(select(User).where(User.id.in_(user_ids)))).all())
            assert all(
                user.username.startswith("lifecycle-user-")
                and user.email is not None
                and user.display_name is not None
                and not user.is_active
                and user.credential_version == 3
                and user.deleted_at is not None
                and user.deleted_by_id == actor_id
                and user.deleted_by_type == "admin"
                and user.deletion_reason == "管理员批量清理"
                for user in deleted_users
            )

        async with resources.session_factory() as current_session:
            restored = await service(current_session).restore_user(user_ids[0])
            assert restored.id == user_ids[0]
            assert not restored.is_active
            assert restored.deleted_at is None

        async with resources.session_factory() as current_session:
            result = await service(current_session).restore_users_bulk(UserRestoreBatchIn(user_ids=[user_ids[1]]))
            assert result.completed_count == 1
            assert result.target_ids == [user_ids[1]]

        async with resources.session_factory() as session:
            restored_users = list((await session.scalars(select(User).where(User.id.in_(user_ids)))).all())
            assert all(
                not user.is_active
                and user.credential_version == 4
                and user.deleted_at is None
                and user.deleted_by_id is None
                and user.deleted_by_type is None
                and user.deletion_reason is None
                for user in restored_users
            )

        async with resources.session_factory() as current_session:
            result = await service(current_session).set_role_status_bulk(
                RoleBulkStatusUpdateIn(role_ids=[assigned_role_id], is_active=False)
            )
            assert result.completed_count == 1
            assert result.target_ids == [assigned_role_id]

        async with resources.session_factory() as session:
            stored_admin = await session.get(Admin, admin_id)
            stored_admin_session = await session.get(AdminSession, admin_session_id)
            stored_role = await session.get(Role, assigned_role_id)
            assert stored_admin is not None and stored_admin.credential_version == 2
            assert stored_admin_session is not None
            assert stored_admin_session.revoked_at is not None
            assert stored_admin_session.revoke_reason == "role_status_changed"
            assert stored_role is not None and not stored_role.is_active

        async with resources.session_factory() as current_session:
            with pytest.raises(AppException) as blocked_exc:
                await service(current_session).delete_roles_bulk(
                    RoleBulkDeleteIn(role_ids=[assigned_role_id, unused_role_ids[0]])
                )
            assert blocked_exc.value.code == ErrorCode.STATE_CONFLICT

        async with resources.session_factory() as session:
            remaining_roles = list(
                (await session.scalars(select(Role).where(Role.id.in_([assigned_role_id, *unused_role_ids])))).all()
            )
            denied_audit = await session.scalar(select(AuditEvent).where(AuditEvent.request_id == request_ids[-1]))
            assert {role.id for role in remaining_roles} == {assigned_role_id, *unused_role_ids}
            assert denied_audit is not None and denied_audit.result == "denied"

        async with resources.session_factory() as current_session:
            result = await service(current_session).delete_roles_bulk(
                RoleBulkDeleteIn(role_ids=list(reversed(unused_role_ids)))
            )
            assert result.completed_count == 2
            assert result.target_ids == sorted(unused_role_ids)

        async with resources.session_factory() as session:
            assert await session.scalar(select(func.count()).select_from(Role).where(Role.id.in_(unused_role_ids))) == 0
            succeeded_audits = list(
                (
                    await session.scalars(
                        select(AuditEvent).where(
                            AuditEvent.request_id.in_(request_ids),
                            AuditEvent.result == "succeeded",
                        )
                    )
                ).all()
            )
            assert {event.action for event in succeeded_audits} == {
                "users:status:update-bulk",
                "users:delete-bulk",
                "users:restore",
                "users:restore-bulk",
                "roles:status:update-bulk",
                "roles:delete-bulk",
            }
    finally:
        async with resources.session_factory() as session, transaction_scope(session):
            await session.execute(delete(UserSession).where(UserSession.id.in_(user_session_ids)))
            await session.execute(delete(AdminSession).where(AdminSession.id == admin_session_id))
            await session.execute(delete(AuditEvent).where(AuditEvent.actor_id == actor_id))
            await session.execute(delete(Admin).where(Admin.id.in_([actor_id, admin_id])))
            await session.execute(delete(Role).where(Role.id.in_([assigned_role_id, *unused_role_ids])))
            await session.execute(delete(User).where(User.id.in_(user_ids)))
        await resources.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_non_superuser_cannot_demote_superusers_concurrently() -> None:
    settings = _integration_settings()
    resources = create_resources(settings)
    actor_id = new_uuid7()
    target_ids = [new_uuid7(), new_uuid7()]
    request_ids: list[str] = []
    existing_superusers: list[tuple[uuid.UUID, int, datetime]] = []
    try:
        async with resources.session_factory() as session, transaction_scope(session):
            existing_superusers = list(
                (
                    await session.execute(
                        select(Admin.id, Admin.credential_version, Admin.updated_at).where(
                            Admin.is_active.is_(True), Admin.is_superuser.is_(True)
                        )
                    )
                ).tuples()
            )
            if existing_superusers:
                await session.execute(
                    update(Admin)
                    .where(Admin.id.in_([item[0] for item in existing_superusers]))
                    .values(is_superuser=False)
                )
            session.add(
                Admin(
                    id=actor_id,
                    username=f"guard-actor-{actor_id.hex[-12:]}",
                    display_name="Guard Actor",
                    password_hash="not-used-by-this-test",
                    is_active=True,
                    is_superuser=False,
                    credential_version=1,
                )
            )
            for target_id in target_ids:
                session.add(
                    Admin(
                        id=target_id,
                        username=f"guard-target-{target_id.hex[-12:]}",
                        display_name="Guard Target",
                        password_hash="not-used-by-this-test",
                        is_active=True,
                        is_superuser=True,
                        credential_version=1,
                    )
                )

        async def demote(target_id: uuid.UUID) -> Admin | BaseException:
            metadata = _request_metadata()
            request_ids.append(metadata.request_id)
            async with resources.session_factory() as session:
                service = AdminManagementService(
                    session=session,
                    session_factory=resources.session_factory,
                    settings=settings,
                    password_manager=resources.password_manager,
                    metadata=metadata,
                    actor_id=actor_id,
                )
                try:
                    return await service.set_admin_superuser(
                        target_id,
                        AdminSuperuserUpdateIn(is_superuser=False),
                    )
                except BaseException as exc:
                    return exc

        results = await asyncio.gather(*(demote(target_id) for target_id in target_ids))
        assert sum(isinstance(result, Admin) for result in results) == 0
        failures = [result for result in results if isinstance(result, AppException)]
        assert len(failures) == 2
        assert all(failure.code == ErrorCode.PERMISSION_DENIED for failure in failures)

        async with resources.session_factory() as session:
            active_superusers = int(
                (
                    await session.scalar(
                        select(func.count())
                        .select_from(Admin)
                        .where(Admin.id.in_(target_ids), Admin.is_active.is_(True), Admin.is_superuser.is_(True))
                    )
                )
                or 0
            )
            assert active_superusers == 2
    finally:
        async with resources.session_factory() as session, transaction_scope(session):
            await session.execute(delete(AuditEvent).where(AuditEvent.request_id.in_(request_ids)))
            await session.execute(delete(Admin).where(Admin.id.in_([actor_id, *target_ids])))
            for admin_id, credential_version, updated_at in existing_superusers:
                await session.execute(
                    update(Admin)
                    .where(Admin.id == admin_id)
                    .values(
                        is_superuser=True,
                        credential_version=credential_version,
                        updated_at=updated_at,
                    )
                )
        await resources.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_redis_rate_limit_is_atomic_and_has_ttl() -> None:
    settings = _integration_settings()
    resources = create_resources(settings)
    assert resources.redis is not None
    key = f"pinjie:test:rate-limit:v1:{uuid.uuid7()}"
    try:
        first = await enforce_rate_limit(resources.redis, key=key, limit=2, window_seconds=60)
        second = await enforce_rate_limit(resources.redis, key=key, limit=2, window_seconds=60)
        assert first.count == 1
        assert second.count == 2
        assert 1 <= await resources.redis.ttl(key) <= 60
        with pytest.raises(AppException) as exc_info:
            await enforce_rate_limit(resources.redis, key=key, limit=2, window_seconds=60)
        assert exc_info.value.code == ErrorCode.RATE_LIMITED
        assert exc_info.value.headers["Retry-After"]
    finally:
        await resources.redis.delete(key)
        await resources.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_security_retention_cleanup_dry_run_and_apply_cascade_refresh_tokens(capsys) -> None:
    settings = _integration_settings().model_copy(
        update={
            "security_event_retention_days": 30,
            "request_log_retention_days": 1,
            "session_retention_days": 1,
        }
    )
    database_name = urlsplit(settings.database_url or "").path.removeprefix("/")
    old = datetime.now(UTC) - timedelta(days=3)
    user_id = new_uuid7()
    admin_id = new_uuid7()
    user_session_id = new_uuid7()
    admin_session_id = new_uuid7()
    user_refresh_id = new_uuid7()
    admin_refresh_id = new_uuid7()

    seed_resources = create_resources(settings)
    try:
        async with seed_resources.session_factory() as session, transaction_scope(session):
            session.add_all(
                [
                    User(
                        id=user_id,
                        username=f"retention-user-{user_id.hex[:12]}",
                        password_hash="not-used-by-this-test",
                        is_active=True,
                        credential_version=1,
                    ),
                    Admin(
                        id=admin_id,
                        username=f"retention-admin-{admin_id.hex[:12]}",
                        password_hash="not-used-by-this-test",
                        is_active=True,
                        is_superuser=False,
                        credential_version=1,
                    ),
                ]
            )
            await session.flush()
            session.add_all(
                [
                    UserSession(
                        id=user_session_id,
                        user_id=user_id,
                        family_id=new_uuid7(),
                        credential_profile="browser_cookie",
                        client_id="pinjie-web",
                        csrf_digest="a" * 64,
                        last_seen_at=old,
                        idle_expires_at=old,
                        absolute_expires_at=old,
                    ),
                    AdminSession(
                        id=admin_session_id,
                        admin_id=admin_id,
                        family_id=new_uuid7(),
                        credential_profile="browser_cookie",
                        client_id="pinjie-admin",
                        csrf_digest="b" * 64,
                        last_seen_at=old,
                        idle_expires_at=old,
                        absolute_expires_at=old,
                    ),
                ]
            )
            await session.flush()
            session.add_all(
                [
                    UserRefreshToken(
                        id=user_refresh_id,
                        session_id=user_session_id,
                        token_digest=user_refresh_id.hex * 2,
                        issued_at=old,
                        expires_at=old,
                    ),
                    AdminRefreshToken(
                        id=admin_refresh_id,
                        session_id=admin_session_id,
                        token_digest=admin_refresh_id.hex * 2,
                        issued_at=old,
                        expires_at=old,
                    ),
                ]
            )
    finally:
        await seed_resources.close()

    try:
        dry_run_resources = create_resources(settings)
        with (
            patch("scripts.cleanup_security_logs.get_settings", return_value=settings),
            patch("scripts.cleanup_security_logs.create_resources", return_value=dry_run_resources),
        ):
            await run_retention_cleanup(Namespace(apply=False, confirm_database=database_name))
        assert "Dry run only; no rows deleted" in capsys.readouterr().out

        verification_resources = create_resources(settings)
        try:
            async with verification_resources.session_factory() as session:
                assert await session.get(UserSession, user_session_id) is not None
                assert await session.get(AdminSession, admin_session_id) is not None
        finally:
            await verification_resources.close()

        apply_resources = create_resources(settings)
        with (
            patch("scripts.cleanup_security_logs.get_settings", return_value=settings),
            patch("scripts.cleanup_security_logs.create_resources", return_value=apply_resources),
        ):
            await run_retention_cleanup(Namespace(apply=True, confirm_database=database_name))
        assert "Retention cleanup applied" in capsys.readouterr().out

        verification_resources = create_resources(settings)
        try:
            async with verification_resources.session_factory() as session:
                assert await session.get(UserSession, user_session_id) is None
                assert await session.get(AdminSession, admin_session_id) is None
                assert await session.get(UserRefreshToken, user_refresh_id) is None
                assert await session.get(AdminRefreshToken, admin_refresh_id) is None
        finally:
            await verification_resources.close()
    finally:
        cleanup_resources = create_resources(settings)
        try:
            async with cleanup_resources.session_factory() as session, transaction_scope(session):
                await session.execute(delete(UserRefreshToken).where(UserRefreshToken.session_id == user_session_id))
                await session.execute(delete(AdminRefreshToken).where(AdminRefreshToken.session_id == admin_session_id))
                await session.execute(delete(UserSession).where(UserSession.id == user_session_id))
                await session.execute(delete(AdminSession).where(AdminSession.id == admin_session_id))
                await session.execute(delete(User).where(User.id == user_id))
                await session.execute(delete(Admin).where(Admin.id == admin_id))
        finally:
            await cleanup_resources.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_request_log_consumer_reclaims_pending_and_routes_invalid_messages_to_dlq() -> None:
    settings = _integration_settings().model_copy(update={"request_log_mode": "metadata"})
    resources = create_resources(settings)
    assert resources.redis is not None
    redis = resources.redis
    keys = cache_keys(settings)
    stream = keys.request_log_stream()
    dead_letter = keys.request_log_dead_letter()
    request_id = str(new_uuid7())
    valid_fields = {
        "request_id": request_id,
        "trace_id": str(new_uuid7()),
        "method": "GET",
        "route_template": "/api/v1/system/status",
        "status_code": "200",
        "duration_ms": "7",
        "principal_type": "",
        "principal_digest": "",
        "release_version": "test",
        "occurred_at": "2026-08-15T00:00:00+00:00",
    }
    try:
        try:
            await redis.xgroup_create(stream, GROUP_NAME, id="0", mkstream=True)
        except ResponseError as exc:
            if not str(exc).startswith("BUSYGROUP"):
                raise
        await redis.xadd(stream, valid_fields)
        await redis.xadd(stream, {"request_id": str(new_uuid7())})
        delivered = await redis.xreadgroup(GROUP_NAME, "crashed-consumer", {stream: ">"}, count=2)
        assert len(delivered[0][1]) == 2

        reclaimed = await _reclaim_pending(
            resources,
            stream=stream,
            dead_letter=dead_letter,
            redis=redis,
            consumer="recovery-consumer",
            batch_size=10,
            min_idle_ms=0,
        )
        assert reclaimed == 2
        async with resources.session_factory() as session:
            stored = await session.scalar(select(RequestLog).where(RequestLog.request_id == request_id))
            assert stored is not None
            assert stored.route_template == "/api/v1/system/status"
        assert await redis.xlen(dead_letter) == 1
        pending = await redis.xpending(stream, GROUP_NAME)
        assert pending["pending"] == 0
    finally:
        async with resources.session_factory() as session, transaction_scope(session):
            await session.execute(delete(RequestLog).where(RequestLog.request_id == request_id))
        await redis.delete(stream, dead_letter)
        await resources.close()
