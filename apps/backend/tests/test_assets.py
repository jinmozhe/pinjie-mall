import io
import os
import uuid
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError
from sqlalchemy import delete, select

from app.api import dependencies as api_dependencies
from app.api.dependencies import get_asset_service, get_db_session
from app.core.config import Settings
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.core.request_metadata import RequestMetadata
from app.core.resources import create_resources
from app.core.security import token_digest
from app.db.models import Asset, AuditEvent
from app.db.transaction import transaction_scope
from app.domains.assets.schemas import AssetBulkDeleteIn, AssetRead, UploaderType, UploadScene
from app.main import app
from app.services.assets import AssetService, AssetUploader
from app.services.security_events import AuditCoordinator
from app.services.storage import LocalStorageProvider, StagedDeletion
from tests.conftest import TEST_SECRETS

_PNG = b"\x89PNG\r\n\x1a\n" + b"asset-test-content"


def _zip_content(*names: str) -> bytes:
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w") as archive:
        for name in names:
            archive.writestr(name, b"test")
    return target.getvalue()


def _integration_settings(upload_root: Path) -> Settings:
    database_url = os.getenv("TEST_DATABASE_URL")
    redis_url = os.getenv("TEST_REDIS_URL")
    if not database_url:
        pytest.fail("TEST_DATABASE_URL is required for asset integration tests")
    if not redis_url:
        pytest.fail("TEST_REDIS_URL is required for asset integration tests")
    settings = Settings(
        ENVIRONMENT="test",
        DATABASE_URL=database_url,
        TEST_DATABASE_URL=database_url,
        REDIS_MODE="required",
        REDIS_URL=redis_url,
        UPLOAD_LOCAL_ROOT=upload_root,
        **{key: value for key, value in TEST_SECRETS.items() if key not in {"REDIS_MODE", "REDIS_URL"}},
    )
    settings.validate_runtime()
    return settings


def _metadata() -> RequestMetadata:
    return RequestMetadata(
        request_id=str(uuid.uuid7()),
        trace_id=str(uuid.uuid7()),
        ip_address="127.0.0.1",
        user_agent_summary="pytest",
        release_version="test",
    )


@pytest.fixture
def asset_api_service() -> AsyncMock:
    service = AsyncMock(spec=AssetService)
    now = datetime.now(UTC)
    service.upload.return_value = AssetRead(
        id=uuid.uuid7(),
        uploader_type=UploaderType.USER,
        uploader_id=uuid.uuid7(),
        storage_driver="local",
        file_key="avatar/20260825/hash_asset.png",
        original_name="avatar.png",
        mime_type="image/png",
        file_size=len(_PNG),
        file_hash="a" * 64,
        url="/static/uploads/avatar/20260825/hash_asset.png",
        scene=UploadScene.AVATAR,
        created_at=now,
        updated_at=now,
    )
    app.dependency_overrides[get_asset_service] = lambda: service
    app.dependency_overrides[get_db_session] = lambda: object()
    try:
        yield service
    finally:
        app.dependency_overrides.pop(get_asset_service, None)
        app.dependency_overrides.pop(get_db_session, None)


def _current_principal(*, admin: bool, csrf_token: str) -> SimpleNamespace:
    settings = app.state.settings
    web_secret, admin_secret, web_hmac, admin_hmac = settings.authentication_secrets()
    del web_secret, admin_secret
    principal = SimpleNamespace(id=uuid.uuid7())
    login_session = SimpleNamespace(
        csrf_digest=token_digest(csrf_token, admin_hmac if admin else web_hmac),
    )
    if admin:
        return SimpleNamespace(admin=principal, login_session=login_session, permissions=frozenset())
    return SimpleNamespace(user=principal, login_session=login_session)


def test_asset_bulk_delete_rejects_duplicate_ids() -> None:
    asset_id = uuid.uuid7()

    with pytest.raises(ValidationError):
        AssetBulkDeleteIn(asset_ids=[asset_id, asset_id])


