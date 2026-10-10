from fastapi import APIRouter, Depends

from app.api.dependencies import ConsumerAuth, UserPrincipal, require_consumer_profile
from app.core.context import current_request_id
from app.core.response import ResponseModel, success_response

from .schemas import ConsumerCapabilitiesRead, ConsumerRefreshIn, ConsumerSessionRead, WechatLoginIn

router = APIRouter(prefix="/auth", tags=["用户认证"], dependencies=[Depends(require_consumer_profile)])


@router.get("/capabilities", response_model=ResponseModel[ConsumerCapabilitiesRead], summary="查询微信登录开放状态")
async def capabilities(auth: ConsumerAuth) -> ResponseModel[ConsumerCapabilitiesRead]:
    return success_response(
        data=ConsumerCapabilitiesRead(login_enabled=auth.settings.miniapp_login_enabled),
        request_id=current_request_id(),
    )


@router.post("/login", response_model=ResponseModel[ConsumerSessionRead], summary="微信凭证登录")
async def login(payload: WechatLoginIn, auth: ConsumerAuth) -> ResponseModel[ConsumerSessionRead]:
    return success_response(data=await auth.login(payload.code), request_id=current_request_id())


@router.post("/refresh", response_model=ResponseModel[ConsumerSessionRead], summary="轮换小程序会话凭据")
async def refresh(payload: ConsumerRefreshIn, auth: ConsumerAuth) -> ResponseModel[ConsumerSessionRead]:
    return success_response(data=await auth.refresh(payload.refresh_token), request_id=current_request_id())


@router.post("/logout", response_model=ResponseModel[None], summary="退出小程序会话")
async def logout(auth: ConsumerAuth, current: UserPrincipal) -> ResponseModel[None]:
    await auth.logout(current.user.id, current.login_session.id)
    return success_response(data=None, request_id=current_request_id())
