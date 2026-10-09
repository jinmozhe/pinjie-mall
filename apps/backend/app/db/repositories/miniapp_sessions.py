"""Owner- and profile-scoped session persistence; transaction belongs to the caller."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.db.models import UserSession


def miniapp_session_filters(user_id: UUID) -> tuple[ColumnElement[bool], ...]:
    return (
        UserSession.user_id == user_id,
        UserSession.credential_profile == "miniapp_bearer",
        UserSession.client_id == "pinjie-miniapp",
        UserSession.csrf_digest.is_(None),
    )


class MiniappSessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def page(self, user_id: UUID, page: int, page_size: int) -> tuple[list[UserSession], int]:
        filters = miniapp_session_filters(user_id)
        total = (await self.session.execute(select(func.count()).select_from(UserSession).where(*filters))).scalar_one()
        rows = await self.session.scalars(
            select(UserSession)
            .where(*filters)
            .order_by(UserSession.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(rows), total

    async def active_others(self, user_id: UUID, current_id: UUID, now: datetime) -> tuple[list[UUID], int]:
        filters = (
            *miniapp_session_filters(user_id),
            UserSession.id != current_id,
            UserSession.revoked_at.is_(None),
            UserSession.idle_expires_at > now,
            UserSession.absolute_expires_at > now,
        )
        total = (await self.session.execute(select(func.count()).select_from(UserSession).where(*filters))).scalar_one()
        ids = await self.session.scalars(
            select(UserSession.id).where(*filters).order_by(UserSession.id.desc()).limit(100)
        )
        return list(ids), total

    async def targets(self, user_id: UUID, ids: list[UUID], *, for_update: bool = False) -> list[UserSession]:
        stmt = (
            select(UserSession)
            .where(*miniapp_session_filters(user_id), UserSession.id.in_(ids))
            .order_by(UserSession.id)
        )
        if for_update:
            stmt = stmt.with_for_update().execution_options(populate_existing=True)
        return list(await self.session.scalars(stmt))
