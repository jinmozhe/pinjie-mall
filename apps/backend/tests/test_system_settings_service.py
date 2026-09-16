import uuid
from dataclasses import replace
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.core.request_metadata import RequestMetadata
from app.db.models import SystemSetting
from app.domains.settings.schemas import (
    RegistrationSettingPatchIn,
    RegistrationSettingValue,
    SiteLogoValue,
    SiteSettingPatchIn,
    SiteSettingValue,
)
from app.services.security_events import AuditCoordinator
from app.services.settings_media import PreparedMediaOperation, SettingsMediaStore, StagedSiteLogo
from app.services.system_settings import SystemSettingsService, recover_settings_media
from tests.conftest import TEST_SECRETS

_DATABASE_URL = "postgresql+asyncpg://u:p@localhost:5432/app"


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        ENVIRONMENT="local",
        DATABASE_URL=_DATABASE_URL,
        SETTINGS_MEDIA_ROOT=tmp_path / "settings-media",
        **TEST_SECRETS,
    )


def _metadata() -> RequestMetadata:
    return RequestMetadata(
        request_id=str(uuid.uuid7()),
        trace_id=str(uuid.uuid7()),
        ip_address="127.0.0.1",
        user_agent_summary="pytest",
        release_version="test",
    )


def _site_value(*, logo: SiteLogoValue | None = None) -> SiteSettingValue:
    return SiteSettingValue(
        name="Pinjie",
        logo=logo,
        title="Pinjie Mall",
        keywords=["mall", "commerce"],
        description="Independent mall platform",
    )


def _setting(group: str, value: SiteSettingValue | RegistrationSettingValue, *, revision: int = 3) -> SystemSetting:
    now = datetime.now(UTC)
    return SystemSetting(
        id=uuid.uuid7(),
        setting_group=group,
        setting_value=value.model_dump(mode="json"),
        revision=revision,
        updated_by_id=None,
        created_at=now,
        updated_at=now,
    )


def _service(
    tmp_path: Path,
    *,
    repository: SimpleNamespace,
    actor_id: uuid.UUID | None = None,
    media: AsyncMock | None = None,
) -> SystemSettingsService:
    service = SystemSettingsService(
        session=AsyncMock(),
        session_factory=MagicMock(),
        settings=_settings(tmp_path),
        metadata=_metadata(),
        actor_id=actor_id,
        media=media,
    )
    service._repository = repository  # type: ignore[assignment]
    return service


async def _execute_audit_operation(_coordinator: AuditCoordinator, **kwargs):
    return await kwargs["operation"]()


def _logo() -> SiteLogoValue:
    return SiteLogoValue(
        path="site/logo.png",
        mime_type="image/png",
        file_size=128,
        sha256="a" * 64,
    )


def _staged_logo() -> StagedSiteLogo:
    return StagedSiteLogo(
        token="staged-logo",
        extension="png",
        mime_type="image/png",
        file_size=128,
        sha256="a" * 64,
    )


def _prepared(*, old_revision: int = 3, new_revision: int = 4) -> PreparedMediaOperation:
    return PreparedMediaOperation(
        operation_id="operation-id",
        kind="replace",
        manifest_path="manifest.json",
        old_revision=old_revision,
        new_revision=new_revision,
        old_logo=None,
        new_logo=_logo().model_dump(mode="json"),
        target_key="site/logo.png",
        old_files=(),
    )


@pytest.mark.asyncio
async def test_system_settings_reads_public_and_admin_views(tmp_path: Path) -> None:
    logo = _logo()
    site = _setting("site", _site_value(logo=logo), revision=7)
    registration = _setting("registration", RegistrationSettingValue(enabled=True), revision=4)
    updater_id = uuid.uuid7()
    site.updated_by_id = updater_id
    repository = SimpleNamespace(
        get=AsyncMock(side_effect=lambda group, **_kwargs: site if group == "site" else registration),
        get_admin_summary=AsyncMock(return_value=(updater_id, "Settings Admin")),
    )
    media = AsyncMock(spec=SettingsMediaStore)
    media.validate_logo.return_value = True
    service = _service(tmp_path, repository=repository, media=media)

    admin_site = await service.site_for_admin()
    profile = await service.site_profile()
    admin_registration = await service.registration_for_admin()
    registration_enabled = await service.registration_enabled(for_update=True)

    assert admin_site.logo is not None
    assert admin_site.logo.url == "/static/settings/site/logo.png?v=7"
    assert admin_site.updated_by is not None
    assert admin_site.updated_by.display_name == "Settings Admin"
    assert profile.logo_url == admin_site.logo.url
    assert profile.name == "Pinjie"
    assert admin_registration.enabled is True
    assert registration_enabled is True
    assert repository.get.await_args_list[-1].kwargs == {"for_update": True}


