from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import BinaryIO, TypeVar

from loguru import logger
from pydantic import BaseModel, ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.core.request_metadata import RequestMetadata
from app.db.models import SystemSetting
from app.db.repositories import SystemSettingRepository
from app.domains.settings.schemas import (
    AdminRegistrationSettingRead,
    AdminSiteSettingRead,
    AdminSummaryRead,
    RegistrationSettingPatchIn,
    RegistrationSettingValue,
    SiteLogoRead,
    SiteLogoValue,
    SiteProfileRead,
    SiteSettingPatchIn,
    SiteSettingValue,
)
from app.services.security_events import AuditCoordinator
from app.services.settings_media import PreparedMediaOperation, SettingsMediaStore, StagedSiteLogo

SettingSchema = TypeVar("SettingSchema", bound=BaseModel)
ResultSchema = TypeVar("ResultSchema")


class SystemSettingsService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
        metadata: RequestMetadata,
        actor_id: uuid.UUID | None = None,
        media: SettingsMediaStore | None = None,
    ) -> None:
        self._session = session
        self._session_factory = session_factory
        self._settings = settings
        self._metadata = metadata
        self._actor_id = actor_id
        self._repository = SystemSettingRepository(session)
        self._media = media or SettingsMediaStore(settings.settings_media_root)

    async def site_for_admin(self) -> AdminSiteSettingRead:
        setting, value = await self._read("site", SiteSettingValue)
        await self._require_valid_media(value.logo)
        return await self._admin_site(setting, value)

    async def registration_for_admin(self) -> AdminRegistrationSettingRead:
        setting, value = await self._read("registration", RegistrationSettingValue)
        return await self._admin_registration(setting, value)

    async def site_profile(self) -> SiteProfileRead:
        setting, value = await self._read("site", SiteSettingValue)
        await self._require_valid_media(value.logo)
        return SiteProfileRead(
            name=value.name,
            logo_url=self._logo_url(value.logo, setting.revision) if value.logo is not None else None,
            title=value.title,
            keywords=value.keywords,
            description=value.description,
        )

    async def registration_enabled(self, *, for_update: bool = False) -> bool:
        _, value = await self._read("registration", RegistrationSettingValue, for_update=for_update)
        return value.enabled

    async def update_site(self, payload: SiteSettingPatchIn) -> AdminSiteSettingRead:
        actor_id = self._require_actor()
        changed_fields: dict[str, object] = {}

        async def operation() -> AdminSiteSettingRead:
            setting, current = await self._read("site", SiteSettingValue, for_update=True)
            self._check_revision(setting, payload.revision)
            updates = payload.model_dump(exclude_unset=True, exclude={"revision"})
            merged = SiteSettingValue.model_validate({**current.model_dump(mode="python"), **updates})
            for field, new_value in updates.items():
                old_value = getattr(current, field)
                if old_value != new_value:
                    changed_fields[field] = {"old": old_value, "new": new_value}
            self._apply(setting, merged, actor_id)
            return await self._admin_site(setting, merged)

        return await self._audit("settings.site.update", "system_setting", changed_fields, operation)

    async def update_registration(self, payload: RegistrationSettingPatchIn) -> AdminRegistrationSettingRead:
        actor_id = self._require_actor()
        changed_fields: dict[str, object] = {}

        async def operation() -> AdminRegistrationSettingRead:
            setting, current = await self._read("registration", RegistrationSettingValue, for_update=True)
            self._check_revision(setting, payload.revision)
            value = RegistrationSettingValue(enabled=payload.enabled)
            if current.enabled != value.enabled:
                changed_fields["enabled"] = {"old": current.enabled, "new": value.enabled}
            self._apply(setting, value, actor_id)
            return await self._admin_registration(setting, value)

        return await self._audit("settings.registration.update", "system_setting", changed_fields, operation)

    async def upload_site_logo(self, source: BinaryIO, *, revision: int) -> AdminSiteSettingRead:
        actor_id = self._require_actor()
        staged = await self._stage_logo(source)
        prepared: PreparedMediaOperation | None = None
        changed_fields: dict[str, object] = {}

        async def operation() -> AdminSiteSettingRead:
            nonlocal prepared
            setting, current = await self._read("site", SiteSettingValue, for_update=True)
            self._check_revision(setting, revision)
            prepared = await self._media.prepare_replace(
                staged=staged,
                old_logo=current.logo,
                old_revision=setting.revision,
                new_revision=setting.revision + 1,
            )
            if prepared.new_logo is None:
                raise RuntimeError("prepared logo replacement is missing its target value")
            new_logo = SiteLogoValue.model_validate(prepared.new_logo)
            changed_fields["logo"] = {
                "old": current.logo.model_dump(mode="json") if current.logo is not None else None,
                "new": new_logo.model_dump(mode="json"),
            }
            value = current.model_copy(update={"logo": new_logo})
            self._apply(setting, value, actor_id)
            return await self._admin_site(setting, value)

        try:
            result = await self._audit("settings.site.logo.update", "system_setting", changed_fields, operation)
        except BaseException as exc:
            await self._compensate(prepared, staged, exc)
            raise
        await self._finalize(prepared)
        return result

    async def delete_site_logo(self, *, revision: int) -> AdminSiteSettingRead:
        actor_id = self._require_actor()
        prepared: PreparedMediaOperation | None = None
        changed_fields: dict[str, object] = {}

        async def operation() -> AdminSiteSettingRead:
            nonlocal prepared
            setting, current = await self._read("site", SiteSettingValue, for_update=True)
            self._check_revision(setting, revision)
            prepared = await self._media.prepare_delete(
                old_logo=current.logo,
                old_revision=setting.revision,
                new_revision=setting.revision + 1,
            )
            changed_fields["logo"] = {
                "old": current.logo.model_dump(mode="json") if current.logo is not None else None,
                "new": None,
                "repair_missing_media": current.logo is not None and not await self._media.validate_logo(current.logo),
            }
            value = current.model_copy(update={"logo": None})
            self._apply(setting, value, actor_id)
            return await self._admin_site(setting, value)

        try:
            result = await self._audit("settings.site.logo.delete", "system_setting", changed_fields, operation)
        except BaseException as exc:
            await self._compensate(prepared, None, exc)
            raise
        await self._finalize(prepared)
        return result

    async def _read(
        self,
        group: str,
        schema: type[SettingSchema],
        *,
        for_update: bool = False,
    ) -> tuple[SystemSetting, SettingSchema]:
        try:
            setting = await self._repository.get(group, for_update=for_update)
            if setting is None:
                raise AppException(status_code=503, code=ErrorCode.SERVICE_UNAVAILABLE, message="系统设置暂时不可用")
            return setting, schema.model_validate(setting.setting_value)
        except AppException:
            raise
        except (SQLAlchemyError, ValidationError, TypeError) as exc:
            logger.bind(setting_group=group).opt(exception=exc).error("failed to read system setting")
            raise AppException(
                status_code=503, code=ErrorCode.SERVICE_UNAVAILABLE, message="系统设置暂时不可用"
            ) from exc

    def _apply(
        self, setting: SystemSetting, value: SiteSettingValue | RegistrationSettingValue, actor_id: uuid.UUID
    ) -> None:
        setting.setting_value = value.model_dump(mode="json")
        setting.revision += 1
        setting.updated_by_id = actor_id
        setting.updated_at = datetime.now(UTC)

    @staticmethod
    def _check_revision(setting: SystemSetting, revision: int) -> None:
        if setting.revision != revision:
            raise AppException(
                status_code=412,
                code=ErrorCode.SETTINGS_REVISION_MISMATCH,
                message="设置已被其他管理员修改，请重新加载",
            )

    async def _admin_summary(self, admin_id: uuid.UUID | None) -> AdminSummaryRead | None:
        summary = await self._repository.get_admin_summary(admin_id)
        return AdminSummaryRead(id=summary[0], display_name=summary[1]) if summary is not None else None

    async def _admin_site(self, setting: SystemSetting, value: SiteSettingValue) -> AdminSiteSettingRead:
        return AdminSiteSettingRead(
            name=value.name,
            logo=(
                SiteLogoRead(
                    url=self._logo_url(value.logo, setting.revision),
                    mime_type=value.logo.mime_type,
                    file_size=value.logo.file_size,
                )
                if value.logo is not None
                else None
            ),
            title=value.title,
            keywords=value.keywords,
            description=value.description,
            revision=setting.revision,
            updated_at=setting.updated_at,
            updated_by=await self._admin_summary(setting.updated_by_id),
        )

    async def _admin_registration(
        self, setting: SystemSetting, value: RegistrationSettingValue
    ) -> AdminRegistrationSettingRead:
        return AdminRegistrationSettingRead(
            enabled=value.enabled,
            revision=setting.revision,
            updated_at=setting.updated_at,
            updated_by=await self._admin_summary(setting.updated_by_id),
        )

    def _logo_url(self, logo: SiteLogoValue, revision: int) -> str:
        return f"{self._settings.settings_media_base_url}/{logo.path}?v={revision}"

    async def _require_valid_media(self, logo: SiteLogoValue | None) -> None:
        if logo is not None and not await self._media.validate_logo(logo):
            logger.bind(file_key=logo.path).critical("site logo metadata and storage are inconsistent")
            raise AppException(status_code=503, code=ErrorCode.SERVICE_UNAVAILABLE, message="站点媒体暂时不可用")

    async def _stage_logo(self, source: BinaryIO) -> StagedSiteLogo:
        try:
            return await self._media.stage_site_logo(source)
        except ValueError as exc:
            if str(exc) == "file_too_large":
                raise AppException(
                    status_code=413, code=ErrorCode.ASSET_FILE_TOO_LARGE, message="站点 LOGO 不能超过 2 MB"
                ) from exc
            raise AppException(
                status_code=422,
                code=ErrorCode.SETTINGS_MEDIA_INVALID,
                message="站点 LOGO 必须是有效的静态 PNG、JPEG 或 WebP 图片",
            ) from exc
        except OSError as exc:
            raise AppException(
                status_code=503, code=ErrorCode.ASSET_STORAGE_FAILED, message="站点媒体存储暂时不可用"
            ) from exc

    async def _audit(
        self,
        action: str,
        target_type: str,
        changed_fields: dict[str, object],
        operation: Callable[[], Awaitable[ResultSchema]],
    ) -> ResultSchema:
        return await AuditCoordinator(
            session=self._session,
            session_factory=self._session_factory,
            actor_id=self._require_actor(),
            metadata=self._metadata,
        ).execute(
            action=action,
            target_type=target_type,
            target_id=None,
            changed_fields=changed_fields,
            operation=operation,
        )

    def _require_actor(self) -> uuid.UUID:
        # 此处 actor_id 为 None 属于调用方编程错误（未正确传入 actor），
        # 使用 RuntimeError 而非 AppException，不对外暴露为业务错误
        if self._actor_id is None:
            raise RuntimeError("an admin actor is required for system setting writes")
        return self._actor_id

    async def _compensate(
        self,
        prepared: PreparedMediaOperation | None,
        staged: StagedSiteLogo | None,
        original_exc: BaseException,
    ) -> None:
        try:
            if prepared is not None:
                await self._media.rollback(prepared)
            elif staged is not None:
                await self._media.discard(staged)
        except OSError as exc:
            logger.opt(exception=exc).critical("failed to compensate settings media operation")
            raise AppException(
                status_code=503, code=ErrorCode.ASSET_STORAGE_FAILED, message="站点媒体结果需要人工核查"
            ) from original_exc

    async def _finalize(self, prepared: PreparedMediaOperation | None) -> None:
        if prepared is None:
            return
        try:
            await self._media.finalize(prepared)
        except OSError as exc:
            logger.bind(operation_id=prepared.operation_id).opt(exception=exc).critical(
                "failed to purge committed settings media operation"
            )