def _asset_delete_service(*, storage: AsyncMock, assets: list[SimpleNamespace]) -> AssetService:
    service = AssetService(
        session=AsyncMock(),
        session_factory=AsyncMock(),
        settings=app.state.settings,
        storage=storage,
        metadata=_metadata(),
    )
    service._session.scalar.return_value = None
    service._assets = SimpleNamespace(  # type: ignore[assignment]
        get_many=AsyncMock(return_value=assets),
        delete=AsyncMock(),
        is_referenced_by_avatar=AsyncMock(return_value=False),
    )
    return service


async def _execute_audit_operation(_coordinator: AuditCoordinator, **kwargs):
    return await kwargs["operation"]()


@pytest.mark.asyncio
async def test_asset_bulk_delete_restores_staged_files_when_later_staging_fails(monkeypatch) -> None:
    first_id = uuid.uuid7()
    second_id = uuid.uuid7()
    first_deletion = StagedDeletion(token="trash-one", file_key="product/one.png")
    storage = AsyncMock()
    storage.stage_delete.side_effect = [first_deletion, OSError("stage failed")]
    service = _asset_delete_service(
        storage=storage,
        assets=[
            SimpleNamespace(id=first_id, file_key=first_deletion.file_key, url="/static/uploads/product/one.png"),
            SimpleNamespace(id=second_id, file_key="product/two.png", url="/static/uploads/product/two.png"),
        ],
    )
    monkeypatch.setattr(AuditCoordinator, "execute", _execute_audit_operation)

    with pytest.raises(AppException) as exc_info:
        await service.delete_bulk(asset_ids=[first_id, second_id], actor_id=uuid.uuid7())

    assert exc_info.value.code == ErrorCode.ASSET_STORAGE_FAILED
    storage.restore.assert_awaited_once_with(first_deletion)
    service._assets.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_asset_delete_rejects_assets_referenced_by_avatar(monkeypatch) -> None:
    asset_id = uuid.uuid7()
    storage = AsyncMock()
    service = _asset_delete_service(
        storage=storage,
        assets=[SimpleNamespace(id=asset_id, file_key="avatar/used.png", url="/static/uploads/avatar/used.png")],
    )
    service._assets.is_referenced_by_avatar.return_value = True
    monkeypatch.setattr(AuditCoordinator, "execute", _execute_audit_operation)

    with pytest.raises(AppException) as exc_info:
        await service.delete(asset_id=asset_id, actor_id=uuid.uuid7())

    assert exc_info.value.status_code == 409
    assert exc_info.value.code == ErrorCode.STATE_CONFLICT
    storage.stage_delete.assert_not_awaited()
    service._assets.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_asset_delete_rejects_product_image_before_staging(monkeypatch) -> None:
    asset_id = uuid.uuid7()
    storage = AsyncMock()
    service = _asset_delete_service(
        storage=storage,
        assets=[SimpleNamespace(id=asset_id, file_key="product/used.png", url="/static/uploads/product/used.png")],
    )
    service._session.scalar.return_value = uuid.uuid7()
    monkeypatch.setattr(AuditCoordinator, "execute", _execute_audit_operation)

    with pytest.raises(AppException) as conflict:
        await service.delete(asset_id=asset_id, actor_id=uuid.uuid7())

    assert conflict.value.status_code == 409
    assert conflict.value.code == ErrorCode.STATE_CONFLICT
    storage.stage_delete.assert_not_awaited()
    service._assets.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_asset_bulk_delete_restores_in_reverse_order_when_database_commit_fails(monkeypatch) -> None:
    first_id = uuid.uuid7()
    second_id = uuid.uuid7()
    first_deletion = StagedDeletion(token="trash-one", file_key="product/one.png")
    second_deletion = StagedDeletion(token="trash-two", file_key="product/two.png")
    storage = AsyncMock()
    storage.stage_delete.side_effect = [first_deletion, second_deletion]
    service = _asset_delete_service(
        storage=storage,
        assets=[
            SimpleNamespace(id=first_id, file_key=first_deletion.file_key, url="/static/uploads/product/one.png"),
            SimpleNamespace(id=second_id, file_key=second_deletion.file_key, url="/static/uploads/product/two.png"),
        ],
    )

    async def fail_after_operation(_coordinator: AuditCoordinator, **kwargs):
        await kwargs["operation"]()
        raise RuntimeError("database commit failed")

    monkeypatch.setattr(AuditCoordinator, "execute", fail_after_operation)

    with pytest.raises(RuntimeError, match="database commit failed"):
        await service.delete_bulk(asset_ids=[first_id, second_id], actor_id=uuid.uuid7())

    assert [call.args[0] for call in storage.restore.await_args_list] == [second_deletion, first_deletion]