@pytest.mark.asyncio
async def test_system_settings_rejects_site_profile_with_missing_media(tmp_path: Path) -> None:
    site = _setting("site", _site_value(logo=_logo()), revision=7)
    repository = SimpleNamespace(get=AsyncMock(return_value=site), get_admin_summary=AsyncMock())
    media = AsyncMock(spec=SettingsMediaStore)
    media.validate_logo.return_value = False
    service = _service(tmp_path, repository=repository, media=media)

    with pytest.raises(AppException) as exc_info:
        await service.site_for_admin()

    assert exc_info.value.status_code == 503
    assert exc_info.value.code == ErrorCode.SERVICE_UNAVAILABLE


@pytest.mark.asyncio
async def test_system_settings_rejects_missing_invalid_and_failed_reads(tmp_path: Path) -> None:
    repository = SimpleNamespace(get=AsyncMock(return_value=None), get_admin_summary=AsyncMock())
    service = _service(tmp_path, repository=repository)

    with pytest.raises(AppException) as missing_exc:
        await service.site_profile()
    assert missing_exc.value.code == ErrorCode.SERVICE_UNAVAILABLE

    invalid = _setting("registration", RegistrationSettingValue(enabled=True))
    invalid.setting_value = {"enabled": "yes"}
    repository.get.return_value = invalid
    with pytest.raises(AppException) as invalid_exc:
        await service.registration_enabled()
    assert invalid_exc.value.code == ErrorCode.SERVICE_UNAVAILABLE

    repository.get.side_effect = SQLAlchemyError("database unavailable")
    with pytest.raises(AppException) as database_exc:
        await service.registration_for_admin()
    assert database_exc.value.status_code == 503


@pytest.mark.asyncio
async def test_system_settings_updates_values_and_enforces_revision(tmp_path: Path, monkeypatch) -> None:
    actor_id = uuid.uuid7()
    site = _setting("site", _site_value(), revision=3)
    registration = _setting("registration", RegistrationSettingValue(enabled=False), revision=8)
    repository = SimpleNamespace(
        get=AsyncMock(side_effect=lambda group, **_kwargs: site if group == "site" else registration),
        get_admin_summary=AsyncMock(return_value=None),
    )
    service = _service(tmp_path, repository=repository, actor_id=actor_id)
    monkeypatch.setattr(AuditCoordinator, "execute", _execute_audit_operation)

    updated_site = await service.update_site(SiteSettingPatchIn(revision=3, name="Updated Pinjie"))
    updated_registration = await service.update_registration(RegistrationSettingPatchIn(revision=8, enabled=True))

    assert updated_site.name == "Updated Pinjie"
    assert updated_site.revision == 4
    assert site.updated_by_id == actor_id
    assert updated_registration.enabled is True
    assert updated_registration.revision == 9

    unchanged_site = await service.update_site(SiteSettingPatchIn(revision=4, name="Updated Pinjie"))
    unchanged_registration = await service.update_registration(RegistrationSettingPatchIn(revision=9, enabled=True))
    assert unchanged_site.revision == 5
    assert unchanged_registration.revision == 10

    with pytest.raises(AppException) as conflict_exc:
        await service.update_site(SiteSettingPatchIn(revision=4, title="Stale update"))
    assert conflict_exc.value.code == ErrorCode.SETTINGS_REVISION_MISMATCH

    public_service = _service(tmp_path, repository=repository)
    with pytest.raises(RuntimeError, match="admin actor"):
        await public_service.update_registration(RegistrationSettingPatchIn(revision=9, enabled=False))


@pytest.mark.parametrize(
    ("storage_error", "status_code", "error_code"),
    [
        (ValueError("file_too_large"), 413, ErrorCode.ASSET_FILE_TOO_LARGE),
        (ValueError("invalid_image"), 422, ErrorCode.SETTINGS_MEDIA_INVALID),
        (OSError("storage unavailable"), 503, ErrorCode.ASSET_STORAGE_FAILED),
    ],
)
@pytest.mark.asyncio
async def test_system_settings_maps_logo_staging_failures(
    tmp_path: Path,
    storage_error: Exception,
    status_code: int,
    error_code: ErrorCode,
) -> None:
    media = AsyncMock(spec=SettingsMediaStore)
    media.stage_site_logo.side_effect = storage_error
    repository = SimpleNamespace(get=AsyncMock(), get_admin_summary=AsyncMock())
    service = _service(tmp_path, repository=repository, actor_id=uuid.uuid7(), media=media)

    with pytest.raises(AppException) as exc_info:
        await service.upload_site_logo(BytesIO(b"logo"), revision=1)

    assert exc_info.value.status_code == status_code
    assert exc_info.value.code == error_code


