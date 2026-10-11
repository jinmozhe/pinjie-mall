import uuid
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from typing import TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.db.repositories import AdminRepository, SessionRepository
from app.db.repositories.commerce_access import CommerceAccessRepository
from app.domains.admin.permissions import PermissionCode
from app.services.security_events import AuditCoordinator, AuditSuccess

T = TypeVar("T")

_ACTION_PERMISSIONS = {
    "users:status:update": PermissionCode.USERS_UPDATE,
    "users:status:update-bulk": PermissionCode.USERS_UPDATE,
    "users:delete-bulk": PermissionCode.USERS_DELETE,
    "users:restore-bulk": PermissionCode.USERS_RESTORE,
    "users:sessions:revoke-all": PermissionCode.USERS_SESSIONS_REVOKE,
    "admins:superuser:update": PermissionCode.ADMINS_SUPERUSER_CHANGE,
    "admins:status:update": PermissionCode.ADMINS_UPDATE,
    "admins:status:update-bulk": PermissionCode.ADMINS_UPDATE,
    "admins:sessions:revoke-all": PermissionCode.ADMINS_SESSIONS_REVOKE,
    "roles:status:update-bulk": PermissionCode.ROLES_UPDATE,
    "roles:delete-bulk": PermissionCode.ROLES_DELETE,
    "points.adjust": PermissionCode.POINTS_ADJUST,
    "commission-policies.create": PermissionCode.COMMISSION_POLICIES_CREATE,
    "commission-policies.update": PermissionCode.COMMISSION_POLICIES_UPDATE,
    "commission-policies.publish": PermissionCode.COMMISSION_POLICIES_PUBLISH,
    "settings.commission-control.update": PermissionCode.SETTINGS_COMMISSION_CONTROL_UPDATE,
    "settings.order-shipping.update": PermissionCode.SETTINGS_ORDER_SHIPPING_UPDATE,
    "settings.site.update": PermissionCode.SETTINGS_SITE_UPDATE,
    "settings.site.logo.update": PermissionCode.SETTINGS_SITE_UPDATE,
    "settings.site.logo.delete": PermissionCode.SETTINGS_SITE_UPDATE,
    "settings.registration.update": PermissionCode.SETTINGS_REGISTRATION_UPDATE,
    "settings.miniapp_registration.update": PermissionCode.SETTINGS_MINIAPP_REGISTRATION_UPDATE,
    "asset.delete": PermissionCode.ASSETS_DELETE,
    "assets:delete-bulk": PermissionCode.ASSETS_DELETE,
}
_SAVE_PERMISSIONS = {
    "member-levels.write": (PermissionCode.MEMBER_LEVELS_CREATE, PermissionCode.MEMBER_LEVELS_UPDATE),
    "member-level-conditions.write": (
        PermissionCode.MEMBER_LEVEL_CONDITIONS_CREATE,
        PermissionCode.MEMBER_LEVEL_CONDITIONS_UPDATE,
    ),
    "member-price-rules.write": (PermissionCode.MEMBER_PRICE_RULES_CREATE, PermissionCode.MEMBER_PRICE_RULES_UPDATE),
}


class AdminAuditCoordinator:
    """在审计事务内锁定权威身份、校验会话与准确权限，再执行业务操作。"""

    def __init__(
        self, *, audit: AuditCoordinator, session: AsyncSession, actor_id: uuid.UUID, session_id: uuid.UUID | None
    ) -> None:
        self._audit = audit
        self._access = CommerceAccessRepository(session)
        self._admins = AdminRepository(session)
        self._sessions = SessionRepository(session)
        self._actor_id = actor_id
        self._session_id = session_id

    async def execute(
        self,
        *,
        action: str,
        target_type: str,
        target_id: uuid.UUID | None,
        changed_fields: dict[str, object],
        operation: Callable[[], Awaitable[T]],
        permission: PermissionCode | None = None,
        admin_ids: Sequence[uuid.UUID] = (),
        role_ids: Sequence[uuid.UUID] = (),
        target_revision: int | None = None,
        success_event: Callable[[T], AuditSuccess] | None = None,
    ) -> T:
        if permission is None:
            if action in _SAVE_PERMISSIONS:
                permission = _SAVE_PERMISSIONS[action][0 if target_id is None else 1]
            elif action in _ACTION_PERMISSIONS:
                permission = _ACTION_PERMISSIONS[action]
            else:
                # Actions already using the source permission code keep that exact permission.
                permission = PermissionCode(action)

        async def authorized() -> T:
            if self._session_id is None:
                raise self._denied()
            if action.startswith(("admins:", "roles:")):
                # Serialize identity graph changes before taking ANY admin/session/role
                # row lock, so the affected role membership cannot change during collection.
                await self._admins.lock_management_guard()
                targets = {self._actor_id, *admin_ids}
                affected_roles = set(role_ids)
                if target_type == "admin" and target_id is not None:
                    targets.add(target_id)
                if target_type == "role" and target_id is not None:
                    affected_roles.add(target_id)
                if target_type == "admin_batch" and not admin_ids:
                    raise ValueError("admin batch writes require explicit lock targets")
                if target_type == "role_batch" and not role_ids:
                    raise ValueError("role batch writes require explicit lock targets")
                targets.update(await self._admins.admin_ids_for_roles(sorted(affected_roles)))
                await self._admins.get_many(sorted(targets), for_update=True)

            admin = await self._access.get_admin_for_update(self._actor_id)
            actor_session = await self._sessions.get_admin(self._session_id, for_update=True)
            now = datetime.now(UTC)
            if (
                admin is None
                or not admin.is_active
                or actor_session is None
                or actor_session.admin_id != self._actor_id
                or actor_session.revoked_at is not None
                or actor_session.idle_expires_at <= now
                or actor_session.absolute_expires_at <= now
            ):
                raise self._denied()
            granted = admin.is_superuser or any(
                role.is_active and any(item.is_active and item.code == permission.value for item in role.permissions)
                for role in admin.roles
            )
            if not granted:
                raise self._denied()
            return await operation()

        return await self._audit.execute(
            action=action,
            target_type=target_type,
            target_id=target_id,
            target_revision=target_revision,
            changed_fields=changed_fields,
            operation=authorized,
            success_event=success_event,
        )

    @staticmethod
    def _denied() -> AppException:
        return AppException(status_code=403, code=ErrorCode.PERMISSION_DENIED, message="当前管理员权限已失效")
