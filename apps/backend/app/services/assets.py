from __future__ import annotations

import builtins
import posixpath
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import BinaryIO
from urllib.parse import unquote, urlsplit

from loguru import logger
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.core.identifiers import new_uuid7
from app.core.request_metadata import RequestMetadata
from app.db.models import Asset
from app.db.repositories import AssetRepository
from app.db.repositories.commerce_access import CommerceAccessRepository
from app.db.transaction import transaction_scope
from app.domains.assets.schemas import (
    AssetBulkDeleteResult,
    AssetPage,
    AssetRead,
    UploaderType,
    UploadScene,
)
from app.services.security_events import AuditCoordinator
from app.services.storage import StagedDeletion, StagedFile, StorageProvider


@dataclass(frozen=True, slots=True)
class AssetUploader:
    type: UploaderType
    id: uuid.UUID


@dataclass(frozen=True, slots=True)
class ScenePolicy:
    max_bytes: int
    extensions: frozenset[str]
    mime_types: frozenset[str]


_IMAGE_MIMES = frozenset({"image/jpeg", "image/png", "image/webp"})
_SCENE_POLICIES = {
    UploadScene.AVATAR: ScenePolicy(2 * 1024 * 1024, frozenset({"jpg", "jpeg", "png", "webp"}), _IMAGE_MIMES),
    UploadScene.ARTICLE: ScenePolicy(
        5 * 1024 * 1024,
        frozenset({"jpg", "jpeg", "png", "webp", "gif"}),
        _IMAGE_MIMES | {"image/gif"},
    ),
    UploadScene.PRODUCT: ScenePolicy(10 * 1024 * 1024, frozenset({"jpg", "jpeg", "png", "webp"}), _IMAGE_MIMES),
    UploadScene.DOCUMENT: ScenePolicy(
        30 * 1024 * 1024,
        frozenset({"pdf", "doc", "docx", "xls", "xlsx"}),
        frozenset(
            {
                "application/pdf",
                "application/msword",
                "application/vnd.ms-excel",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            }
        ),
    ),
}
_USER_SCENES = frozenset({UploadScene.AVATAR, UploadScene.ATTACHMENT, UploadScene.TEMP})


