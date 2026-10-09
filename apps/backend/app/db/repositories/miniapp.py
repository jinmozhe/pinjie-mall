import hashlib
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.identity import UserExternalIdentity


class MiniappIdentityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def lock_subject(self, app_id: str, subject_id: str) -> None:
        key = int.from_bytes(hashlib.sha256(f"wechat:{app_id}:{subject_id}".encode()).digest()[:8], signed=True)
        await self.session.execute(select(func.pg_advisory_xact_lock(key)))

    async def identity(self, app_id: str, subject_id: str) -> UserExternalIdentity | None:
        return (
            await self.session.scalars(
                select(UserExternalIdentity).where(
                    UserExternalIdentity.provider == "wechat",
                    UserExternalIdentity.app_id == app_id,
                    UserExternalIdentity.subject_id == subject_id,
                )
            )
        ).one_or_none()

    def add(self, user_id: UUID, app_id: str, subject_id: str, union_id: str | None) -> None:
        self.session.add(
            UserExternalIdentity(
                user_id=user_id,
                provider="wechat",
                app_id=app_id,
                subject_id=subject_id,
                union_id=union_id,
            )
        )
