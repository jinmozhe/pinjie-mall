from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.asset import Asset
from app.db.models.identity import Admin, User
from app.db.models.product import ProductImage
from app.db.repositories.identity import AdminRepository


class CommerceAccessRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_admin_for_update(self, actor_id: UUID) -> Admin | None:
        return await AdminRepository(self.session).get(actor_id, for_update=True)

    async def get_user_for_update(self, user_id: UUID) -> User | None:
        return (
            await self.session.scalars(
                select(User)
                .where(User.id == user_id)
                # NO KEY UPDATE 串行用户状态写入，同时允许佣金等表的外键 KEY SHARE 检查。
                .with_for_update(key_share=True)
                .execution_options(populate_existing=True)
            )
        ).one_or_none()

    async def get_images_for_update(self, asset_ids: list[UUID]) -> list[Asset]:
        if not asset_ids:
            return []
        return list(
            await self.session.scalars(
                select(Asset)
                .where(Asset.id.in_(asset_ids))
                .order_by(Asset.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        )

    async def asset_is_product_image(self, asset_id: UUID) -> bool:
        return (
            await self.session.scalar(select(ProductImage.product_id).where(ProductImage.asset_id == asset_id).limit(1))
            is not None
        )