@pytest.mark.asyncio
async def test_system_settings_uploads_and_deletes_logo(tmp_path: Path, monkeypatch) -> None:
    actor_id = uuid.uuid7()
    site = _setting("site", _site_value(), revision=3)
    repository = SimpleNamespace(get=AsyncMock(return_value=site), get_admin_summary=AsyncMock(return_value=None))
    media = AsyncMock(spec=SettingsMediaStore)
    staged = _staged_logo()
    replacement = _prepared()
    deletion = _prepared(old_revision=4, new_revision=5)
    media.stage_site_logo.return_value = staged
    media.prepare_replace.return_value = replacement
    media.prepare_delete.return_value = deletion
    media.validate_logo.return_value = False
    service = _service(tmp_path, repository=repository, actor_id=actor_id, media=media)
    monkeypatch.setattr(AuditCoordinator, "execute", _execute_audit_operation)

    uploaded = await service.upload_site_logo(BytesIO(b"logo"), revision=3)
    assert uploaded.logo is not None
    assert uploaded.logo.url.endswith("?v=4")
    media.finalize.assert_awaited_once_with(replacement)

    media.finalize.reset_mock()
    media.finalize.side_effect = OSError("trash purge failed")
    deleted = await service.delete_site_logo(revision=4)
    assert deleted.logo is None
    assert deleted.revision == 5
    media.prepare_delete.assert_awaited_once()
    media.finalize.assert_awaited_once_with(deletion)


@pytest.mark.asyncio
async def test_system_settings_discards_staged_logo_on_revision_conflict(tmp_path: Path, monkeypatch) -> None:
    site = _setting("site", _site_value(), revision=3)
    repository = SimpleNamespace(get=AsyncMock(return_value=site), get_admin_summary=AsyncMock(return_value=None))
    media = AsyncMock(spec=SettingsMediaStore)
    staged = _staged_logo()
    media.stage_site_logo.return_value = staged
    service = _service(tmp_path, repository=repository, actor_id=uuid.uuid7(), media=media)
    monkeypatch.setattr(AuditCoordinator, "execute", _execute_audit_operation)

    with pytest.raises(AppException) as exc_info:
        await service.upload_site_logo(BytesIO(b"logo"), revision=2)

    assert exc_info.value.code == ErrorCode.SETTINGS_REVISION_MISMATCH
    media.discard.assert_awaited_once_with(staged)
    media.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_system_settings_rolls_back_prepared_logo_on_commit_failure(tmp_path: Path, monkeypatch) -> None:
    site = _setting("site", _site_value(), revision=3)
    repository = SimpleNamespace(get=AsyncMock(return_value=site), get_admin_summary=AsyncMock(return_value=None))
    media = AsyncMock(spec=SettingsMediaStore)
    staged = _staged_logo()
    prepared = _prepared()
    media.stage_site_logo.return_value = staged
    media.prepare_replace.return_value = prepared
    service = _service(tmp_path, repository=repository, actor_id=uuid.uuid7(), media=media)

    async def fail_after_operation(_coordinator: AuditCoordinator, **kwargs):
        await kwargs["operation"]()
        raise RuntimeError("database commit failed")

    monkeypatch.setattr(AuditCoordinator, "execute", fail_after_operation)

    with pytest.raises(RuntimeError, match="database commit failed"):
        await service.upload_site_logo(BytesIO(b"logo"), revision=3)

    media.rollback.assert_awaited_once_with(prepared)

    media.rollback.side_effect = OSError("rollback failed")
    site.revision = 3
    with pytest.raises(AppException) as compensation_exc:
        await service.upload_site_logo(BytesIO(b"logo"), revision=3)
    assert compensation_exc.value.code == ErrorCode.ASSET_STORAGE_FAILED