async def recover_settings_media(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    media = SettingsMediaStore(settings.settings_media_root)
    await media.ensure_layout()
    for manifest_path in await asyncio.to_thread(media.pending_manifests):
        try:
            operation = await asyncio.to_thread(media.load_manifest, manifest_path)
            async with session_factory() as session:
                setting = await SystemSettingRepository(session).get("site")
                if setting is None:
                    raise RuntimeError("site setting is missing during media recovery")
                current = SiteSettingValue.model_validate(setting.setting_value)
                current_logo = current.logo.model_dump(mode="json") if current.logo is not None else None
            if setting.revision == operation.new_revision and current_logo == operation.new_logo:
                if operation.new_logo is not None:
                    logo = SiteLogoValue.model_validate(operation.new_logo)
                    if not await media.validate_logo(logo):
                        raise RuntimeError("committed site logo is missing or invalid")
                await media.finalize(operation)
            elif setting.revision == operation.old_revision and current_logo == operation.old_logo:
                await media.rollback(operation)
            else:
                raise RuntimeError("settings media operation has an unknown database state")
        except Exception as exc:
            logger.bind(manifest=str(manifest_path)).opt(exception=exc).critical(
                "settings media recovery requires manual intervention"
            )
            raise RuntimeError("settings media recovery failed") from exc


__all__ = ["SystemSettingsService", "recover_settings_media"]