@pytest.mark.asyncio
async def test_asset_bulk_delete_reports_manual_review_when_restore_fails(monkeypatch) -> None:
    first_id = uuid.uuid7()
    first_deletion = StagedDeletion(token="trash-one", file_key="product/one.png")
    storage = AsyncMock()
    storage.stage_delete.side_effect = [first_deletion, OSError("stage failed")]
    storage.restore.side_effect = OSError("restore failed")
    service = _asset_delete_service(
        storage=storage,
        assets=[
            SimpleNamespace(id=first_id, file_key=first_deletion.file_key, url="/static/uploads/product/one.png"),
            SimpleNamespace(id=uuid.uuid7(), file_key="product/two.png", url="/static/uploads/product/two.png"),
        ],
    )
    monkeypatch.setattr(AuditCoordinator, "execute", _execute_audit_operation)

    with pytest.raises(AppException, match="文件删除结果需要人工核查") as exc_info:
        await service.delete_bulk(
            asset_ids=[asset.id for asset in service._assets.get_many.return_value],
            actor_id=uuid.uuid7(),
        )

    assert exc_info.value.code == ErrorCode.ASSET_STORAGE_FAILED


@pytest.mark.asyncio
async def test_asset_bulk_delete_keeps_committed_result_when_trash_purge_fails(monkeypatch) -> None:
    asset_id = uuid.uuid7()
    deletion = StagedDeletion(token="trash-one", file_key="product/one.png")
    storage = AsyncMock()
    storage.stage_delete.return_value = deletion
    storage.purge.side_effect = OSError("purge failed")
    service = _asset_delete_service(
        storage=storage,
        assets=[SimpleNamespace(id=asset_id, file_key=deletion.file_key, url="/static/uploads/product/one.png")],
    )
    monkeypatch.setattr(AuditCoordinator, "execute", _execute_audit_operation)

    result = await service.delete_bulk(asset_ids=[asset_id], actor_id=uuid.uuid7())

    assert result.completed_count == 1
    assert result.target_ids == [asset_id]
    storage.purge.assert_awaited_once_with(deletion)


@pytest.mark.asyncio
async def test_upload_api_rejects_unauthenticated_request(client, asset_api_service: AsyncMock) -> None:
    response = await client.post(
        "/api/v1/assets/upload",
        headers={"Origin": "http://localhost:3000"},
        data={"scene": "avatar"},
        files={"file": ("avatar.png", _PNG, "image/png")},
    )

    assert response.status_code == 401
    assert response.json()["code"] == ErrorCode.AUTH_REQUIRED
    asset_api_service.upload.assert_not_awaited()


@pytest.mark.asyncio
async def test_upload_api_rejects_cookie_from_wrong_origin(client, asset_api_service: AsyncMock) -> None:
    client.cookies.set("pinjie_web_access", "web-access-token")
    response = await client.post(
        "/api/v1/assets/upload",
        headers={"Origin": "http://localhost:3001"},
        data={"scene": "avatar"},
        files={"file": ("avatar.png", _PNG, "image/png")},
    )

    assert response.status_code == 403
    assert response.json()["code"] == ErrorCode.CSRF_REJECTED
    asset_api_service.upload.assert_not_awaited()