@pytest.mark.asyncio
async def test_system_settings_rolls_back_prepared_deletion_on_commit_failure(tmp_path: Path, monkeypatch) -> None:
    site = _setting("site", _site_value(logo=_logo()), revision=3)
    repository = SimpleNamespace(get=AsyncMock(return_value=site), get_admin_summary=AsyncMock(return_value=None))
    media = AsyncMock(spec=SettingsMediaStore)
    prepared = _prepared()
    media.prepare_delete.return_value = prepared
    media.validate_logo.return_value = True
    service = _service(tmp_path, repository=repository, actor_id=uuid.uuid7(), media=media)

    async def fail_after_operation(_coordinator: AuditCoordinator, **kwargs):
        await kwargs["operation"]()
        raise RuntimeError("database commit failed")

    monkeypatch.setattr(AuditCoordinator, "execute", fail_after_operation)

    with pytest.raises(RuntimeError, match="database commit failed"):
        await service.delete_site_logo(revision=3)

    media.rollback.assert_awaited_once_with(prepared)


class _SessionContext:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, *_args):
        return None


@pytest.mark.asyncio
async def test_recover_settings_media_finalizes_and_rolls_back_known_states(tmp_path: Path, monkeypatch) -> None:
    media = MagicMock(spec=SettingsMediaStore)
    media.ensure_layout = AsyncMock()
    media.finalize = AsyncMock()
    media.rollback = AsyncMock()
    manifest = tmp_path / "operation.json"
    committed = _prepared(old_revision=3, new_revision=4)
    committed = replace(committed, manifest_path=str(manifest), new_logo=None, target_key=None)
    media.pending_manifests.return_value = [manifest]
    media.load_manifest.return_value = committed
    setting = _setting("site", _site_value(), revision=4)
    repository = SimpleNamespace(get=AsyncMock(return_value=setting))
    monkeypatch.setattr("app.services.system_settings.SettingsMediaStore", MagicMock(return_value=media))
    monkeypatch.setattr("app.services.system_settings.SystemSettingRepository", MagicMock(return_value=repository))
    session_factory = MagicMock(return_value=_SessionContext())

    await recover_settings_media(session_factory=session_factory, settings=_settings(tmp_path))
    media.finalize.assert_awaited_once_with(committed)

    media.finalize.reset_mock()
    setting.revision = committed.old_revision
    await recover_settings_media(session_factory=session_factory, settings=_settings(tmp_path))
    media.rollback.assert_awaited_once_with(committed)


@pytest.mark.asyncio
async def test_recover_settings_media_rejects_unknown_database_state(tmp_path: Path, monkeypatch) -> None:
    media = MagicMock(spec=SettingsMediaStore)
    media.ensure_layout = AsyncMock()
    media.finalize = AsyncMock()
    media.rollback = AsyncMock()
    manifest = tmp_path / "operation.json"
    operation = _prepared(old_revision=3, new_revision=4)
    media.pending_manifests.return_value = [manifest]
    media.load_manifest.return_value = operation
    repository = SimpleNamespace(get=AsyncMock(return_value=_setting("site", _site_value(), revision=99)))
    monkeypatch.setattr("app.services.system_settings.SettingsMediaStore", MagicMock(return_value=media))
    monkeypatch.setattr("app.services.system_settings.SystemSettingRepository", MagicMock(return_value=repository))

    with pytest.raises(RuntimeError, match="settings media recovery failed"):
        await recover_settings_media(
            session_factory=MagicMock(return_value=_SessionContext()),
            settings=_settings(tmp_path),
        )


@pytest.mark.parametrize("failure", ["missing_setting", "invalid_committed_logo"])
@pytest.mark.asyncio
async def test_recover_settings_media_rejects_incomplete_committed_state(
    tmp_path: Path,
    monkeypatch,
    failure: str,
) -> None:
    media = MagicMock(spec=SettingsMediaStore)
    media.ensure_layout = AsyncMock()
    media.validate_logo = AsyncMock(return_value=False)
    manifest = tmp_path / "operation.json"
    operation = _prepared(old_revision=3, new_revision=4)
    media.pending_manifests.return_value = [manifest]
    media.load_manifest.return_value = operation
    setting = _setting("site", _site_value(logo=_logo()), revision=4)
    repository = SimpleNamespace(get=AsyncMock(return_value=None if failure == "missing_setting" else setting))
    monkeypatch.setattr("app.services.system_settings.SettingsMediaStore", MagicMock(return_value=media))
    monkeypatch.setattr("app.services.system_settings.SystemSettingRepository", MagicMock(return_value=repository))

    with pytest.raises(RuntimeError, match="settings media recovery failed"):
        await recover_settings_media(
            session_factory=MagicMock(return_value=_SessionContext()),
            settings=_settings(tmp_path),
        )
