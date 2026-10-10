import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.db.models import User
from app.domains.assets.schemas import UploaderType, UploadScene
from app.domains.users.schemas import UserAvatarUpdateIn
from app.main import app
from app.services.accounts import UserProfileService


def _service(user: User, asset: object | None) -> UserProfileService:
    service = UserProfileService(
        session=AsyncMock(),
        settings=app.state.settings,
    )
    service.users = SimpleNamespace(get=AsyncMock(return_value=user))  # type: ignore[assignment]
    service.assets = SimpleNamespace(get=AsyncMock(return_value=asset))  # type: ignore[assignment]
    return service


@pytest.mark.asyncio
async def test_user_avatar_schema_accepts_asset_or_null() -> None:
    asset_id = uuid.uuid7()
    assert UserAvatarUpdateIn(asset_id=asset_id).asset_id == asset_id
    assert UserAvatarUpdateIn(asset_id=None).asset_id is None


@pytest.mark.asyncio
async def test_user_can_bind_own_avatar_asset() -> None:
    user_id = uuid.uuid7()
    user = User(id=user_id, username="avatar-user", password_hash="hash", is_active=True, credential_version=1)
    asset = SimpleNamespace(
        uploader_type=UploaderType.USER.value,
        uploader_id=user_id,
        scene=UploadScene.AVATAR.value,
        url=f"{app.state.settings.upload_base_url}/avatar/test.png",
    )
    service = _service(user, asset)

    updated = await service.update_avatar(user_id, UserAvatarUpdateIn(asset_id=uuid.uuid7()))

    assert updated.avatar == asset.url


@pytest.mark.asyncio
async def test_user_avatar_rejects_other_uploader() -> None:
    user_id = uuid.uuid7()
    user = User(id=user_id, username="avatar-user", password_hash="hash", is_active=True, credential_version=1)
    asset = SimpleNamespace(
        uploader_type=UploaderType.ADMIN.value,
        uploader_id=uuid.uuid7(),
        scene=UploadScene.AVATAR.value,
        url=f"{app.state.settings.upload_base_url}/avatar/test.png",
    )
    service = _service(user, asset)

    with pytest.raises(AppException) as exc_info:
        await service.update_avatar(user_id, UserAvatarUpdateIn(asset_id=uuid.uuid7()))

    assert exc_info.value.status_code == 403
    assert exc_info.value.code == ErrorCode.PERMISSION_DENIED