@pytest.mark.asyncio
async def test_upload_api_rejects_missing_csrf_pair(
    client,
    asset_api_service: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = _current_principal(admin=False, csrf_token="web-csrf-token")

    async def fake_current_user(*_args, **_kwargs):
        return current

    monkeypatch.setattr(api_dependencies, "get_current_user", fake_current_user)
    client.cookies.set("pinjie_web_access", "web-access-token")
    response = await client.post(
        "/api/v1/assets/upload",
        headers={"Origin": "http://localhost:3000"},
        data={"scene": "avatar"},
        files={"file": ("avatar.png", _PNG, "image/png")},
    )

    assert response.status_code == 403
    assert response.json()["code"] == ErrorCode.CSRF_REJECTED
    asset_api_service.upload.assert_not_awaited()


@pytest.mark.parametrize(
    ("admin", "origin", "access_cookie", "csrf_cookie"),
    [
        (False, "http://localhost:3000", "pinjie_web_access", "pinjie_web_csrf"),
        (True, "http://localhost:3001", "pinjie_admin_access", "pinjie_admin_csrf"),
    ],
)
@pytest.mark.asyncio
async def test_upload_api_accepts_authenticated_dual_domain_session(
    client,
    asset_api_service: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    admin: bool,
    origin: str,
    access_cookie: str,
    csrf_cookie: str,
) -> None:
    csrf_token = "domain-csrf-token"
    current = _current_principal(admin=admin, csrf_token=csrf_token)

    async def fake_current(*_args, **_kwargs):
        return current

    monkeypatch.setattr(
        api_dependencies,
        "get_current_admin" if admin else "get_current_user",
        fake_current,
    )
    client.cookies.set(access_cookie, "domain-access-token")
    client.cookies.set(csrf_cookie, csrf_token)
    response = await client.post(
        "/api/v1/assets/upload",
        headers={"Origin": origin, "X-CSRF-Token": csrf_token},
        data={"scene": "avatar"},
        files={"file": ("avatar.png", _PNG, "image/png")},
    )

    assert response.status_code == 201
    assert response.json()["data"]["url"].startswith("/static/uploads/avatar/")
    uploader = asset_api_service.upload.await_args.kwargs["uploader"]
    assert uploader.type == (UploaderType.ADMIN if admin else UploaderType.USER)
    assert uploader.id == (current.admin.id if admin else current.user.id)


@pytest.mark.asyncio
async def test_local_storage_rejects_oversized_and_disguised_files(tmp_path: Path) -> None:
    provider = LocalStorageProvider(tmp_path / "uploads", io_concurrency=1)

    with pytest.raises(ValueError, match="file_too_large"):
        await provider.stage(io.BytesIO(_PNG), extension="png", max_bytes=4)
    with pytest.raises(ValueError, match="file_type_mismatch"):
        await provider.stage(io.BytesIO(b"not-a-png"), extension="png", max_bytes=1024)

    assert not list((tmp_path / ".uploads-staging").glob("upload-*"))


@pytest.mark.parametrize(
    ("extension", "content", "mime_type"),
    [
        ("jpg", b"\xff\xd8\xff" + b"jpeg", "image/jpeg"),
        ("gif", b"GIF89a" + b"gif", "image/gif"),
        ("webp", b"RIFF\x04\x00\x00\x00WEBP" + b"webp", "image/webp"),
        ("pdf", b"%PDF-1.7\n" + b"pdf", "application/pdf"),
        ("doc", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"doc", "application/msword"),
        ("xls", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"xls", "application/vnd.ms-excel"),
        (
            "docx",
            _zip_content("[Content_Types].xml", "word/document.xml"),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
        (
            "xlsx",
            _zip_content("[Content_Types].xml", "xl/workbook.xml"),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ),
        ("zip", _zip_content("payload.txt"), "application/zip"),
    ],
)
@pytest.mark.asyncio
async def test_local_storage_detects_supported_file_formats(
    tmp_path: Path,
    extension: str,
    content: bytes,
    mime_type: str,
) -> None:
    provider = LocalStorageProvider(tmp_path / "uploads", io_concurrency=1)

    staged = await provider.stage(io.BytesIO(content), extension=extension, max_bytes=1024 * 1024)

    assert staged.file_size == len(content)
    assert staged.mime_type == mime_type
    await provider.discard(staged)


@pytest.mark.asyncio
async def test_local_storage_commit_restore_purge_and_path_boundary(tmp_path: Path) -> None:
    provider = LocalStorageProvider(tmp_path / "uploads", io_concurrency=1)
    staged = await provider.stage(io.BytesIO(_PNG), extension="png", max_bytes=1024)
    file_key = "avatar/20260825/hash_asset.png"

    await provider.commit(staged, file_key=file_key)
    assert await provider.exists(file_key)

    deletion = await provider.stage_delete(file_key)
    assert not await provider.exists(file_key)
    await provider.restore(deletion)
    assert await provider.exists(file_key)

    deletion = await provider.stage_delete(file_key)
    await provider.purge(deletion)
    assert not await provider.exists(file_key)
    with pytest.raises(FileNotFoundError):
        await provider.stage_delete(file_key)
    with pytest.raises(ValueError, match="escapes storage root"):
        await provider.exists("../escape.png")


@pytest.mark.asyncio
async def test_local_storage_rejects_empty_file(tmp_path: Path) -> None:
    provider = LocalStorageProvider(tmp_path / "uploads", io_concurrency=1)

    with pytest.raises(ValueError, match="empty_file"):
        await provider.stage(io.BytesIO(), extension="png", max_bytes=1024)


@pytest.mark.asyncio
async def test_asset_service_maps_invalid_uploads_to_public_errors(tmp_path: Path) -> None:
    settings = _integration_settings(tmp_path / "uploads")
    resources = create_resources(settings)
    uploader = AssetUploader(type=UploaderType.USER, id=uuid.uuid7())
    try:
        async with resources.session_factory() as session:
            service = AssetService(
                session=session,
                session_factory=resources.session_factory,
                settings=settings,
                storage=LocalStorageProvider(settings.upload_local_root, io_concurrency=1),
                metadata=_metadata(),
            )
            for filename in ("avatar.exe", "", "avatar.bad-ext"):
                with pytest.raises(AppException) as exc_info:
                    await service.upload(
                        source=io.BytesIO(_PNG),
                        original_name=filename,
                        scene=UploadScene.AVATAR,
                        uploader=uploader,
                    )
                assert exc_info.value.code == ErrorCode.ASSET_TYPE_NOT_ALLOWED

            with pytest.raises(AppException) as empty_exc:
                await service.upload(
                    source=io.BytesIO(),
                    original_name="avatar.png",
                    scene=UploadScene.AVATAR,
                    uploader=uploader,
                )
            assert empty_exc.value.status_code == 422
            assert empty_exc.value.code == ErrorCode.ASSET_TYPE_NOT_ALLOWED

            with pytest.raises(AppException) as oversized_exc:
                await service.upload(
                    source=io.BytesIO(_PNG + b"x" * (2 * 1024 * 1024)),
                    original_name="avatar.png",
                    scene=UploadScene.AVATAR,
                    uploader=uploader,
                )
            assert oversized_exc.value.status_code == 413
            assert oversized_exc.value.code == ErrorCode.ASSET_FILE_TOO_LARGE
    finally:
        await resources.close()


@pytest.mark.asyncio
async def test_asset_service_maps_storage_io_failure_to_unavailable(tmp_path: Path) -> None:
    blocked_parent = tmp_path / "blocked"
    blocked_parent.write_bytes(b"not-a-directory")
    settings = _integration_settings(blocked_parent / "uploads")
    resources = create_resources(settings)
    try:
        async with resources.session_factory() as session:
            service = AssetService(
                session=session,
                session_factory=resources.session_factory,
                settings=settings,
                storage=LocalStorageProvider(settings.upload_local_root, io_concurrency=1),
                metadata=_metadata(),
            )
            with pytest.raises(AppException) as exc_info:
                await service.upload(
                    source=io.BytesIO(_PNG),
                    original_name="avatar.png",
                    scene=UploadScene.AVATAR,
                    uploader=AssetUploader(type=UploaderType.USER, id=uuid.uuid7()),
                )
            assert exc_info.value.status_code == 503
            assert exc_info.value.code == ErrorCode.ASSET_STORAGE_FAILED
    finally:
        await resources.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_asset_upload_deduplicates_and_audited_delete_uses_real_postgres(tmp_path: Path) -> None:
    settings = _integration_settings(tmp_path / "uploads")
    resources = create_resources(settings)
    storage = LocalStorageProvider(settings.upload_local_root, io_concurrency=1)
    uploader = AssetUploader(type=UploaderType.USER, id=uuid.uuid7())
    actor_id = uuid.uuid7()
    asset_id: uuid.UUID | None = None
    try:
        async with resources.session_factory() as session:
            service = AssetService(
                session=session,
                session_factory=resources.session_factory,
                settings=settings,
                storage=storage,
                metadata=_metadata(),
            )
            created = await service.upload(
                source=io.BytesIO(_PNG),
                original_name="avatar.png",
                scene=UploadScene.AVATAR,
                uploader=uploader,
            )
            duplicate = await service.upload(
                source=io.BytesIO(_PNG),
                original_name="avatar-copy.png",
                scene=UploadScene.AVATAR,
                uploader=uploader,
            )
            asset_id = created.id
            assert duplicate.id == created.id
            assert created.mime_type == "image/png"
            assert created.file_key.startswith("avatar/")
            assert created.url.startswith("/static/uploads/avatar/")
            assert (settings.upload_local_root / created.file_key).read_bytes() == _PNG

            (settings.upload_local_root / created.file_key).unlink()
            repaired = await service.upload(
                source=io.BytesIO(_PNG),
                original_name="avatar-repair.png",
                scene=UploadScene.AVATAR,
                uploader=uploader,
            )
            assert repaired.id == created.id
            assert (settings.upload_local_root / created.file_key).read_bytes() == _PNG

            page = await service.list(page=1, page_size=20)
            assert any(item.id == created.id for item in page.items)
            assert page.total >= 1

            stored = await session.scalar(select(Asset).where(Asset.id == created.id))
            assert stored is not None
            assert stored.file_hash == created.file_hash

            await service.delete(asset_id=created.id, actor_id=actor_id)
            assert not (settings.upload_local_root / created.file_key).exists()

        async with resources.session_factory() as session:
            assert await session.scalar(select(Asset).where(Asset.id == asset_id)) is None
            audit = await session.scalar(
                select(AuditEvent).where(AuditEvent.target_id == asset_id, AuditEvent.action == "asset.delete")
            )
            assert audit is not None
            assert audit.result == "succeeded"
    finally:
        async with resources.session_factory() as session, transaction_scope(session):
            if asset_id is not None:
                await session.execute(delete(Asset).where(Asset.id == asset_id))
                await session.execute(delete(AuditEvent).where(AuditEvent.target_id == asset_id))
        await resources.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_asset_bulk_delete_filters_and_rejects_partial_targets(tmp_path: Path) -> None:
    settings = _integration_settings(tmp_path / "uploads")
    resources = create_resources(settings)
    storage = LocalStorageProvider(settings.upload_local_root, io_concurrency=1)
    uploader = AssetUploader(type=UploaderType.USER, id=uuid.uuid7())
    actor_id = uuid.uuid7()
    asset_ids: list[uuid.UUID] = []
    file_keys: list[str] = []
    try:
        async with resources.session_factory() as session:
            service = AssetService(
                session=session,
                session_factory=resources.session_factory,
                settings=settings,
                storage=storage,
                metadata=_metadata(),
            )
            first = await service.upload(
                source=io.BytesIO(_PNG + b"-bulk-one"),
                original_name="batch-one.png",
                scene=UploadScene.AVATAR,
                uploader=uploader,
            )
            second = await service.upload(
                source=io.BytesIO(_PNG + b"-bulk-two"),
                original_name="batch-two.png",
                scene=UploadScene.AVATAR,
                uploader=uploader,
            )
            asset_ids = [first.id, second.id]
            file_keys = [first.file_key, second.file_key]

            filtered = await service.list(
                page=1,
                page_size=20,
                search="batch-one",
                scene=UploadScene.AVATAR,
                uploader_type=UploaderType.USER,
            )
            assert [item.id for item in filtered.items] == [first.id]

            missing_id = uuid.uuid7()
            with pytest.raises(AppException) as missing_exc:
                await service.delete_bulk(asset_ids=[first.id, missing_id], actor_id=actor_id)
            assert missing_exc.value.code == ErrorCode.ASSET_NOT_FOUND
            assert all((settings.upload_local_root / file_key).is_file() for file_key in file_keys)

            result = await service.delete_bulk(asset_ids=list(reversed(asset_ids)), actor_id=actor_id)
            assert result.completed_count == 2
            assert result.target_ids == sorted(asset_ids)
            assert all(not (settings.upload_local_root / file_key).exists() for file_key in file_keys)

        async with resources.session_factory() as session:
            stored_assets = list((await session.scalars(select(Asset).where(Asset.id.in_(asset_ids)))).all())
            audits = list(
                (
                    await session.scalars(
                        select(AuditEvent).where(
                            AuditEvent.actor_id == actor_id,
                            AuditEvent.action == "assets:delete-bulk",
                        )
                    )
                ).all()
            )
            assert stored_assets == []
            assert {audit.result for audit in audits} == {"denied", "succeeded"}
    finally:
        async with resources.session_factory() as session, transaction_scope(session):
            if asset_ids:
                await session.execute(delete(Asset).where(Asset.id.in_(asset_ids)))
            await session.execute(delete(AuditEvent).where(AuditEvent.actor_id == actor_id))
        for file_key in file_keys:
            (settings.upload_local_root / file_key).unlink(missing_ok=True)
        await resources.close()


@pytest.mark.asyncio
async def test_user_cannot_upload_admin_only_scene(tmp_path: Path) -> None:
    settings = _integration_settings(tmp_path / "uploads")
    resources = create_resources(settings)
    try:
        async with resources.session_factory() as session:
            service = AssetService(
                session=session,
                session_factory=resources.session_factory,
                settings=settings,
                storage=LocalStorageProvider(settings.upload_local_root, io_concurrency=1),
                metadata=_metadata(),
            )
            with pytest.raises(AppException) as exc_info:
                await service.upload(
                    source=io.BytesIO(_PNG),
                    original_name="product.png",
                    scene=UploadScene.PRODUCT,
                    uploader=AssetUploader(type=UploaderType.USER, id=uuid.uuid7()),
                )
            assert exc_info.value.code == ErrorCode.PERMISSION_DENIED
    finally:
        await resources.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_attachment_scene_uses_global_policy_and_persists_zip(tmp_path: Path) -> None:
    settings = _integration_settings(tmp_path / "uploads")
    resources = create_resources(settings)
    asset_id: uuid.UUID | None = None
    file_key: str | None = None
    try:
        async with resources.session_factory() as session:
            service = AssetService(
                session=session,
                session_factory=resources.session_factory,
                settings=settings,
                storage=LocalStorageProvider(settings.upload_local_root, io_concurrency=1),
                metadata=_metadata(),
            )
            created = await service.upload(
                source=io.BytesIO(_zip_content("payload.txt")),
                original_name="archive.zip",
                scene=UploadScene.ATTACHMENT,
                uploader=AssetUploader(type=UploaderType.USER, id=uuid.uuid7()),
            )
            asset_id = created.id
            file_key = created.file_key
            assert created.mime_type == "application/zip"
            assert created.file_key.startswith("attachment/")
    finally:
        async with resources.session_factory() as session, transaction_scope(session):
            if asset_id is not None:
                await session.execute(delete(Asset).where(Asset.id == asset_id))
        if file_key is not None:
            (settings.upload_local_root / file_key).unlink(missing_ok=True)
        await resources.close()
