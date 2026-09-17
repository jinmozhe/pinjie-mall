from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.address import UserAddress


class AddressRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def lock_owner(self, user_id: UUID) -> None:
        await self.session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"pinjie:addresses:{user_id}"},
        )

    async def list_for_user(self, user_id: UUID) -> list[UserAddress]:
        return list(
            await self.session.scalars(
                select(UserAddress)
                .where(UserAddress.user_id == user_id)
                .order_by(UserAddress.created_at, UserAddress.id)
                .execution_options(populate_existing=True)
            )
        )

    async def get(self, user_id: UUID, address_id: UUID) -> UserAddress | None:
        return (
            await self.session.scalars(
                select(UserAddress)
                .where(UserAddress.id == address_id, UserAddress.user_id == user_id)
                .execution_options(populate_existing=True)
            )
        ).one_or_none()

    async def flush(self) -> None:
        await self.session.flush()

    async def save(self, address: UserAddress) -> None:
        self.session.add(address)
        await self.session.flush()

    async def delete(self, address: UserAddress) -> None:
        await self.session.delete(address)
        await self.session.flush()
