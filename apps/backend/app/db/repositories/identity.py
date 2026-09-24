import uuid
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.interfaces import LoaderOption
from sqlalchemy.sql.elements import ColumnElement

from app.db.models import (
    Admin,
    AdminRefreshToken,
    AdminSession,
    AuditEvent,
    Permission,
    RequestLog,
    Role,
    SecurityLoginEvent,
    User,
    UserRefreshToken,
    UserSession,
)

_SUPERUSER_GUARD_LOCK_KEY = 0x50494E4A49455355


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_username(self, username: str, *, for_update: bool = False) -> User | None:
        statement = select(User).where(User.username == username)
        if for_update:
            statement = statement.with_for_update()
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def get(self, user_id: uuid.UUID, *, for_update: bool = False) -> User | None:
        statement = select(User).where(User.id == user_id)
        if for_update:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def get_many(self, user_ids: list[uuid.UUID], *, for_update: bool = False) -> list[User]:
        if not user_ids:
            return []
        statement = select(User).where(User.id.in_(user_ids)).order_by(User.id)
        if for_update:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return list((await self.session.scalars(statement)).all())

    async def get_by_email(self, email: str) -> User | None:
        return (await self.session.execute(select(User).where(User.email == email))).scalar_one_or_none()

    def add(self, user: User) -> None:
        self.session.add(user)

    async def list_users(
        self,
        *,
        page: int,
        page_size: int,
        search: str | None = None,
        lifecycle: Literal["all", "active", "inactive", "deleted"] = "all",
    ) -> tuple[list[User], int]:
        filters: list[ColumnElement[bool]] = []
        if lifecycle == "all":
            filters.append(User.deleted_at.is_(None))
        elif lifecycle == "active":
            filters.extend((User.deleted_at.is_(None), User.is_active.is_(True)))
        elif lifecycle == "inactive":
            filters.extend((User.deleted_at.is_(None), User.is_active.is_(False)))
        elif lifecycle == "deleted":
            filters.append(User.deleted_at.is_not(None))
        if search:
            pattern = f"%{search}%"
            filters.append(
                or_(User.username.ilike(pattern), User.display_name.ilike(pattern), User.email.ilike(pattern))
            )
        total = int((await self.session.scalar(select(func.count()).select_from(User).where(*filters))) or 0)
        statement = (
            select(User).where(*filters).order_by(User.id.desc()).offset((page - 1) * page_size).limit(page_size)
        )
        return list((await self.session.scalars(statement)).all()), total


class AdminRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def _with_permissions() -> LoaderOption:
        return selectinload(Admin.roles).selectinload(Role.permissions)

    async def get_by_username(self, username: str, *, for_update: bool = False) -> Admin | None:
        statement = select(Admin).where(Admin.username == username).options(self._with_permissions())
        if for_update:
            statement = statement.with_for_update()
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def get_role_by_code(self, code: str) -> Role | None:
        statement = select(Role).where(Role.code == code).options(selectinload(Role.permissions))
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def get(self, admin_id: uuid.UUID, *, for_update: bool = False) -> Admin | None:
        statement = select(Admin).where(Admin.id == admin_id).options(self._with_permissions())
        if for_update:
            # Authentication may already have loaded this identity before a concurrent permission change.
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def get_many(self, admin_ids: list[uuid.UUID], *, for_update: bool = False) -> list[Admin]:
        if not admin_ids:
            return []
        statement = select(Admin).where(Admin.id.in_(admin_ids)).options(self._with_permissions()).order_by(Admin.id)
        if for_update:
            statement = statement.with_for_update()
        return list((await self.session.scalars(statement)).unique().all())

    def add(self, admin: Admin) -> None:
        self.session.add(admin)

    async def list_admins(self, *, page: int, page_size: int) -> tuple[list[Admin], int]:
        total = int((await self.session.scalar(select(func.count()).select_from(Admin))) or 0)
        statement = (
            select(Admin)
            .options(self._with_permissions())
            .order_by(Admin.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list((await self.session.scalars(statement)).unique().all()), total

    async def count_active_superusers(self) -> int:
        statement = (
            select(func.count()).select_from(Admin).where(Admin.is_active.is_(True), Admin.is_superuser.is_(True))
        )
        return int((await self.session.scalar(statement)) or 0)

    async def lock_active_superuser_guard(self) -> None:
        await self.session.execute(select(func.pg_advisory_xact_lock(_SUPERUSER_GUARD_LOCK_KEY)))

    async def get_roles(self, role_ids: list[uuid.UUID]) -> list[Role]:
        if not role_ids:
            return []
        return list(
            (await self.session.scalars(select(Role).where(Role.id.in_(role_ids), Role.is_active.is_(True)))).all()
        )

    async def get_admins_by_role(self, role_id: uuid.UUID) -> list[Admin]:
        from app.db.models import admin_roles

        statement = (
            select(Admin)
            .join(admin_roles, Admin.id == admin_roles.c.admin_id)
            .where(admin_roles.c.role_id == role_id)
            .options(self._with_permissions())
            .with_for_update()
        )
        return list((await self.session.scalars(statement)).unique().all())

    async def get_role(self, role_id: uuid.UUID, *, for_update: bool = False) -> Role | None:
        statement = select(Role).where(Role.id == role_id).options(selectinload(Role.permissions))
        if for_update:
            statement = statement.with_for_update()
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def get_many_roles(self, role_ids: list[uuid.UUID], *, for_update: bool = False) -> list[Role]:
        if not role_ids:
            return []
        statement = select(Role).where(Role.id.in_(role_ids)).options(selectinload(Role.permissions)).order_by(Role.id)
        if for_update:
            statement = statement.with_for_update()
        return list((await self.session.scalars(statement)).unique().all())

    async def list_roles(self, *, page: int, page_size: int) -> tuple[list[Role], int]:
        total = int((await self.session.scalar(select(func.count()).select_from(Role))) or 0)
        statement = (
            select(Role)
            .options(selectinload(Role.permissions))
            .order_by(Role.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list((await self.session.scalars(statement)).unique().all()), total

    async def get_permissions_by_codes(self, codes: list[str]) -> list[Permission]:
        if not codes:
            return []
        statement = select(Permission).where(Permission.code.in_(codes), Permission.is_active.is_(True))
        return list((await self.session.scalars(statement)).all())

    async def list_permissions(self) -> list[Permission]:
        return list((await self.session.scalars(select(Permission).order_by(Permission.code))).all())

    async def role_admin_count(self, role_id: uuid.UUID) -> int:
        from app.db.models import admin_roles

        statement = select(func.count()).select_from(admin_roles).where(admin_roles.c.role_id == role_id)
        return int((await self.session.scalar(statement)) or 0)

    async def role_ids_with_admins(self, role_ids: list[uuid.UUID]) -> set[uuid.UUID]:
        if not role_ids:
            return set()
        from app.db.models import admin_roles

        statement = select(admin_roles.c.role_id).where(admin_roles.c.role_id.in_(role_ids)).distinct()
        return set((await self.session.scalars(statement)).all())

    async def get_admins_by_roles(self, role_ids: list[uuid.UUID]) -> list[Admin]:
        if not role_ids:
            return []
        from app.db.models import admin_roles

        statement = (
            select(Admin)
            .join(admin_roles, Admin.id == admin_roles.c.admin_id)
            .where(admin_roles.c.role_id.in_(role_ids))
            .options(self._with_permissions())
            .order_by(Admin.id)
            .with_for_update()
        )
        return list((await self.session.scalars(statement)).unique().all())

    async def delete_role(self, role: Role) -> None:
        await self.session.delete(role)

    def add_role(self, role: Role) -> None:
        self.session.add(role)

    def add_permission(self, permission: Permission) -> None:
        self.session.add(permission)


class SessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add_web(self, login_session: UserSession, refresh: UserRefreshToken) -> None:
        self.session.add_all((login_session, refresh))

    def add_admin(self, login_session: AdminSession, refresh: AdminRefreshToken) -> None:
        self.session.add_all((login_session, refresh))

    async def get_web(self, session_id: uuid.UUID, *, for_update: bool = False) -> UserSession | None:
        statement = select(UserSession).where(UserSession.id == session_id).options(selectinload(UserSession.user))
        if for_update:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def get_admin(self, session_id: uuid.UUID, *, for_update: bool = False) -> AdminSession | None:
        statement = (
            select(AdminSession)
            .where(AdminSession.id == session_id)
            .options(selectinload(AdminSession.admin).selectinload(Admin.roles).selectinload(Role.permissions))
        )
        if for_update:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def get_web_for_user(self, session_id: uuid.UUID, user_id: uuid.UUID) -> UserSession | None:
        statement = select(UserSession).where(UserSession.id == session_id, UserSession.user_id == user_id)
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def get_admin_for_owner(self, session_id: uuid.UUID, admin_id: uuid.UUID) -> AdminSession | None:
        statement = select(AdminSession).where(AdminSession.id == session_id, AdminSession.admin_id == admin_id)
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def get_web_refresh_for_update(self, digest: str) -> UserRefreshToken | None:
        statement = (
            select(UserRefreshToken)
            .where(UserRefreshToken.token_digest == digest)
            .options(selectinload(UserRefreshToken.session).selectinload(UserSession.user))
            .with_for_update()
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def get_admin_refresh_for_update(self, digest: str) -> AdminRefreshToken | None:
        statement = (
            select(AdminRefreshToken)
            .where(AdminRefreshToken.token_digest == digest)
            .options(
                selectinload(AdminRefreshToken.session)
                .selectinload(AdminSession.admin)
                .selectinload(Admin.roles)
                .selectinload(Role.permissions)
            )
            .with_for_update()
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def list_web(self, user_id: uuid.UUID, *, page: int, page_size: int) -> tuple[list[UserSession], int]:
        predicate = UserSession.user_id == user_id
        total = int((await self.session.scalar(select(func.count()).select_from(UserSession).where(predicate))) or 0)
        statement = (
            select(UserSession)
            .where(predicate)
            .order_by(UserSession.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list((await self.session.scalars(statement)).all()), total

    async def list_admin(self, admin_id: uuid.UUID, *, page: int, page_size: int) -> tuple[list[AdminSession], int]:
        predicate = AdminSession.admin_id == admin_id
        total = int((await self.session.scalar(select(func.count()).select_from(AdminSession).where(predicate))) or 0)
        statement = (
            select(AdminSession)
            .where(predicate)
            .order_by(AdminSession.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list((await self.session.scalars(statement)).all()), total

    async def revoke_web_refresh_tokens(self, session_id: uuid.UUID, *, reason: str, now: datetime) -> None:
        await self.session.execute(
            update(UserRefreshToken)
            .where(UserRefreshToken.session_id == session_id, UserRefreshToken.revoked_at.is_(None))
            .values(revoked_at=now, revoke_reason=reason)
        )

    async def revoke_admin_refresh_tokens(self, session_id: uuid.UUID, *, reason: str, now: datetime) -> None:
        await self.session.execute(
            update(AdminRefreshToken)
            .where(AdminRefreshToken.session_id == session_id, AdminRefreshToken.revoked_at.is_(None))
            .values(revoked_at=now, revoke_reason=reason)
        )

    async def revoke_web_session(self, session_id: uuid.UUID, *, reason: str, now: datetime | None = None) -> bool:
        revoked_id = await self.session.scalar(
            update(UserSession)
            .where(UserSession.id == session_id, UserSession.revoked_at.is_(None))
            .values(revoked_at=now or datetime.now(UTC), revoke_reason=reason)
            .returning(UserSession.id)
        )
        return revoked_id is not None

    async def revoke_admin_session(self, session_id: uuid.UUID, *, reason: str, now: datetime | None = None) -> bool:
        revoked_id = await self.session.scalar(
            update(AdminSession)
            .where(AdminSession.id == session_id, AdminSession.revoked_at.is_(None))
            .values(revoked_at=now or datetime.now(UTC), revoke_reason=reason)
            .returning(AdminSession.id)
        )
        return revoked_id is not None

    async def revoke_web_for_user(self, user_id: uuid.UUID, *, reason: str, except_id: uuid.UUID | None = None) -> None:
        statement = update(UserSession).where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        if except_id is not None:
            statement = statement.where(UserSession.id != except_id)
        await self.session.execute(statement.values(revoked_at=datetime.now(UTC), revoke_reason=reason))

    async def revoke_admin_for_admin(
        self, admin_id: uuid.UUID, *, reason: str, except_id: uuid.UUID | None = None
    ) -> None:
        statement = update(AdminSession).where(AdminSession.admin_id == admin_id, AdminSession.revoked_at.is_(None))
        if except_id is not None:
            statement = statement.where(AdminSession.id != except_id)
        await self.session.execute(statement.values(revoked_at=datetime.now(UTC), revoke_reason=reason))


class SecurityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add_login_event(self, event: SecurityLoginEvent) -> None:
        self.session.add(event)

    def add_audit_event(self, event: AuditEvent) -> None:
        self.session.add(event)

    async def get_audit_event(self, event_id: uuid.UUID, *, for_update: bool = False) -> AuditEvent | None:
        statement = select(AuditEvent).where(AuditEvent.id == event_id)
        if for_update:
            statement = statement.with_for_update()
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def list_login_events(self, *, page: int, page_size: int) -> tuple[list[SecurityLoginEvent], int]:
        total = int((await self.session.scalar(select(func.count()).select_from(SecurityLoginEvent))) or 0)
        statement = (
            select(SecurityLoginEvent)
            .order_by(SecurityLoginEvent.occurred_at.desc(), SecurityLoginEvent.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list((await self.session.scalars(statement)).all()), total

    async def list_audit_events(self, *, page: int, page_size: int) -> tuple[list[AuditEvent], int]:
        total = int((await self.session.scalar(select(func.count()).select_from(AuditEvent))) or 0)
        statement = (
            select(AuditEvent)
            .order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list((await self.session.scalars(statement)).all()), total


class RequestLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, request_log: RequestLog) -> None:
        self.session.add(request_log)

    async def list_logs(self, *, page: int, page_size: int) -> tuple[list[RequestLog], int]:
        total = int((await self.session.scalar(select(func.count()).select_from(RequestLog))) or 0)
        statement = (
            select(RequestLog)
            .order_by(RequestLog.occurred_at.desc(), RequestLog.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list((await self.session.scalars(statement)).all()), total

    async def delete_before(self, cutoff: datetime) -> int:
        deleted_ids = list(
            (
                await self.session.scalars(
                    delete(RequestLog).where(RequestLog.occurred_at < cutoff).returning(RequestLog.id)
                )
            ).all()
        )
        return len(deleted_ids)


__all__ = ["AdminRepository", "RequestLogRepository", "SecurityRepository", "SessionRepository", "UserRepository"]
