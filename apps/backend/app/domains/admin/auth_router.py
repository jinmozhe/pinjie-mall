from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Request, Response
from loguru import logger

from app.api.dependencies import (
    AdminAccountServiceDependency,
    AdminAuthServiceDependency,
    CurrentAdmin,
    get_current_admin,
    get_request_settings,
    require_admin_csrf,
    require_admin_csrf_pair,
    require_admin_origin,
)
from app.core.context import current_request_id
from app.core.cookies import ADMIN_COOKIES, clear_auth_cookies, set_auth_cookies
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.core.response import ResponseModel, success_response
from app.domains.auth.schemas import RefreshSessionOut
from app.domains.users.schemas import PasswordChangeIn
from app.services.authentication import SessionArtifacts

from .presenters import admin_read
from .schemas import AdminAuthSessionOut, AdminConfirmIn, AdminConfirmOut, AdminLoginIn, AdminProfileUpdateIn, AdminRead

router = APIRouter(prefix="/admin/auth", tags=["管理员认证"])


def _set_session_cookies(response: Response, request: Request, artifacts: SessionArtifacts) -> None:
    settings = get_request_settings(request)
    set_auth_cookies(
        response,
        names=ADMIN_COOKIES,
        access_token=artifacts.access_token,
        refresh_token=artifacts.refresh_token,
        csrf_token=artifacts.csrf_token,
        access_max_age=settings.admin_access_ttl_seconds,
        refresh_max_age=settings.refresh_idle_ttl_days * 86400,
        settings=settings,
    )


@router.post(
    "/login",
    response_model=ResponseModel[AdminAuthSessionOut],
    dependencies=[Depends(require_admin_origin)],
    summary="管理员登录",
)
async def login(
    payload: AdminLoginIn,
    request: Request,
    response: Response,
    service: AdminAuthServiceDependency,
) -> ResponseModel[AdminAuthSessionOut]:
    admin, artifacts = await service.login(payload)
    _set_session_cookies(response, request, artifacts)
    return success_response(
        data=AdminAuthSessionOut(
            principal=admin_read(admin),
            session_id=artifacts.session_id,
            access_expires_at=artifacts.access_expires_at,
            idle_expires_at=artifacts.idle_expires_at,
            absolute_expires_at=artifacts.absolute_expires_at,
        ),
        request_id=current_request_id(),
        message="登录成功",
    )


@router.post("/refresh", response_model=ResponseModel[RefreshSessionOut], summary="刷新管理员登录会话")
async def refresh(
    request: Request,
    response: Response,
    service: AdminAuthServiceDependency,
    csrf_token: Annotated[str, Depends(require_admin_csrf_pair)],
    refresh_token: Annotated[str | None, Cookie(alias=ADMIN_COOKIES.refresh)] = None,
) -> ResponseModel[RefreshSessionOut]:
    try:
        if not refresh_token:
            raise AppException(
                status_code=401,
                code=ErrorCode.AUTH_REQUIRED,
                message="需要管理员刷新令牌身份认证",
                headers={"WWW-Authenticate": "Cookie"},
            )
        artifacts = await service.refresh(refresh_token, csrf_token)
    except AppException as exc:
        if exc.code in {
            ErrorCode.AUTH_REQUIRED,
            ErrorCode.AUTH_TOKEN_INVALID,
            ErrorCode.AUTH_REFRESH_REUSE_DETECTED,
            ErrorCode.AUTH_SESSION_REVOKED,
            ErrorCode.AUTH_SESSION_EXPIRED,
            ErrorCode.AUTH_ACCOUNT_DISABLED,
        }:
            request.state.clear_auth_profile = "admin"
        raise
    _set_session_cookies(response, request, artifacts)
    return success_response(
        data=RefreshSessionOut(
            session_id=artifacts.session_id,
            access_expires_at=artifacts.access_expires_at,
            idle_expires_at=artifacts.idle_expires_at,
            absolute_expires_at=artifacts.absolute_expires_at,
        ),
        request_id=current_request_id(),
        message="会话刷新成功",
    )


