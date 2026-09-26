from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.repositories.asset import AssetRepository
from app.db.transaction import transaction_scope
from app.services.storage import StorageProvider


@dataclass(frozen=True, slots=True)
class BackfillResult:
    asset_id: UUID
    status: str


class AssetImageBackfill:
    def __init__(self, factory: async_sessionmaker[AsyncSession], storage: StorageProvider) -> None:
        self._factory = factory
        self._storage = storage

    async def run_one(self, asset_id: UUID, *, apply: bool) -> BackfillResult:
        async with self._factory() as session:
            asset = await AssetRepository(session).get(asset_id)
            if asset is None:
                return BackfillResult(asset_id, "missing")
            if asset.scene != "product" or asset.storage_driver != self._storage.driver:
                return BackfillResult(asset_id, "unsupported")
            if asset.width is not None:
                return BackfillResult(asset_id, "already_complete")
            snapshot = (asset.file_key, asset.file_hash, asset.file_size, asset.mime_type)
        key, digest, size, mime_type = snapshot
        if size > 10 * 1024 * 1024:
            return BackfillResult(asset_id, "file_too_large")
        try:
            metadata = await self._storage.inspect_image(
                key,
                expected_hash=digest,
                mime_type=mime_type,
                max_bytes=size,
            )
        except FileNotFoundError:
            return BackfillResult(asset_id, "file_missing")
        except ValueError as exc:
            if str(exc) == "image_decode_busy":
                return BackfillResult(asset_id, "storage_busy")
            return BackfillResult(asset_id, "invalid_image_or_hash")
        except OSError:
            return BackfillResult(asset_id, "storage_failed")
        if not apply:
            return BackfillResult(asset_id, "ready")
        async with self._factory() as session, transaction_scope(session):
            current = await AssetRepository(session).get(asset_id, for_update=True)
            if (
                current is None
                or (current.file_key, current.file_hash, current.file_size, current.mime_type) != snapshot
                or current.width is not None
            ):
                return BackfillResult(asset_id, "conflict")
            if current.scene != "product" or current.storage_driver != self._storage.driver:
                return BackfillResult(asset_id, "conflict")
            # The asset lock excludes the controlled deletion workflow while publishing metadata.
            if not await self._storage.exists(key):
                return BackfillResult(asset_id, "file_missing")
            current.width, current.height, current.frame_count = metadata.width, metadata.height, metadata.frame_count
        return BackfillResult(asset_id, "updated")
