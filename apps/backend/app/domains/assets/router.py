import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile

from app.api.dependencies import (
    AssetServiceDependency,
    AssetUploaderDependency,
    CurrentAdmin,
    require_admin_csrf,
    require_permission,
)
from app.core.context import current_request_id
from app.core.response import ResponseModel, success_response
from app.domains.admin.permissions import PermissionCode

from .schemas import AssetBulkDeleteIn, AssetBulkDeleteResult, AssetPage, AssetRead, UploaderType, UploadScene

router = APIRouter(prefix="/assets", tags=["文件资产"])


@router.post(
    "/upload",
    response_model=ResponseModel[AssetRead],
    status_code=201,
    summary="上传文件资产",
    description="按受控场景校验扩展名、真实文件头、体积与管理员上传权限后保存文件资产；消费者头像使用本人资料上传入口。",
)
async def upload_asset(
    file: Annotated[UploadFile, File(description="需要上传的文件")],
    scene: Annotated[UploadScene, Form(description="受控的文件使用场景")],
    uploader: AssetUploaderDependency,
    service: AssetServiceDependency,
) -> ResponseModel[AssetRead]:
    asset = await service.upload(
        source=file.file,
        original_name=file.filename or "",
        scene=scene,
        uploader=uploader,
    )
    return success_response(data=asset, request_id=current_request_id(), message="文件上传成功")


@router.get(
    "",
    response_model=ResponseModel[AssetPage],
    dependencies=[Depends(require_permission(PermissionCode.ASSETS_READ))],
    summary="获取文件资产列表",
)
async def list_assets(
    service: AssetServiceDependency,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    search: Annotated[str | None, Query(max_length=255)] = None,
    scene: Annotated[UploadScene | None, Query()] = None,
    uploader_type: Annotated[UploaderType | None, Query()] = None,
) -> ResponseModel[AssetPage]:
    return success_response(
        data=await service.list(
            page=page,
            page_size=page_size,
            search=search,
            scene=scene,
            uploader_type=uploader_type,
        ),
        request_id=current_request_id(),
    )


@router.delete(
    "/batch",
    response_model=ResponseModel[AssetBulkDeleteResult],
    dependencies=[Depends(require_permission(PermissionCode.ASSETS_DELETE))],
    summary="批量删除文件资产",
    description="通过权限、CSRF 与审计链原子删除明确选中的资产元数据和对应存储文件。",
)
async def delete_assets_bulk(
    payload: AssetBulkDeleteIn,
    service: AssetServiceDependency,
    current: Annotated[CurrentAdmin, Depends(require_admin_csrf)],
) -> ResponseModel[AssetBulkDeleteResult]:
    result = await service.delete_bulk(asset_ids=payload.asset_ids, actor_id=current.admin.id)
    return success_response(data=result, request_id=current_request_id(), message="文件资产批量删除成功")


@router.delete(
    "/{asset_id}",
    response_model=ResponseModel[bool],
    dependencies=[Depends(require_permission(PermissionCode.ASSETS_DELETE))],
    summary="删除文件资产",
    description="通过权限、CSRF 与审计链删除资产元数据和对应存储文件。",
)
async def delete_asset(
    asset_id: uuid.UUID,
    service: AssetServiceDependency,
    current: Annotated[CurrentAdmin, Depends(require_admin_csrf)],
) -> ResponseModel[bool]:
    await service.delete(asset_id=asset_id, actor_id=current.admin.id)
    return success_response(data=True, request_id=current_request_id(), message="文件资产删除成功")


__all__ = ["router"]