@router.post("/logout", response_model=ResponseModel[bool], summary="退出当前管理员会话")
async def logout(
    request: Request,
    response: Response,
    service: AdminAuthServiceDependency,
    csrf_token: Annotated[str, Depends(require_admin_csrf_pair)],
    refresh_token: Annotated[str | None, Cookie(alias=ADMIN_COOKIES.refresh)] = None,
) -> ResponseModel[bool]:
    request.state.clear_auth_profile = "admin"
    if not refresh_token:
        raise AppException(
            status_code=401,
            code=ErrorCode.AUTH_REQUIRED,
            message="需要管理员刷新令牌身份认证",
            headers={"WWW-Authenticate": "Cookie"},
        )
    await service.logout(refresh_token, csrf_token)
    clear_auth_cookies(response, names=ADMIN_COOKIES, settings=get_request_settings(request))
    request.state.clear_auth_profile = None
    return success_response(data=True, request_id=current_request_id(), message="退出登录成功")


@router.get("/me", response_model=ResponseModel[AdminRead], summary="获取当前管理员")
async def get_me(current: Annotated[CurrentAdmin, Depends(get_current_admin)]) -> ResponseModel[AdminRead]:
    return success_response(data=admin_read(current.admin), request_id=current_request_id())


@router.patch("/profile", response_model=ResponseModel[AdminRead], summary="修改当前管理员个人资料")
async def update_profile(
    payload: AdminProfileUpdateIn,
    service: AdminAccountServiceDependency,
    current: Annotated[CurrentAdmin, Depends(require_admin_csrf)],
) -> ResponseModel[AdminRead]:
    admin = await service.update_profile(
        admin=current.admin,
        payload=payload,
    )
    return success_response(data=admin_read(admin), request_id=current_request_id(), message="个人资料已更新")


@router.post("/password", response_model=ResponseModel[RefreshSessionOut], summary="修改当前管理员密码")
async def change_password(
    payload: PasswordChangeIn,
    request: Request,
    response: Response,
    service: AdminAccountServiceDependency,
    current: Annotated[CurrentAdmin, Depends(require_admin_csrf)],
) -> ResponseModel[RefreshSessionOut]:
    artifacts = await service.change_password(
        admin=current.admin,
        login_session=current.login_session,
        payload=payload,
    )
    _set_session_cookies(response, request, artifacts)
    return success_response(
        data=RefreshSessionOut(
            session_id=artifacts.session_id,
            access_expires_at=artifacts.access_expires_at,
            idle_expires_at=artifacts.idle_expires_at,
            absolute_expires_at=artifacts.absolute_expires_at,
        ),
        request_id=current_request_id(),
        message="密码修改成功",
    )


@router.post(
    "/confirm",
    response_model=ResponseModel[AdminConfirmOut],
    summary="兼容旧版管理员敏感操作确认",
    description="仅供旧版 Admin 客户端迁移使用，已弃用并计划于 2026-09-26 删除。确认回执不参与后续操作授权。",
    deprecated=True,
    operation_id="confirm_api_v1_admin_auth_confirm_post",
)
async def confirm_compatibility(
    payload: AdminConfirmIn,
    response: Response,
    service: AdminAccountServiceDependency,
    current: Annotated[CurrentAdmin, Depends(require_admin_csrf)],
) -> ResponseModel[AdminConfirmOut]:
    logger.bind(
        event="admin_confirmation_compatibility_used",
        admin_id=str(current.admin.id),
        action=payload.action.value,
        sunset="2026-09-26",
    ).warning("deprecated admin confirmation compatibility endpoint used")
    result = await service.create_confirmation_compatibility(admin=current.admin, payload=payload)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Sunset"] = "Sat, 26 Sep 2026 00:00:00 GMT"
    return success_response(data=result, request_id=current_request_id(), message="敏感操作确认成功")


__all__ = ["router"]
