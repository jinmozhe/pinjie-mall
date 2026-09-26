import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.db.models import Admin, Asset, User


class AssetRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, asset: Asset) -> None:
        self._session.add(asset)

    async def get(self, asset_id: uuid.UUID, *, for_update: bool = False) -> Asset | None:
        statement = select(Asset).where(Asset.id == asset_id)
        if for_update:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def get_by_file_key(self, file_key: str, *, for_update: bool = False) -> Asset | None:
        statement = select(Asset).where(Asset.file_key == file_key)
        if for_update:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def get_many(self, asset_ids: list[uuid.UUID], *, for_update: bool = False) -> list[Asset]:
        if not asset_ids:
            return []
        statement = select(Asset).where(Asset.id.in_(asset_ids)).order_by(Asset.id)
        if for_update:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return list((await self._session.scalars(statement)).all())

    async def images_missing_metadata(self, *, asset_ids: list[uuid.UUID], limit: int) -> list[Asset]:
        statement = select(Asset).where(
            Asset.scene == "product",
            Asset.width.is_(None),
            Asset.mime_type.in_(["image/jpeg", "image/png", "image/webp"]),
        )
        if asset_ids:
            statement = statement.where(Asset.id.in_(asset_ids))
        return list(await self._session.scalars(statement.order_by(Asset.id).limit(limit)))

    async def find_duplicate(
        self,
        *,
        uploader_type: str,
        uploader_id: uuid.UUID,
        scene: str,
        file_hash: str,
    ) -> Asset | None:
        statement = select(Asset).where(
            Asset.uploader_type == uploader_type,
            Asset.uploader_id == uploader_id,
            Asset.scene == scene,
            Asset.file_hash == file_hash,
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def list(
        self,
        *,
        page: int,
        page_size: int,
        search: str | None = None,
        scene: str | None = None,
        uploader_type: str | None = None,
    ) -> tuple[list[Asset], int]:
        filters: list[ColumnElement[bool]] = []
        if search:
            filters.append(Asset.original_name.ilike(f"%{search}%"))
        if scene:
            filters.append(Asset.scene == scene)
        if uploader_type:
            filters.append(Asset.uploader_type == uploader_type)
        total = await self._session.scalar(select(func.count()).select_from(Asset).where(*filters))
        items = list(
            await self._session.scalars(
                select(Asset).where(*filters).order_by(Asset.id.desc()).offset((page - 1) * page_size).limit(page_size)
            )
        )
        return items, int(total or 0)

    async def delete(self, asset: Asset) -> None:
        await self._session.delete(asset)

    async def is_referenced_by_avatar(self, url: str) -> bool:
        user_reference = await self._session.scalar(select(User.id).where(User.avatar == url).limit(1))
        if user_reference is not None:
            return True
        admin_reference = await self._session.scalar(select(Admin.id).where(Admin.avatar == url).limit(1))
        return admin_reference is not None


__all__ = ["AssetRepository"]
