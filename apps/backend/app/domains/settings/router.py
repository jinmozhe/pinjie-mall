from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile

from app.api.dependencies import (
    AdminSystemSettingsServiceDependency,
    PublicSystemSettingsServiceDependency,
    require_admin_csrf,
    require_permission,
)
from app.core.context import current_request_id
from app.core.response import ResponseModel, success_response
from app.domains.admin.permissions import PermissionCode

from .schemas import (
    AdminRegistrationSettingRead,
    AdminSiteSettingRead,
    MiniappRegistrationPatch,
    MiniappRegistrationRead,
    RegistrationSettingPatchIn,
    SiteProfileRead,
    SiteSettingPatchIn,
)

public_router = APIRouter(prefix="/system", tags=["系统"])
admin_router = APIRouter(prefix="/admin/settings", tags=["系统设置"])


@public_router.get(
    "/site-profile",
    response_model=ResponseModel[SiteProfileRead],
    summary="获取公共站点资料",
    description="返回 Web 服务端渲染所需的完整强类型站点资料，不暴露内部路径、哈希或修订元数据。",
)
async def get_site_profile(
    service: PublicSystemSettingsServiceDependency,
    response: Response,
) -> ResponseModel[SiteProfileRead]:
    response.headers["Cache-Control"] = "no-store"
    return success_response(data=await service.site_profile(), request_id=current_request_id())


@admin_router.get(
    "/site",
    response_model=ResponseModel[AdminSiteSettingRead],
    dependencies=[Depends(require_permission(PermissionCode.SETTINGS_SITE_READ))],
    summary="获取站点设置",
)
async def get_site_setting(service: AdminSystemSettingsServiceDependency) -> ResponseModel[AdminSiteSettingRead]:
    return success_response(data=await service.site_for_admin(), request_id=current_request_id())


@admin_router.patch(
    "/site",
    response_model=ResponseModel[AdminSiteSettingRead],
    dependencies=[Depends(require_admin_csrf), Depends(require_permission(PermissionCode.SETTINGS_SITE_UPDATE))],
    summary="更新站点设置",
)
async def update_site_setting(
    payload: SiteSettingPatchIn,
    service: AdminSystemSettingsServiceDependency,
) -> ResponseModel[AdminSiteSettingRead]:
    return success_response(
        data=await service.update_site(payload), request_id=current_request_id(), message="站点设置已保存"
    )


@admin_router.put(
    "/site/logo",
    response_model=ResponseModel[AdminSiteSettingRead],
    dependencies=[Depends(require_admin_csrf), Depends(require_permission(PermissionCode.SETTINGS_SITE_UPDATE))],
    summary="更换站点 LOGO",
)
async def update_site_logo(
    file: Annotated[UploadFile, File(description="PNG、JPEG 或 WebP 静态 LOGO，最大 2 MB")],
    revision: Annotated[int, Form(gt=0, description="读取站点设置时获得的修订号")],
    service: AdminSystemSettingsServiceDependency,
) -> ResponseModel[AdminSiteSettingRead]:
    return success_response(
        data=await service.upload_site_logo(file.file, revision=revision),
        request_id=current_request_id(),
        message="站点 LOGO 已更新",
    )


@admin_router.delete(
    "/site/logo",
    response_model=ResponseModel[AdminSiteSettingRead],
    dependencies=[Depends(require_admin_csrf), Depends(require_permission(PermissionCode.SETTINGS_SITE_UPDATE))],
    summary="移除站点 LOGO",
)
async def delete_site_logo(
    revision: Annotated[int, Query(gt=0, description="读取站点设置时获得的修订号")],
    service: AdminSystemSettingsServiceDependency,
) -> ResponseModel[AdminSiteSettingRead]:
    return success_response(
        data=await service.delete_site_logo(revision=revision),
        request_id=current_request_id(),
        message="站点 LOGO 已移除",
    )


@admin_router.get(
    "/registration",
    response_model=ResponseModel[AdminRegistrationSettingRead],
    dependencies=[Depends(require_permission(PermissionCode.SETTINGS_REGISTRATION_READ))],
    summary="获取注册设置",
)
async def get_registration_setting(
    service: AdminSystemSettingsServiceDependency,
) -> ResponseModel[AdminRegistrationSettingRead]:
    return success_response(data=await service.registration_for_admin(), request_id=current_request_id())


@admin_router.patch(
    "/registration",
    response_model=ResponseModel[AdminRegistrationSettingRead],
    dependencies=[
        Depends(require_admin_csrf),
        Depends(require_permission(PermissionCode.SETTINGS_REGISTRATION_UPDATE)),
    ],
    summary="更新注册设置",
)
async def update_registration_setting(
    payload: RegistrationSettingPatchIn,
    service: AdminSystemSettingsServiceDependency,
) -> ResponseModel[AdminRegistrationSettingRead]:
    return success_response(
        data=await service.update_registration(payload),
        request_id=current_request_id(),
        message="注册设置已保存",
    )


@admin_router.get(
    "/miniapp-registration",
    response_model=ResponseModel[MiniappRegistrationRead],
    dependencies=[Depends(require_permission(PermissionCode.SETTINGS_MINIAPP_REGISTRATION_READ))],
    summary="读取微信小程序首次建号设置",
)
async def miniapp_registration_read(
    service: AdminSystemSettingsServiceDependency,
) -> ResponseModel[MiniappRegistrationRead]:
    return success_response(data=await service.miniapp_registration_for_admin(), request_id=current_request_id())


@admin_router.patch(
    "/miniapp-registration",
    response_model=ResponseModel[MiniappRegistrationRead],
    dependencies=[
        Depends(require_admin_csrf),
        Depends(require_permission(PermissionCode.SETTINGS_MINIAPP_REGISTRATION_UPDATE)),
    ],
    summary="修改微信小程序首次建号设置",
)
async def miniapp_registration_update(
    payload: MiniappRegistrationPatch, service: AdminSystemSettingsServiceDependency
) -> ResponseModel[MiniappRegistrationRead]:
    return success_response(data=await service.update_miniapp_registration(payload), request_id=current_request_id())


__all__ = ["admin_router", "public_router"]
