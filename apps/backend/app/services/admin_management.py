import asyncio
import json
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from importlib.metadata import version
from platform import python_version
from typing import Literal, TypeVar

from loguru import logger
from pydantic import ValidationError
from redis.exceptions import RedisError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.cache_keys import CacheKeys, cache_keys
from app.core.config import Settings
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.core.health import check_database
from app.core.identifiers import new_uuid7
from app.core.pagination import PageResult
from app.core.redis import check_redis
from app.core.request_metadata import RequestMetadata
from app.core.resources import AppResources
from app.core.security import PasswordManager
from app.db.models import Admin, AdminSession, Asset, AuditEvent, Role, User, UserSession
from app.db.repositories import (
    AdminRepository,
    RequestLogRepository,
    SecurityRepository,
    SessionRepository,
    UserRepository,
)
from app.db.repositories.commerce_access import CommerceAccessRepository
from app.domains.admin.permissions import PERMISSION_CODES, ROLE_ASSIGNABLE_PERMISSION_CODES, PermissionCode
from app.domains.admin.presenters import admin_read, role_read
from app.domains.admin.schemas import (
    AdminBulkStatusUpdateIn,
    AdminCreateIn,
    AdminRead,
    AdminRoleAssignIn,
    AdminSuperuserUpdateIn,
    AdminUpdateIn,
    AdminUserCreateIn,
    AdminUserRead,
    AuditEventPage,
    AuditEventRead,
    BatchActionResult,
    DatabaseHealthRead,
    InfrastructureOverviewRead,
    LoginEventPage,
    LoginEventRead,
    PasswordResetIn,
    PermissionRead,
    RedisHealthRead,
    RequestLogPage,
    RequestLogRead,
    RoleBulkDeleteIn,
    RoleBulkStatusUpdateIn,
    RoleCreateIn,
    RolePage,
    RolePermissionAssignIn,
    RoleUpdateIn,
    SecurityConfigurationRead,
    StatusUpdateIn,
    StorageConfigurationRead,
    SystemOverviewRead,
    SystemTelemetryRead,
    UserBulkDeleteIn,
    UserBulkStatusUpdateIn,
    UserPage,
    UserRestoreBatchIn,
)
from app.domains.users.schemas import UserUpdateIn
from app.services.assets import resolve_admin_avatar
from app.services.security_events import AuditCoordinator

_FASTAPI_VERSION = version("fastapi")
_PYTHON_VERSION = python_version()
_SYSTEM_TELEMETRY_TTL_SECONDS = 120
T = TypeVar("T")

# 当前默认部署为单 Backend 实例；该锁避免同一实例内缓存失效时重复执行精确统计。
_SYSTEM_TELEMETRY_REFRESH_LOCK = asyncio.Lock()

_MANAGEMENT_ACTION_PERMISSIONS: dict[str, PermissionCode] = {
    "users:create": PermissionCode.USERS_CREATE,
    "users:update": PermissionCode.USERS_UPDATE,
    "users:status:update": PermissionCode.USERS_UPDATE,
    "users:status:update-bulk": PermissionCode.USERS_UPDATE,
    "users:delete-bulk": PermissionCode.USERS_DELETE,
    "users:restore": PermissionCode.USERS_RESTORE,
    "users:restore-bulk": PermissionCode.USERS_RESTORE,
    "users:credentials:reset": PermissionCode.USERS_CREDENTIALS_RESET,
    "users:sessions:revoke": PermissionCode.USERS_SESSIONS_REVOKE,
    "users:sessions:revoke-all": PermissionCode.USERS_SESSIONS_REVOKE,
    "admins:create": PermissionCode.ADMINS_CREATE,
    "admins:update": PermissionCode.ADMINS_UPDATE,
    "admins:superuser:update": PermissionCode.ADMINS_SUPERUSER_CHANGE,
    "admins:status:update": PermissionCode.ADMINS_UPDATE,
    "admins:status:update-bulk": PermissionCode.ADMINS_UPDATE,
    "admins:credentials:reset": PermissionCode.ADMINS_CREDENTIALS_RESET,
    "admins:roles:assign": PermissionCode.ADMINS_ROLES_ASSIGN,
    "admins:sessions:revoke-all": PermissionCode.ADMINS_SESSIONS_REVOKE,
    "roles:create": PermissionCode.ROLES_CREATE,
    "roles:update": PermissionCode.ROLES_UPDATE,
    "roles:status:update-bulk": PermissionCode.ROLES_UPDATE,
    "roles:delete": PermissionCode.ROLES_DELETE,
    "roles:delete-bulk": PermissionCode.ROLES_DELETE,
    "roles:permissions:assign": PermissionCode.ROLES_PERMISSIONS_ASSIGN,
}


class ManagementAuditCoordinator:
    def __init__(
        self, *, audit: AuditCoordinator, session: AsyncSession, actor_id: uuid.UUID, session_id: uuid.UUID | None
    ) -> None:
        self._audit = audit
        self._access = CommerceAccessRepository(session)
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
    ) -> T:
        permission = _MANAGEMENT_ACTION_PERMISSIONS.get(action)
        if permission is None:
            raise ValueError(f"management action is missing a permission mapping: {action}")

        async def authorized() -> T:
            admin = await self._access.get_admin_for_update(self._actor_id)
            now = datetime.now(UTC)
            actor_session = (
                await self._sessions.get_admin(self._session_id, for_update=True)
                if self._session_id is not None
                else None
            )
            if (
                admin is None
                or not admin.is_active
                or (
                    self._session_id is not None
                    and (
                        actor_session is None
                        or actor_session.admin_id != self._actor_id
                        or actor_session.revoked_at is not None
                        or actor_session.idle_expires_at <= now
                        or actor_session.absolute_expires_at <= now
                    )
                )
            ):
                raise AppException(status_code=403, code=ErrorCode.PERMISSION_DENIED, message="当前管理员权限已失效")
            granted = admin.is_superuser or any(
                role.is_active and any(item.is_active and item.code == permission.value for item in role.permissions)
                for role in admin.roles
            )
            if not granted:
                raise AppException(status_code=403, code=ErrorCode.PERMISSION_DENIED, message="当前管理员权限已失效")
            return await operation()

        return await self._audit.execute(
            action=action,
            target_type=target_type,
            target_id=target_id,
            changed_fields=changed_fields,
            operation=authorized,
        )