class AssetService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
        storage: StorageProvider,
        metadata: RequestMetadata,
    ) -> None:
        self._session = session
        self._session_factory = session_factory
        self._settings = settings
        self._storage = storage
        self._metadata = metadata
        self._assets = AssetRepository(session)

    async def upload(
        self,
        *,
        source: BinaryIO,
        original_name: str,
        scene: UploadScene,
        uploader: AssetUploader,
    ) -> AssetRead:
        if uploader.type == UploaderType.USER and scene not in _USER_SCENES:
            raise AppException(status_code=403, code=ErrorCode.PERMISSION_DENIED, message="当前用户无权使用该上传场景")
        safe_name, extension = self._safe_filename(original_name)
        policy = self._policy(scene)
        if extension not in policy.extensions or extension not in self._settings.allowed_upload_extensions:
            raise AppException(
                status_code=422,
                code=ErrorCode.ASSET_TYPE_NOT_ALLOWED,
                message="文件扩展名不在允许范围内",
            )
        max_bytes = min(policy.max_bytes, self._settings.upload_max_file_size_mb * 1024 * 1024)
        try:
            staged = await self._storage.stage(source, extension=extension, max_bytes=max_bytes)
        except ValueError as exc:
            code = ErrorCode.ASSET_FILE_TOO_LARGE if str(exc) == "file_too_large" else ErrorCode.ASSET_TYPE_NOT_ALLOWED
            message = "文件大小超过场景限制" if code == ErrorCode.ASSET_FILE_TOO_LARGE else "文件内容与声明类型不匹配"
            raise AppException(
                status_code=413 if code == ErrorCode.ASSET_FILE_TOO_LARGE else 422, code=code, message=message
            ) from exc
        except OSError as exc:
            raise AppException(
                status_code=503, code=ErrorCode.ASSET_STORAGE_FAILED, message="文件存储暂时不可用"
            ) from exc

        if staged.mime_type not in policy.mime_types:
            await self._storage.discard(staged)
            raise AppException(
                status_code=422, code=ErrorCode.ASSET_TYPE_NOT_ALLOWED, message="文件类型不适用于当前场景"
            )

        try:
            duplicate = await self._assets.find_duplicate(
                uploader_type=uploader.type.value,
                uploader_id=uploader.id,
                scene=scene.value,
                file_hash=staged.file_hash,
            )
        except SQLAlchemyError as exc:
            await self._storage.discard(staged)
            raise AppException(
                status_code=503, code=ErrorCode.SERVICE_UNAVAILABLE, message="资产服务暂时不可用"
            ) from exc
        if duplicate is not None:
            if await self._storage.exists(duplicate.file_key):
                await self._storage.discard(staged)
            else:
                await self._commit_staged(staged, duplicate.file_key)
            return AssetRead.model_validate(duplicate)

        asset_id = new_uuid7()
        date_bucket = datetime.now(UTC).strftime("%Y%m%d")
        file_key = f"{scene.value}/{date_bucket}/{staged.file_hash[:16]}_{asset_id.hex}.{extension}"
        url = f"{self._settings.upload_base_url}/{file_key}"
        asset = Asset(
            id=asset_id,
            uploader_type=uploader.type.value,
            uploader_id=uploader.id,
            storage_driver=self._storage.driver,
            file_key=file_key,
            original_name=safe_name,
            mime_type=staged.mime_type,
            file_size=staged.file_size,
            file_hash=staged.file_hash,
            url=url,
            scene=scene.value,
        )
        await self._commit_staged(staged, file_key)
        try:
            async with transaction_scope(self._session):
                self._assets.add(asset)
                await self._session.flush()
        except IntegrityError as exc:
            await self._delete_committed_file(file_key)
            duplicate = await self._assets.find_duplicate(
                uploader_type=uploader.type.value,
                uploader_id=uploader.id,
                scene=scene.value,
                file_hash=staged.file_hash,
            )
            if duplicate is not None:
                return AssetRead.model_validate(duplicate)
            raise AppException(status_code=409, code=ErrorCode.STATE_CONFLICT, message="相同资产已存在") from exc
        except SQLAlchemyError as exc:
            await self._delete_committed_file(file_key)
            raise AppException(
                status_code=503, code=ErrorCode.SERVICE_UNAVAILABLE, message="资产服务暂时不可用"
            ) from exc
        return AssetRead.model_validate(asset)

    async def list(
        self,
        *,
        page: int,
        page_size: int,
        search: str | None = None,
        scene: UploadScene | None = None,
        uploader_type: UploaderType | None = None,
    ) -> AssetPage:
        try:
            items, total = await self._assets.list(
                page=page,
                page_size=page_size,
                search=search.strip() if search and search.strip() else None,
                scene=scene.value if scene else None,
                uploader_type=uploader_type.value if uploader_type else None,
            )
        except SQLAlchemyError as exc:
            raise AppException(
                status_code=503, code=ErrorCode.SERVICE_UNAVAILABLE, message="资产服务暂时不可用"
            ) from exc
        return AssetPage.create(
            items=[AssetRead.model_validate(item) for item in items],
            page=page,
            page_size=page_size,
            total=total,
        )

    async def delete(self, *, asset_id: uuid.UUID, actor_id: uuid.UUID) -> None:
        await self._delete_many(
            asset_ids=[asset_id],
            actor_id=actor_id,
            action="asset.delete",
            target_type="asset",
            target_id=asset_id,
            missing_message="文件资产不存在",
        )

    async def delete_bulk(self, *, asset_ids: builtins.list[uuid.UUID], actor_id: uuid.UUID) -> AssetBulkDeleteResult:
        return await self._delete_many(
            asset_ids=asset_ids,
            actor_id=actor_id,
            action="assets:delete-bulk",
            target_type="asset_batch",
            target_id=None,
            missing_message="一个或多个文件资产不存在",
        )

    async def _delete_many(
        self,
        *,
        asset_ids: builtins.list[uuid.UUID],
        actor_id: uuid.UUID,
        action: str,
        target_type: str,
        target_id: uuid.UUID | None,
        missing_message: str,
    ) -> AssetBulkDeleteResult:
        deletions: builtins.list[tuple[uuid.UUID, StagedDeletion]] = []
        audit = AuditCoordinator(
            session=self._session,
            session_factory=self._session_factory,
            actor_id=actor_id,
            metadata=self._metadata,
        )

        async def operation() -> AssetBulkDeleteResult:
            assets = await self._assets.get_many(asset_ids, for_update=True)
            if len(assets) != len(asset_ids):
                raise AppException(status_code=404, code=ErrorCode.ASSET_NOT_FOUND, message=missing_message)
            # 在循环外实例化 Repository，避免每次迭代重复创建对象
            commerce_access = CommerceAccessRepository(self._session)
            for asset in assets:
                if await commerce_access.asset_is_product_image(asset.id) or await commerce_access.asset_is_brand_logo(
                    asset.id
                ):
                    raise AppException(
                        status_code=409, code=ErrorCode.STATE_CONFLICT, message="商品或品牌图片正在被使用，无法删除"
                    )
                if await self._assets.is_referenced_by_avatar(asset.url):
                    raise AppException(
                        status_code=409, code=ErrorCode.STATE_CONFLICT, message="头像资产正在被使用，无法删除"
                    )
            for asset in assets:
                try:
                    deletion = await self._storage.stage_delete(asset.file_key)
                except OSError as exc:
                    raise AppException(
                        status_code=503,
                        code=ErrorCode.ASSET_STORAGE_FAILED,
                        message="文件存储暂时不可用",
                    ) from exc
                deletions.append((asset.id, deletion))
            for asset in assets:
                await self._assets.delete(asset)
            return AssetBulkDeleteResult(
                completed_count=len(assets),
                target_ids=[asset.id for asset in assets],
            )

        try:
            result = await audit.execute(
                action=action,
                target_type=target_type,
                target_id=target_id,
                changed_fields={
                    "asset_ids": [str(current_id) for current_id in asset_ids],
                    "deleted": True,
                },
                operation=operation,
            )
        except BaseException as original_exc:
            try:
                await self._restore_deletions(deletions)
            except AppException as restore_exc:
                raise restore_exc from original_exc
            raise
        await self._purge_deletions(deletions)
        return result

    async def _restore_deletions(self, deletions: builtins.list[tuple[uuid.UUID, StagedDeletion]]) -> None:
        first_error: OSError | None = None
        for asset_id, deletion in reversed(deletions):
            try:
                await self._storage.restore(deletion)
            except OSError as exc:
                first_error = first_error or exc
                logger.bind(asset_id=str(asset_id)).opt(exception=exc).critical(
                    "failed to restore asset after database rollback"
                )
        if first_error is not None:
            raise AppException(
                status_code=503,
                code=ErrorCode.ASSET_STORAGE_FAILED,
                message="文件删除结果需要人工核查",
            ) from first_error

    async def _purge_deletions(self, deletions: builtins.list[tuple[uuid.UUID, StagedDeletion]]) -> None:
        for asset_id, deletion in deletions:
            try:
                await self._storage.purge(deletion)
            except OSError as exc:
                logger.bind(asset_id=str(asset_id)).opt(exception=exc).critical("failed to purge deleted asset trash")

    def _policy(self, scene: UploadScene) -> ScenePolicy:
        if scene in _SCENE_POLICIES:
            return _SCENE_POLICIES[scene]
        allowed = self._settings.allowed_upload_extensions
        mime_types = frozenset(
            {
                "image/jpeg",
                "image/png",
                "image/webp",
                "image/gif",
                "application/pdf",
                "application/msword",
                "application/vnd.ms-excel",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "application/zip",
            }
        )
        return ScenePolicy(self._settings.upload_max_file_size_mb * 1024 * 1024, allowed, mime_types)

    @staticmethod
    def _safe_filename(original_name: str) -> tuple[str, str]:
        name = PurePosixPath(original_name.replace("\\", "/")).name.strip()
        if not name or len(name) > 255 or "\x00" in name:
            raise AppException(status_code=422, code=ErrorCode.ASSET_TYPE_NOT_ALLOWED, message="文件名无效")
        suffix = PurePosixPath(name).suffix.lower().removeprefix(".")
        if not suffix or not suffix.isascii() or not suffix.isalnum():
            raise AppException(status_code=422, code=ErrorCode.ASSET_TYPE_NOT_ALLOWED, message="文件扩展名无效")
        return name, suffix

    async def _commit_staged(self, staged: StagedFile, file_key: str) -> None:
        try:
            await self._storage.commit(staged, file_key=file_key)
        except OSError as exc:
            await self._storage.discard(staged)
            raise AppException(
                status_code=503, code=ErrorCode.ASSET_STORAGE_FAILED, message="文件存储暂时不可用"
            ) from exc

    async def _delete_committed_file(self, file_key: str) -> None:
        try:
            deletion = await self._storage.stage_delete(file_key)
            await self._storage.purge(deletion)
        except OSError as exc:
            logger.bind(file_key=file_key).opt(exception=exc).critical("failed to compensate committed asset file")


async def resolve_admin_avatar(*, session: AsyncSession, settings: Settings, avatar: str | None) -> str | None:
    value = avatar.strip() if avatar else None
    if not value:
        return None
    try:
        parsed = urlsplit(value)
    except ValueError as exc:
        raise AppException(status_code=422, code=ErrorCode.VALIDATION_ERROR, message="头像地址无效") from exc
    if parsed.netloc or parsed.scheme:
        origins = [urlsplit(origin) for origin in settings.cors_origins]
        if not any(
            parsed.netloc.lower() == origin.netloc.lower() and (not parsed.scheme or parsed.scheme == origin.scheme)
            for origin in origins
        ):
            return value
    path = posixpath.normpath(unquote(parsed.path))
    prefix = settings.upload_base_url.rstrip("/") + "/"
    if not path.startswith(prefix):
        return value
    # The caller owns the transaction; deletion holds this same asset row lock.
    asset = await AssetRepository(session).get_by_file_key(path[len(prefix) :], for_update=True)
    if asset is None or asset.url != path:
        raise AppException(status_code=404, code=ErrorCode.ASSET_NOT_FOUND, message="头像资产不存在或已删除")
    return asset.url


__all__ = ["AssetService", "AssetUploader", "resolve_admin_avatar"]
