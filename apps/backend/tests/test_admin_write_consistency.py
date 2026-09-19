import io
import os
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import delete, or_, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.core.request_metadata import RequestMetadata
from app.db.models import Admin, Asset, AuditEvent
from app.db.repositories import AdminRepository
from app.domains.admin.schemas import AdminCreateIn, AdminProfileUpdateIn, AdminUpdateIn
from app.domains.assets.schemas import UploaderType, UploadScene
from app.services.accounts import AdminAccountService
from app.services.admin_management import AdminManagementService
from app.services.assets import AssetService, AssetUploader, resolve_admin_avatar
from app.services.storage import LocalStorageProvider


def _metadata() -> RequestMetadata:
    return RequestMetadata(
        request_id=str(uuid.uuid7()),
        trace_id=str(uuid.uuid7()),
        ip_address="127.0.0.1",
        user_agent_summary="pytest",
        release_version="test",
    )


@pytest.fixture
async def admin_database():
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.fail("TEST_DATABASE_URL is required for administrator consistency tests")
    settings = Settings(
        _env_file=None,
        ENVIRONMENT="test",
        DATABASE_URL=database_url,
        TEST_DATABASE_URL=database_url,
        WEB_JWT_SECRET="test-web-jwt-secret-0000000000000001",
        ADMIN_JWT_SECRET="test-admin-jwt-secret-0000000000001",
        WEB_TOKEN_HMAC_KEY="test-web-hmac-secret-000000000000001",
        ADMIN_TOKEN_HMAC_KEY="test-admin-hmac-secret-0000000000001",
    )
    settings.validate_database_runtime()
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    actor_id = uuid.uuid7()
    created_username = f"review-created-{actor_id.hex}"
    try:
        async with factory() as session:
            session.add(
                Admin(
                    id=actor_id,
                    username=f"review-actor-{actor_id.hex}",
                    password_hash="test-only-unused-hash",
                    is_active=True,
                    is_superuser=True,
                    credential_version=1,
                )
            )
            await session.commit()
        yield SimpleNamespace(
            factory=factory,
            settings=settings,
            actor_id=actor_id,
            created_username=created_username,
        )
    finally:
        try:
            async with factory() as session:
                await session.execute(delete(AuditEvent).where(AuditEvent.actor_id == actor_id))
                await session.execute(delete(Asset).where(Asset.uploader_id == actor_id))
                await session.execute(
                    delete(Admin).where(or_(Admin.id == actor_id, Admin.username == created_username))
                )
                await session.commit()
        finally:
            # 确保无论清理 SQL 是否失败，引擎连接池都能被正确关闭
            await engine.dispose()


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize("change", [{"is_superuser": False}, {"is_active": False}])
async def test_final_authorization_reloads_cached_actor_after_revocation(admin_database, change) -> None:
    database = admin_database
    async with database.factory() as request_session:
        actor = await AdminRepository(request_session).get(database.actor_id)
        assert actor.is_active and actor.is_superuser
        async with database.factory() as concurrent_session:
            await concurrent_session.execute(update(Admin).where(Admin.id == database.actor_id).values(**change))
            await concurrent_session.commit()

        service = AdminManagementService(
            session=request_session,
            session_factory=database.factory,
            settings=database.settings,
            password_manager=SimpleNamespace(hash=AsyncMock(return_value="test-only-unused-hash")),
            metadata=_metadata(),
            actor_id=database.actor_id,
        )
        with pytest.raises(AppException) as error:
            await service.create_admin(
                AdminCreateIn(
                    username=database.created_username,
                    initial_password="test-only-password",
                    is_superuser=True,
                )
            )
        assert error.value.status_code == 403
        assert error.value.code == ErrorCode.PERMISSION_DENIED
        assert await request_session.scalar(select(Admin.id).where(Admin.username == database.created_username)) is None


