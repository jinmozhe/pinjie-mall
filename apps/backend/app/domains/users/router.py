from typing import Annotated

from fastapi import APIRouter, File, Query, UploadFile

from app.api.account_dependencies import ConsumerAccount, ConsumerAvatarUploader, ConsumerProfile
from app.api.dependencies import AssetServiceDependency, UserPrincipal
from app.core.context import current_request_id
from app.core.response import ResponseModel, success_response
from app.domains.assets.schemas import UploadScene
from app.domains.auth.schemas import (
    ConsumerUserRead,
)
from app.domains.users.schemas import (
    ConsumerAvatarAssetRead,
    ConsumerAvatarUpdate,
    ConsumerProfileUpdate,
    UserAvatarUpdateIn,
    UserUpdateIn,
)
from app.domains.users.security_schemas import (
    ConsumerClosurePrecheckRead,
    ConsumerLoginSessionsRead,
    ConsumerSessionRevocationRead,
    ConsumerSessionTargets,
)

router = APIRouter(prefix="/users/me", tags=["用户账户"])


@router.get("/sessions", response_model=ResponseModel[ConsumerLoginSessionsRead], summary="分页查询本人小程序登录会话")
async def login_sessions(
    service: ConsumerAccount,
    current: UserPrincipal,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 10,
) -> ResponseModel[ConsumerLoginSessionsRead]:
    return success_response(
        data=await service.list_sessions(current.user.id, current.login_session.id, page, page_size),
        request_id=current_request_id(),
    )


@router.post(
    "/sessions/revoke",
    response_model=ResponseModel[ConsumerSessionRevocationRead],
    summary="撤销本人已确认的其他小程序会话集合",
)
async def revoke_login_sessions(
    payload: ConsumerSessionTargets,
    service: ConsumerAccount,
    current: UserPrincipal,
) -> ResponseModel[ConsumerSessionRevocationRead]:
    return success_response(
        data=await service.revoke(current.user.id, current.login_session.id, current.user.credential_version, payload),
        request_id=current_request_id(),
        message="指定会话已撤销",
    )


@router.post(
    "/sessions/revocation-status",
    response_model=ResponseModel[ConsumerSessionRevocationRead],
    summary="只读查询原目标会话状态，不执行撤销",
)
async def login_session_revocation_status(
    payload: ConsumerSessionTargets,
    service: ConsumerAccount,
    current: UserPrincipal,
) -> ResponseModel[ConsumerSessionRevocationRead]:
    return success_response(
        data=await service.revocation_status(current.user.id, payload), request_id=current_request_id()
    )


@router.get(
    "/closure-precheck",
    response_model=ResponseModel[ConsumerClosurePrecheckRead],
    summary="只读核对本人注销咨询事项，自助注销保持关闭",
)
async def account_closure_precheck(
    service: ConsumerAccount, current: UserPrincipal
) -> ResponseModel[ConsumerClosurePrecheckRead]:
    return success_response(data=await service.closure_precheck(current.user.id), request_id=current_request_id())


@router.patch("", response_model=ResponseModel[ConsumerUserRead], summary="修改本人小程序昵称")
async def profile_update(
    payload: ConsumerProfileUpdate, service: ConsumerProfile, current: UserPrincipal
) -> ResponseModel[ConsumerUserRead]:
    user = await service.update_profile(current.user.id, UserUpdateIn(display_name=payload.display_name))
    return success_response(data=ConsumerUserRead.model_validate(user), request_id=current_request_id())


@router.put("/avatar", response_model=ResponseModel[ConsumerUserRead], summary="绑定或移除本人头像资产")
async def avatar_update(
    payload: ConsumerAvatarUpdate, service: ConsumerProfile, current: UserPrincipal
) -> ResponseModel[ConsumerUserRead]:
    user = await service.update_avatar(current.user.id, UserAvatarUpdateIn(asset_id=payload.asset_id))
    return success_response(data=ConsumerUserRead.model_validate(user), request_id=current_request_id())


@router.post(
    "/avatar-assets",
    response_model=ResponseModel[ConsumerAvatarAssetRead],
    status_code=201,
    summary="上传本人头像资产",
    description="仅允许 avatar 场景；复用类型、体积及存储校验，只返回资产标识和公开地址，上传不自动绑定头像。",
)
async def avatar_upload(
    file: Annotated[UploadFile, File()], uploader: ConsumerAvatarUploader, service: AssetServiceDependency
) -> ResponseModel[ConsumerAvatarAssetRead]:
    asset = await service.upload(
        source=file.file, original_name=file.filename or "", scene=UploadScene.AVATAR, uploader=uploader
    )
    return success_response(data=ConsumerAvatarAssetRead.model_validate(asset), request_id=current_request_id())


@router.get("", response_model=ResponseModel[ConsumerUserRead], summary="读取本人基础信息")
async def me(current: UserPrincipal) -> ResponseModel[ConsumerUserRead]:
    return success_response(data=ConsumerUserRead.model_validate(current.user), request_id=current_request_id())