class AdminManagementService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
        password_manager: PasswordManager,
        metadata: RequestMetadata,
        actor_id: uuid.UUID,
        actor_session_id: uuid.UUID | None = None,
        resources: AppResources | None = None,
        started_at: datetime | None = None,
    ) -> None:
        self.session = session
        self.settings = settings
        self.password_manager = password_manager
        self.resources = resources
        self.started_at = started_at
        self.cache_keys: CacheKeys = cache_keys(settings)
        self.users = UserRepository(session)
        self.admins = AdminRepository(session)
        self.sessions = SessionRepository(session)
        self.security = SecurityRepository(session)
        self.request_logs = RequestLogRepository(session)
        self.audit = ManagementAuditCoordinator(
            audit=AuditCoordinator(
                session=session,
                session_factory=session_factory,
                actor_id=actor_id,
                metadata=metadata,
            ),
            session=session,
            actor_id=actor_id,
            session_id=actor_session_id,
        )
        self.actor_id = actor_id

    def _user_read(self, user: User) -> AdminUserRead:
        return AdminUserRead(
            id=user.id,
            username=user.username,
            display_name=user.display_name,
            email=user.email,
            avatar=user.avatar,
            is_active=user.is_active,
            created_at=user.created_at,
            updated_at=user.updated_at,
            deleted_at=user.deleted_at,
            deleted_by_id=user.deleted_by_id,
            deleted_by_type=user.deleted_by_type,
            deletion_reason=user.deletion_reason,
            can_restore=user.deleted_at is not None,
        )

    async def list_users(
        self,
        *,
        page: int,
        page_size: int,
        search: str | None,
        lifecycle: Literal["all", "active", "inactive", "deleted"],
    ) -> UserPage:
        items, total = await self.users.list_users(
            page=page,
            page_size=page_size,
            search=search,
            lifecycle=lifecycle,
        )
        return UserPage.create(
            items=[self._user_read(item) for item in items],
            page=page,
            page_size=page_size,
            total=total,
        )

    async def get_user(self, user_id: uuid.UUID) -> User:
        user = await self.users.get(user_id)
        if user is None or user.deleted_at is not None:
            raise AppException(status_code=404, code=ErrorCode.USER_NOT_FOUND, message="用户不存在")
        return user

    async def create_user(self, payload: AdminUserCreateIn) -> AdminUserRead:
        password_hash = await self.password_manager.hash(payload.initial_password)
        user_id = new_uuid7()

        async def operation() -> User:
            if await self.users.get_by_username(payload.username) is not None:
                raise AppException(status_code=409, code=ErrorCode.STATE_CONFLICT, message="用户名已被使用")
            if payload.email and await self.users.get_by_email(payload.email) is not None:
                raise AppException(status_code=409, code=ErrorCode.STATE_CONFLICT, message="邮箱已被使用")
            user = User(
                id=user_id,
                username=payload.username,
                email=payload.email,
                display_name=payload.display_name,
                password_hash=password_hash,
                is_active=payload.is_active,
                credential_version=1,
                deleted_at=None,
            )
            self.users.add(user)
            return user

        try:
            user = await self.audit.execute(
                action="users:create",
                target_type="user",
                target_id=user_id,
                changed_fields={
                    "created": True,
                    "is_active": payload.is_active,
                    "has_display_name": bool(payload.display_name),
                    "has_email": payload.email is not None,
                },
                operation=operation,
            )
        except IntegrityError as exc:
            raise AppException(
                status_code=409,
                code=ErrorCode.STATE_CONFLICT,
                message="用户名或邮箱已被使用",
            ) from exc
        return self._user_read(user)

    async def update_user(self, user_id: uuid.UUID, payload: UserUpdateIn) -> User:
        async def operation() -> User:
            user = await self.users.get(user_id, for_update=True)
            if user is None or user.deleted_at is not None:
                raise AppException(status_code=404, code=ErrorCode.USER_NOT_FOUND, message="用户不存在")
            if "email" in payload.model_fields_set and payload.email:
                existing = await self.users.get_by_email(payload.email)
                if existing is not None and existing.id != user.id:
                    raise AppException(status_code=409, code=ErrorCode.STATE_CONFLICT, message="邮箱已被使用")
            if "display_name" in payload.model_fields_set:
                user.display_name = payload.display_name.strip() if payload.display_name else None
            if "email" in payload.model_fields_set:
                user.email = payload.email
            return user

        return await self.audit.execute(
            action="users:update",
            target_type="user",
            target_id=user_id,
            changed_fields={"fields": sorted(payload.model_fields_set)},
            operation=operation,
        )

    async def set_user_status(self, user_id: uuid.UUID, payload: StatusUpdateIn) -> User:
        async def operation() -> User:
            user = await self.users.get(user_id, for_update=True)
            if user is None or user.deleted_at is not None:
                raise AppException(status_code=404, code=ErrorCode.USER_NOT_FOUND, message="用户不存在")
            if user.is_active != payload.is_active:
                user.is_active = payload.is_active
                user.credential_version += 1
                await self.sessions.revoke_web_for_user(user.id, reason="account_status_changed")
            return user

        return await self.audit.execute(
            action="users:status:update",
            target_type="user",
            target_id=user_id,
            changed_fields={"is_active": payload.is_active},
            operation=operation,
        )

    async def set_user_status_bulk(self, payload: UserBulkStatusUpdateIn) -> BatchActionResult:
        async def operation() -> BatchActionResult:
            users = await self.users.get_many(payload.user_ids, for_update=True)
            if len(users) != len(payload.user_ids) or any(user.deleted_at is not None for user in users):
                raise AppException(
                    status_code=404,
                    code=ErrorCode.USER_NOT_FOUND,
                    message="一个或多个用户不存在",
                )
            for user in users:
                if user.is_active == payload.is_active:
                    continue
                user.is_active = payload.is_active
                user.credential_version += 1
                await self.sessions.revoke_web_for_user(user.id, reason="account_status_changed")
            return BatchActionResult(completed_count=len(users), target_ids=[user.id for user in users])

        return await self.audit.execute(
            action="users:status:update-bulk",
            target_type="user_batch",
            target_id=None,
            changed_fields={
                "user_ids": [str(user_id) for user_id in payload.user_ids],
                "is_active": payload.is_active,
            },
            operation=operation,
        )

    async def delete_users_bulk(self, payload: UserBulkDeleteIn) -> BatchActionResult:
        async def operation() -> BatchActionResult:
            users = await self.users.get_many(payload.user_ids, for_update=True)
            if len(users) != len(payload.user_ids) or any(user.deleted_at is not None for user in users):
                raise AppException(
                    status_code=404,
                    code=ErrorCode.USER_NOT_FOUND,
                    message="一个或多个用户不存在",
                )
            deleted_at = datetime.now(UTC)
            for user in users:
                user.is_active = False
                user.credential_version += 1
                user.deleted_at = deleted_at
                user.deleted_by_id = self.actor_id
                user.deleted_by_type = "admin"
                user.deletion_reason = payload.deletion_reason
                await self.sessions.revoke_web_for_user(user.id, reason="account_deleted_by_admin")
            return BatchActionResult(completed_count=len(users), target_ids=[user.id for user in users])

        return await self.audit.execute(
            action="users:delete-bulk",
            target_type="user_batch",
            target_id=None,
            changed_fields={
                "user_ids": [str(user_id) for user_id in payload.user_ids],
                "deleted": True,
                "deletion_reason": payload.deletion_reason,
            },
            operation=operation,
        )

    def _validate_user_restore(self, user: User) -> None:
        if user.deleted_at is None:
            raise AppException(status_code=409, code=ErrorCode.STATE_CONFLICT, message="用户未处于回收站")

    async def restore_user(self, user_id: uuid.UUID) -> AdminUserRead:
        async def operation() -> AdminUserRead:
            user = await self.users.get(user_id, for_update=True)
            if user is None:
                raise AppException(status_code=404, code=ErrorCode.USER_NOT_FOUND, message="用户不存在")
            self._validate_user_restore(user)
            user.deleted_at = None
            user.deleted_by_id = None
            user.deleted_by_type = None
            user.deletion_reason = None
            user.is_active = False
            user.credential_version += 1
            await self.sessions.revoke_web_for_user(user.id, reason="account_restored_by_admin")
            return self._user_read(user)

        return await self.audit.execute(
            action="users:restore",
            target_type="user",
            target_id=user_id,
            changed_fields={"restored": True, "is_active": False},
            operation=operation,
        )

    async def restore_users_bulk(self, payload: UserRestoreBatchIn) -> BatchActionResult:
        async def operation() -> BatchActionResult:
            users = await self.users.get_many(payload.user_ids, for_update=True)
            if len(users) != len(payload.user_ids):
                raise AppException(status_code=404, code=ErrorCode.USER_NOT_FOUND, message="一个或多个用户不存在")
            for user in users:
                self._validate_user_restore(user)
            for user in users:
                user.deleted_at = None
                user.deleted_by_id = None
                user.deleted_by_type = None
                user.deletion_reason = None
                user.is_active = False
                user.credential_version += 1
                await self.sessions.revoke_web_for_user(user.id, reason="account_restored_by_admin")
            return BatchActionResult(completed_count=len(users), target_ids=[user.id for user in users])

        return await self.audit.execute(
            action="users:restore-bulk",
            target_type="user_batch",
            target_id=None,
            changed_fields={
                "user_ids": [str(user_id) for user_id in payload.user_ids],
                "restored": True,
                "is_active": False,
            },
            operation=operation,
        )

    async def reset_user_password(self, user_id: uuid.UUID, payload: PasswordResetIn) -> None:
        password_hash = await self.password_manager.hash(payload.new_password)

        async def operation() -> None:
            user = await self.users.get(user_id, for_update=True)
            if user is None or user.deleted_at is not None:
                raise AppException(status_code=404, code=ErrorCode.USER_NOT_FOUND, message="用户不存在")
            user.password_hash = password_hash
            user.credential_version += 1
            await self.sessions.revoke_web_for_user(user.id, reason="password_reset")

        await self.audit.execute(
            action="users:credentials:reset",
            target_type="user",
            target_id=user_id,
            changed_fields={"password": "reset"},
            operation=operation,
        )

    async def list_user_sessions(
        self, user_id: uuid.UUID, *, page: int, page_size: int
    ) -> tuple[list[UserSession], int]:
        await self.get_user(user_id)
        return await self.sessions.list_web(user_id, page=page, page_size=page_size)

    async def revoke_user_session(self, user_id: uuid.UUID, session_id: uuid.UUID) -> None:
        async def operation() -> None:
            target = await self.sessions.get_web_for_user(session_id, user_id)
            if target is None:
                raise AppException(status_code=404, code=ErrorCode.NOT_FOUND, message="会话不存在")
            await self.sessions.revoke_web_session(session_id, reason="admin_revoked")

        await self.audit.execute(
            action="users:sessions:revoke",
            target_type="user_session",
            target_id=session_id,
            changed_fields={"revoked": True},
            operation=operation,
        )

    async def revoke_all_user_sessions(self, user_id: uuid.UUID) -> None:
        async def operation() -> None:
            if await self.users.get(user_id) is None:
                raise AppException(status_code=404, code=ErrorCode.USER_NOT_FOUND, message="用户不存在")
            await self.sessions.revoke_web_for_user(user_id, reason="admin_revoked_all")

        await self.audit.execute(
            action="users:sessions:revoke-all",
            target_type="user",
            target_id=user_id,
            changed_fields={"sessions": "revoked_all"},
            operation=operation,
        )

    async def list_admins(self, *, page: int, page_size: int) -> PageResult[AdminRead]:
        items, total = await self.admins.list_admins(page=page, page_size=page_size)
        return PageResult[AdminRead].create(
            items=[admin_read(item) for item in items], page=page, page_size=page_size, total=total
        )

    async def get_admin(self, admin_id: uuid.UUID) -> Admin:
        admin = await self.admins.get(admin_id)
        if admin is None:
            raise AppException(status_code=404, code=ErrorCode.ADMIN_NOT_FOUND, message="管理员不存在")
        return admin

    async def create_admin(self, payload: AdminCreateIn) -> Admin:
        password_hash = await self.password_manager.hash(payload.initial_password)
        admin_id = new_uuid7()

        async def operation() -> Admin:
            if payload.is_superuser:
                await self._require_actor_superuser()
            if await self.admins.get_by_username(payload.username) is not None:
                raise AppException(status_code=409, code=ErrorCode.STATE_CONFLICT, message="用户名已被使用")
            roles = await self.admins.get_roles(list(dict.fromkeys(payload.role_ids)))
            if len(roles) != len(set(payload.role_ids)):
                raise AppException(status_code=422, code=ErrorCode.VALIDATION_ERROR, message="一个或多个角色无效")
            admin = Admin(
                id=admin_id,
                username=payload.username,
                display_name=payload.display_name.strip() if payload.display_name else None,
                password_hash=password_hash,
                is_active=payload.is_active,
                is_superuser=payload.is_superuser,
                credential_version=1,
            )
            admin.roles = roles
            self.admins.add(admin)
            return admin

        try:
            return await self.audit.execute(
                action="admins:create",
                target_type="admin",
                target_id=admin_id,
                changed_fields={
                    "created": True,
                    "is_active": payload.is_active,
                    "is_superuser": payload.is_superuser,
                    "role_count": len(set(payload.role_ids)),
                },
                operation=operation,
            )
        except IntegrityError as exc:
            raise AppException(status_code=409, code=ErrorCode.STATE_CONFLICT, message="用户名已被使用") from exc

    async def update_admin(self, admin_id: uuid.UUID, payload: AdminUpdateIn) -> Admin:
        async def operation() -> Admin:
            admin = await self.admins.get(admin_id, for_update=True)
            if admin is None:
                raise AppException(status_code=404, code=ErrorCode.ADMIN_NOT_FOUND, message="管理员不存在")
            await self._require_superuser_target_access(admin)
            if "display_name" in payload.model_fields_set:
                admin.display_name = payload.display_name.strip() if payload.display_name else None
            if "avatar" in payload.model_fields_set:
                admin.avatar = await resolve_admin_avatar(
                    session=self.session, settings=self.settings, avatar=payload.avatar
                )
            return admin

        return await self.audit.execute(
            action="admins:update",
            target_type="admin",
            target_id=admin_id,
            changed_fields={"fields": sorted(payload.model_fields_set)},
            operation=operation,
        )

    async def set_admin_superuser(self, admin_id: uuid.UUID, payload: AdminSuperuserUpdateIn) -> Admin:
        async def operation() -> Admin:
            await self._require_actor_superuser()
            if admin_id == self.actor_id:
                raise AppException(
                    status_code=409,
                    code=ErrorCode.STATE_CONFLICT,
                    message="不能修改自己的超级管理员状态",
                )
            admin = await self.admins.get(admin_id, for_update=True)
            if admin is None:
                raise AppException(status_code=404, code=ErrorCode.ADMIN_NOT_FOUND, message="管理员不存在")
            if admin.is_superuser and not payload.is_superuser and admin.is_active:
                await self._protect_last_superuser()
            if admin.is_superuser != payload.is_superuser:
                admin.is_superuser = payload.is_superuser
                admin.credential_version += 1
                await self.sessions.revoke_admin_for_admin(admin.id, reason="superuser_status_changed")
            return admin

        return await self.audit.execute(
            action="admins:superuser:update",
            target_type="admin",
            target_id=admin_id,
            changed_fields={"is_superuser": payload.is_superuser},
            operation=operation,
        )

    async def set_admin_status(self, admin_id: uuid.UUID, payload: StatusUpdateIn) -> Admin:
        async def operation() -> Admin:
            if admin_id == self.actor_id:
                raise AppException(status_code=409, code=ErrorCode.STATE_CONFLICT, message="不能修改自己的启用状态")
            admin = await self.admins.get(admin_id, for_update=True)
            if admin is None:
                raise AppException(status_code=404, code=ErrorCode.ADMIN_NOT_FOUND, message="管理员不存在")
            await self._require_superuser_target_access(admin)
            if admin.is_active and not payload.is_active and admin.is_superuser:
                await self._protect_last_superuser()
            if admin.is_active != payload.is_active:
                admin.is_active = payload.is_active
                admin.credential_version += 1
                await self.sessions.revoke_admin_for_admin(admin.id, reason="account_status_changed")
            return admin

        return await self.audit.execute(
            action="admins:status:update",
            target_type="admin",
            target_id=admin_id,
            changed_fields={"is_active": payload.is_active},
            operation=operation,
        )

    async def set_admin_status_bulk(self, payload: AdminBulkStatusUpdateIn) -> list[Admin]:
        async def operation() -> list[Admin]:
            if self.actor_id in payload.admin_ids:
                raise AppException(status_code=409, code=ErrorCode.STATE_CONFLICT, message="不能修改自己的启用状态")

            admins = await self.admins.get_many(payload.admin_ids, for_update=True)
            if len(admins) != len(payload.admin_ids):
                raise AppException(
                    status_code=404,
                    code=ErrorCode.ADMIN_NOT_FOUND,
                    message="一个或多个管理员不存在",
                )
            if any(admin.is_superuser for admin in admins):
                await self._require_actor_superuser()

            superusers_to_disable = sum(
                1 for admin in admins if admin.is_active and admin.is_superuser and not payload.is_active
            )
            if superusers_to_disable:
                await self._protect_superuser_reduction(superusers_to_disable)

            for admin in admins:
                if admin.is_active == payload.is_active:
                    continue
                admin.is_active = payload.is_active
                admin.credential_version += 1
                await self.sessions.revoke_admin_for_admin(admin.id, reason="account_status_changed")
            return admins

        return await self.audit.execute(
            action="admins:status:update-bulk",
            target_type="admin_batch",
            target_id=None,
            changed_fields={
                "admin_ids": [str(admin_id) for admin_id in payload.admin_ids],
                "is_active": payload.is_active,
            },
            operation=operation,
        )

    async def reset_admin_password(self, admin_id: uuid.UUID, payload: PasswordResetIn) -> None:
        password_hash = await self.password_manager.hash(payload.new_password)

        async def operation() -> None:
            if admin_id == self.actor_id:
                raise AppException(
                    status_code=409, code=ErrorCode.STATE_CONFLICT, message="请使用当前管理员修改密码接口"
                )
            admin = await self.admins.get(admin_id, for_update=True)
            if admin is None:
                raise AppException(status_code=404, code=ErrorCode.ADMIN_NOT_FOUND, message="管理员不存在")
            await self._require_superuser_target_access(admin)
            admin.password_hash = password_hash
            admin.credential_version += 1
            await self.sessions.revoke_admin_for_admin(admin.id, reason="password_reset")

        await self.audit.execute(
            action="admins:credentials:reset",
            target_type="admin",
            target_id=admin_id,
            changed_fields={"password": "reset"},
            operation=operation,
        )

    async def assign_admin_roles(self, admin_id: uuid.UUID, payload: AdminRoleAssignIn) -> Admin:
        async def operation() -> Admin:
            if admin_id == self.actor_id:
                raise AppException(status_code=409, code=ErrorCode.STATE_CONFLICT, message="不能修改自己的角色")
            admin = await self.admins.get(admin_id, for_update=True)
            if admin is None:
                raise AppException(status_code=404, code=ErrorCode.ADMIN_NOT_FOUND, message="管理员不存在")
            await self._require_superuser_target_access(admin)
            role_ids = list(dict.fromkeys(payload.role_ids))
            roles = await self.admins.get_roles(role_ids)
            if len(roles) != len(role_ids):
                raise AppException(status_code=422, code=ErrorCode.VALIDATION_ERROR, message="一个或多个角色无效")
            admin.roles = roles
            admin.credential_version += 1
            await self.sessions.revoke_admin_for_admin(admin.id, reason="roles_changed")
            return admin

        return await self.audit.execute(
            action="admins:roles:assign",
            target_type="admin",
            target_id=admin_id,
            changed_fields={"role_count": len(set(payload.role_ids))},
            operation=operation,
        )

    async def list_admin_sessions(
        self, admin_id: uuid.UUID, *, page: int, page_size: int
    ) -> tuple[list[AdminSession], int]:
        admin = await self.admins.get(admin_id)
        if admin is None:
            raise AppException(status_code=404, code=ErrorCode.ADMIN_NOT_FOUND, message="管理员不存在")
        await self._require_superuser_target_access(admin)
        return await self.sessions.list_admin(admin_id, page=page, page_size=page_size)

    async def revoke_all_admin_sessions(self, admin_id: uuid.UUID) -> None:
        async def operation() -> None:
            if admin_id == self.actor_id:
                raise AppException(status_code=409, code=ErrorCode.STATE_CONFLICT, message="不能在此处撤销自己的会话")
            admin = await self.admins.get(admin_id, for_update=True)
            if admin is None:
                raise AppException(status_code=404, code=ErrorCode.ADMIN_NOT_FOUND, message="管理员不存在")
            await self._require_superuser_target_access(admin)
            await self.sessions.revoke_admin_for_admin(admin_id, reason="admin_revoked_all")

        await self.audit.execute(
            action="admins:sessions:revoke-all",
            target_type="admin",
            target_id=admin_id,
            changed_fields={"sessions": "revoked_all"},
            operation=operation,
        )

    async def list_roles(self, *, page: int, page_size: int) -> RolePage:
        items, total = await self.admins.list_roles(page=page, page_size=page_size)
        return RolePage.create(items=[role_read(item) for item in items], page=page, page_size=page_size, total=total)

    async def get_role(self, role_id: uuid.UUID) -> Role:
        role = await self.admins.get_role(role_id)
        if role is None:
            raise AppException(status_code=404, code=ErrorCode.ROLE_NOT_FOUND, message="角色不存在")
        return role

    async def create_role(self, payload: RoleCreateIn) -> Role:
        role_id = new_uuid7()

        async def operation() -> Role:
            if await self.admins.get_role_by_code(payload.code) is not None:
                raise AppException(status_code=409, code=ErrorCode.STATE_CONFLICT, message="角色代码已被使用")
            role = Role(
                id=role_id,
                code=payload.code,
                name=payload.name.strip(),
                description=payload.description.strip() if payload.description else None,
                is_active=payload.is_active,
                permissions=[],
            )
            self.admins.add_role(role)
            return role

        return await self.audit.execute(
            action="roles:create",
            target_type="role",
            target_id=role_id,
            changed_fields={"created": True, "is_active": payload.is_active},
            operation=operation,
        )

    async def update_role(self, role_id: uuid.UUID, payload: RoleUpdateIn) -> Role:
        async def operation() -> Role:
            role = await self.admins.get_role(role_id, for_update=True)
            if role is None:
                raise AppException(status_code=404, code=ErrorCode.ROLE_NOT_FOUND, message="角色不存在")
            if "name" in payload.model_fields_set and payload.name is not None:
                role.name = payload.name.strip()
            if "description" in payload.model_fields_set:
                role.description = payload.description.strip() if payload.description else None
            security_changed = False
            if "is_active" in payload.model_fields_set and payload.is_active is not None:
                security_changed = role.is_active != payload.is_active
                role.is_active = payload.is_active
            if security_changed:
                await self._invalidate_role_admins(role.id)
            return role

        return await self.audit.execute(
            action="roles:update",
            target_type="role",
            target_id=role_id,
            changed_fields={"fields": sorted(payload.model_fields_set)},
            operation=operation,
        )

    async def set_role_status_bulk(self, payload: RoleBulkStatusUpdateIn) -> BatchActionResult:
        async def operation() -> BatchActionResult:
            roles = await self.admins.get_many_roles(payload.role_ids, for_update=True)
            if len(roles) != len(payload.role_ids):
                raise AppException(
                    status_code=404,
                    code=ErrorCode.ROLE_NOT_FOUND,
                    message="一个或多个角色不存在",
                )
            changed_role_ids: list[uuid.UUID] = []
            for role in roles:
                if role.is_active == payload.is_active:
                    continue
                role.is_active = payload.is_active
                changed_role_ids.append(role.id)
            await self._invalidate_role_admins_bulk(changed_role_ids, reason="role_status_changed")
            return BatchActionResult(completed_count=len(roles), target_ids=[role.id for role in roles])

        return await self.audit.execute(
            action="roles:status:update-bulk",
            target_type="role_batch",
            target_id=None,
            changed_fields={
                "role_ids": [str(role_id) for role_id in payload.role_ids],
                "is_active": payload.is_active,
            },
            operation=operation,
        )

    async def delete_role(self, role_id: uuid.UUID) -> None:
        async def operation() -> None:
            role = await self.admins.get_role(role_id, for_update=True)
            if role is None:
                raise AppException(status_code=404, code=ErrorCode.ROLE_NOT_FOUND, message="角色不存在")
            if await self.admins.role_admin_count(role_id) > 0:
                raise AppException(status_code=409, code=ErrorCode.STATE_CONFLICT, message="角色仍分配给管理员")
            await self.admins.delete_role(role)

        await self.audit.execute(
            action="roles:delete",
            target_type="role",
            target_id=role_id,
            changed_fields={"deleted": True},
            operation=operation,
        )

    async def delete_roles_bulk(self, payload: RoleBulkDeleteIn) -> BatchActionResult:
        async def operation() -> BatchActionResult:
            roles = await self.admins.get_many_roles(payload.role_ids, for_update=True)
            if len(roles) != len(payload.role_ids):
                raise AppException(
                    status_code=404,
                    code=ErrorCode.ROLE_NOT_FOUND,
                    message="一个或多个角色不存在",
                )
            if await self.admins.role_ids_with_admins(payload.role_ids):
                raise AppException(
                    status_code=409,
                    code=ErrorCode.STATE_CONFLICT,
                    message="一个或多个角色仍分配给管理员",
                )
            for role in roles:
                await self.admins.delete_role(role)
            return BatchActionResult(completed_count=len(roles), target_ids=[role.id for role in roles])

        return await self.audit.execute(
            action="roles:delete-bulk",
            target_type="role_batch",
            target_id=None,
            changed_fields={
                "role_ids": [str(role_id) for role_id in payload.role_ids],
                "deleted": True,
            },
            operation=operation,
        )

    async def assign_role_permissions(self, role_id: uuid.UUID, payload: RolePermissionAssignIn) -> Role:
        codes = list(dict.fromkeys(payload.permission_codes))

        async def operation() -> Role:
            if any(code not in PERMISSION_CODES for code in codes):
                raise AppException(status_code=422, code=ErrorCode.VALIDATION_ERROR, message="权限代码未知")
            if any(code not in ROLE_ASSIGNABLE_PERMISSION_CODES for code in codes):
                raise AppException(
                    status_code=422,
                    code=ErrorCode.VALIDATION_ERROR,
                    message="系统权限不能分配给普通角色",
                )
            role = await self.admins.get_role(role_id, for_update=True)
            if role is None:
                raise AppException(status_code=404, code=ErrorCode.ROLE_NOT_FOUND, message="角色不存在")
            permissions = await self.admins.get_permissions_by_codes(codes)
            if len(permissions) != len(codes):
                raise AppException(
                    status_code=409,
                    code=ErrorCode.STATE_CONFLICT,
                    message="权限目录尚未同步",
                )
            role.permissions = permissions
            await self._invalidate_role_admins(role.id)
            return role

        return await self.audit.execute(
            action="roles:permissions:assign",
            target_type="role",
            target_id=role_id,
            changed_fields={"permission_count": len(codes)},
            operation=operation,
        )

    async def list_permissions(self) -> list[PermissionRead]:
        return [
            PermissionRead(
                id=item.id,
                code=item.code,
                name=item.name,
                description=item.description,
                is_active=item.is_active,
                catalog_version=item.catalog_version,
                assignable_to_roles=item.code in ROLE_ASSIGNABLE_PERMISSION_CODES,
            )
            for item in await self.admins.list_permissions()
        ]

    async def list_login_events(self, *, page: int, page_size: int) -> LoginEventPage:
        items, total = await self.security.list_login_events(page=page, page_size=page_size)
        return LoginEventPage.create(
            items=[LoginEventRead.model_validate(item) for item in items],
            page=page,
            page_size=page_size,
            total=total,
        )

    async def list_audit_events(self, *, page: int, page_size: int) -> AuditEventPage:
        items, total = await self.security.list_audit_events(page=page, page_size=page_size)
        return AuditEventPage.create(
            items=[AuditEventRead.model_validate(item) for item in items],
            page=page,
            page_size=page_size,
            total=total,
        )

    async def list_request_logs(self, *, page: int, page_size: int) -> RequestLogPage:
        if self.settings.request_log_mode != "metadata":
            raise AppException(
                status_code=409,
                code=ErrorCode.STATE_CONFLICT,
                message="请求元数据日志功能已关闭",
            )
        items, total = await self.request_logs.list_logs(page=page, page_size=page_size)
        return RequestLogPage.create(
            items=[RequestLogRead.model_validate(item) for item in items],
            page=page,
            page_size=page_size,
            total=total,
        )

    async def _require_actor_superuser(self) -> Admin:
        actor = await self.admins.get(self.actor_id, for_update=True)
        if actor is None or not actor.is_active or not actor.is_superuser:
            raise AppException(
                status_code=403,
                code=ErrorCode.PERMISSION_DENIED,
                message="仅超级管理员可执行此操作",
            )
        return actor

    async def _require_superuser_target_access(self, admin: Admin) -> None:
        if not admin.is_superuser:
            return
        try:
            await self._require_actor_superuser()
        except AppException as exc:
            raise AppException(
                status_code=403,
                code=ErrorCode.PERMISSION_DENIED,
                message="仅超级管理员可操作超级管理员账户",
            ) from exc

    async def _protect_last_superuser(self) -> None:
        await self._protect_superuser_reduction(1)

    async def _protect_superuser_reduction(self, reduction: int) -> None:
        await self.admins.lock_active_superuser_guard()
        if await self.admins.count_active_superusers() <= reduction:
            raise AppException(
                status_code=409,
                code=ErrorCode.LAST_SUPERUSER_PROTECTED,
                message="最后一名启用的超级管理员受保护",
            )

    async def _invalidate_role_admins(self, role_id: uuid.UUID) -> None:
        for admin in await self.admins.get_admins_by_role(role_id):
            admin.credential_version += 1
            await self.sessions.revoke_admin_for_admin(admin.id, reason="role_permissions_changed")

    async def _invalidate_role_admins_bulk(self, role_ids: list[uuid.UUID], *, reason: str) -> None:
        for admin in await self.admins.get_admins_by_roles(role_ids):
            admin.credential_version += 1
            await self.sessions.revoke_admin_for_admin(admin.id, reason=reason)

    async def _read_system_telemetry_cache(self, cache_key: str) -> SystemTelemetryRead | None:
        if self.resources is None or self.resources.redis is None:
            return None
        try:
            cached_value = await self.resources.redis.get(cache_key)
            if cached_value is None:
                return None
            payload = json.loads(cached_value)
            payload["cached"] = True
            payload["source"] = "redis_cache"
            return SystemTelemetryRead.model_validate(payload)
        except (RedisError, json.JSONDecodeError, TypeError, ValidationError) as exc:
            logger.bind(cache_key=cache_key).opt(exception=exc).warning("failed to read system telemetry cache")
            return None

    async def _query_system_telemetry(self, sampled_at: datetime) -> SystemTelemetryRead:
        audit_cutoff = sampled_at - timedelta(days=self.settings.security_event_retention_days)
        statement = select(
            select(func.count()).select_from(User).where(User.deleted_at.is_(None)).scalar_subquery(),
            select(func.count()).select_from(Admin).where(Admin.is_active.is_(True)).scalar_subquery(),
            select(func.count()).select_from(Role).where(Role.is_active.is_(True)).scalar_subquery(),
            select(func.count()).select_from(Asset).scalar_subquery(),
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.occurred_at >= audit_cutoff)
            .scalar_subquery(),
        )
        try:
            async with asyncio.timeout(self.settings.dependency_timeout):
                user_count, admin_count, role_count, asset_count, audit_event_count = (
                    await self.session.execute(statement)
                ).one()
        except TimeoutError as exc:
            logger.bind(timeout_seconds=self.settings.dependency_timeout).opt(exception=exc).error(
                "system telemetry database query timed out"
            )
            return SystemTelemetryRead(
                status="unavailable",
                sampled_at=sampled_at,
                source="unavailable",
                user_count=None,
                admin_count=None,
                role_count=None,
                asset_count=None,
                audit_event_count=None,
                cached=False,
            )
        except Exception as exc:
            logger.opt(exception=exc).error("failed to query system telemetry")
            return SystemTelemetryRead(
                status="unavailable",
                sampled_at=sampled_at,
                source="unavailable",
                user_count=None,
                admin_count=None,
                role_count=None,
                asset_count=None,
                audit_event_count=None,
                cached=False,
            )

        return SystemTelemetryRead(
            status="ok",
            sampled_at=sampled_at,
            source="database",
            user_count=int(user_count),
            admin_count=int(admin_count),
            role_count=int(role_count),
            asset_count=int(asset_count),
            audit_event_count=int(audit_event_count),
            cached=False,
        )

    async def _write_system_telemetry_cache(self, cache_key: str, telemetry: SystemTelemetryRead) -> None:
        if self.resources is None or self.resources.redis is None or telemetry.status != "ok":
            return
        payload = telemetry.model_dump(mode="json", exclude={"cached", "source"})
        try:
            await self.resources.redis.setex(
                cache_key,
                _SYSTEM_TELEMETRY_TTL_SECONDS,
                json.dumps(payload),
            )
        except RedisError as exc:
            logger.bind(cache_key=cache_key).opt(exception=exc).warning("failed to write system telemetry cache")

    async def _load_system_telemetry(self, *, redis_available: bool, sampled_at: datetime) -> SystemTelemetryRead:
        cache_key = self.cache_keys.system_telemetry()
        if redis_available:
            cached = await self._read_system_telemetry_cache(cache_key)
            if cached is not None:
                return cached

        async with _SYSTEM_TELEMETRY_REFRESH_LOCK:
            if redis_available:
                cached = await self._read_system_telemetry_cache(cache_key)
                if cached is not None:
                    return cached
            telemetry = await self._query_system_telemetry(sampled_at)
            if redis_available:
                await self._write_system_telemetry_cache(cache_key, telemetry)
            return telemetry

    async def get_system_overview(self) -> SystemOverviewRead:
        now = datetime.now(UTC)
        started_at = self.started_at or now
        uptime_seconds = max(0, int((now - started_at).total_seconds()))

        # 1. 数据库探针
        db_status: Literal["ok", "unavailable", "mismatch", "timeout"] = "unavailable"
        db_latency = 0.0
        db_details = "database_check_failed"
        if self.resources is not None:
            start_db = time.perf_counter()
            db_ok, db_state = await check_database(self.resources.engine, self.settings.dependency_timeout)
            db_latency = round((time.perf_counter() - start_db) * 1000.0, 2)
            if db_ok:
                db_status = "ok"
            elif db_state == "migration_revision_mismatch":
                db_status = "mismatch"
            elif db_state == "timeout":
                db_status = "timeout"
            db_details = "migration_heads_matched" if db_ok else db_state

        # 2. Redis 探针
        redis_status: Literal["ok", "unavailable", "disabled"] = "disabled"
        redis_latency = 0.0
        redis_mode = self.settings.redis_mode
        if self.resources is not None and self.resources.redis is not None:
            start_redis = time.perf_counter()
            redis_ok = await check_redis(self.resources.redis, self.settings.dependency_timeout)
            redis_latency = round((time.perf_counter() - start_redis) * 1000.0, 2)
            redis_status = "ok" if redis_ok else "unavailable"

        # 3. 只返回可公开的存储与安全机制摘要，不把配置摘要冒充健康探针。
        storage_configuration = StorageConfigurationRead(
            driver=self.settings.upload_storage_driver,
            public_base_url=self.settings.upload_base_url,
        )
        security_configuration = SecurityConfigurationRead(
            session_isolation="separate_cookie_profiles",
            csrf_strategy="double_submit_hmac",
            refresh_rotation="single_use_rotation",
        )

        infrastructure = InfrastructureOverviewRead(
            database=DatabaseHealthRead(
                status=db_status,
                latency_ms=db_latency,
                details=db_details,
            ),
            redis=RedisHealthRead(
                status=redis_status,
                latency_ms=redis_latency,
                mode=redis_mode,
            ),
            storage=storage_configuration,
            security=security_configuration,
        )

        # 4. 业务资产遥测（Redis 缓存 120s，缓存失效时单次数据库往返精确采样）
        if db_status == "ok":
            telemetry = await self._load_system_telemetry(redis_available=redis_status == "ok", sampled_at=now)
        else:
            telemetry = SystemTelemetryRead(
                status="unavailable",
                sampled_at=now,
                source="unavailable",
                user_count=None,
                admin_count=None,
                role_count=None,
                asset_count=None,
                audit_event_count=None,
                cached=False,
            )

        # 5. 综合健康评估
        overall_status: Literal["healthy", "degraded", "unavailable"] = "healthy"
        if db_status != "ok":
            overall_status = "unavailable"
        elif redis_mode == "required" and redis_status != "ok":
            overall_status = "unavailable"
        elif telemetry.status != "ok":
            overall_status = "degraded"

        return SystemOverviewRead(
            status=overall_status,
            started_at=started_at,
            uptime_seconds=uptime_seconds,
            environment=self.settings.environment,
            release_version=self.settings.release_version or "0.1.0",
            python_version=_PYTHON_VERSION,
            fastapi_version=_FASTAPI_VERSION,
            timezone="UTC",
            cors_origin_count=len(self.settings.cors_origins),
            infrastructure=infrastructure,
            telemetry=telemetry,
        )


__all__ = ["AdminManagementService"]