@pytest.fixture
async def avatar_asset(admin_database, tmp_path):
    database = admin_database
    storage = LocalStorageProvider(tmp_path / "uploads", io_concurrency=2)
    async with database.factory() as session:
        service = AssetService(
            session=session,
            session_factory=database.factory,
            settings=database.settings,
            storage=storage,
            metadata=_metadata(),
        )
        asset = await service.upload(
            source=io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"test-only-image"),
            original_name="avatar.png",
            scene=UploadScene.AVATAR,
            uploader=AssetUploader(type=UploaderType.ADMIN, id=database.actor_id),
        )
    return SimpleNamespace(asset=asset, storage=storage)


async def _save_avatar(database, session, endpoint, avatar):
    if endpoint == "account":
        actor = await AdminRepository(session).get(database.actor_id)
        service = AdminAccountService(
            session=session,
            session_factory=database.factory,
            settings=database.settings,
            redis=None,
            password_manager=AsyncMock(),
            metadata=_metadata(),
        )
        return await service.update_profile(admin=actor, payload=AdminProfileUpdateIn(avatar=avatar))
    service = AdminManagementService(
        session=session,
        session_factory=database.factory,
        settings=database.settings,
        password_manager=AsyncMock(),
        metadata=_metadata(),
        actor_id=database.actor_id,
    )
    return await service.update_admin(database.actor_id, AdminUpdateIn(avatar=avatar))


async def _delete_avatar(database, upload):
    async with database.factory() as session:
        service = AssetService(
            session=session,
            session_factory=database.factory,
            settings=database.settings,
            storage=upload.storage,
            metadata=_metadata(),
        )
        await service.delete(asset_id=upload.asset.id, actor_id=database.actor_id)


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ["account", "management"])
async def test_admin_avatar_rejects_asset_deleted_before_profile_save(admin_database, avatar_asset, endpoint) -> None:
    database = admin_database
    await _delete_avatar(database, avatar_asset)
    async with database.factory() as session:
        with pytest.raises(AppException) as error:
            await _save_avatar(database, session, endpoint, avatar_asset.asset.url)
        assert error.value.code == ErrorCode.ASSET_NOT_FOUND
        assert await session.scalar(select(Admin.avatar).where(Admin.id == database.actor_id)) is None


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ["account", "management"])
async def test_admin_avatar_normalizes_reference_and_blocks_deletion(admin_database, avatar_asset, endpoint) -> None:
    database = admin_database
    alias = f"{database.settings.admin_origins[0]}{avatar_asset.asset.url}?v=1#preview"
    async with database.factory() as session:
        admin = await _save_avatar(database, session, endpoint, alias)
        assert admin.avatar == avatar_asset.asset.url
    with pytest.raises(AppException) as error:
        await _delete_avatar(database, avatar_asset)
    assert error.value.code == ErrorCode.STATE_CONFLICT
    assert await avatar_asset.storage.exists(avatar_asset.asset.file_key)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_avatar_binding_holds_asset_lock_until_transaction_ends(admin_database, avatar_asset) -> None:
    database = admin_database
    async with database.factory() as binding_session:
        await resolve_admin_avatar(session=binding_session, settings=database.settings, avatar=avatar_asset.asset.url)
        async with database.factory() as deletion_session:
            with pytest.raises(DBAPIError) as error:
                await deletion_session.execute(
                    select(Asset).where(Asset.id == avatar_asset.asset.id).with_for_update(nowait=True)
                )
            assert error.value.orig.sqlstate == "55P03"
        await binding_session.rollback()
    await _delete_avatar(database, avatar_asset)
    assert not await avatar_asset.storage.exists(avatar_asset.asset.file_key)


@pytest.mark.asyncio
@pytest.mark.parametrize("avatar", [None, " ", "https://external.example/avatar.png", "/images/default-avatar.png"])
async def test_admin_avatar_preserves_external_and_non_asset_values_without_database_access(avatar) -> None:
    session = AsyncMock()
    result = await resolve_admin_avatar(session=session, settings=Settings.model_construct(), avatar=avatar)
    assert result == (avatar.strip() or None if avatar else None)
    session.execute.assert_not_awaited()
