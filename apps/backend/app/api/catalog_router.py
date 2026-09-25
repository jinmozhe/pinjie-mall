"""商品目标模型的品牌、属性、模板与规格转换接口。"""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.commerce_dependencies import AdminCommerce
from app.api.commerce_router import Page, PageSize
from app.api.dependencies import require_admin_csrf, require_permission
from app.core.batch import ActiveStatusBatch, BatchCompleted
from app.core.context import current_request_id
from app.core.pagination import PageResult
from app.core.response import ResponseModel, success_response
from app.domains.admin.permissions import PermissionCode
from app.domains.products.catalog_schemas import (
    AttributeInput,
    AttributeRead,
    AttributeUpdate,
    BrandInput,
    BrandRead,
    BrandUpdate,
    CandidateAppend,
    DescriptionSet,
    DescriptionUpdate,
    SpecificationConversion,
    StandardValueInput,
    StandardValueRead,
    StandardValueUpdate,
    TemplateRead,
    TemplateUpdate,
)
from app.domains.products.schemas import ProductRead

router = APIRouter(tags=["商品属性与品牌"])


@router.get(
    "/admin/brands",
    response_model=ResponseModel[PageResult[BrandRead]],
    summary="分页查看品牌",
    dependencies=[Depends(require_permission(PermissionCode.BRANDS_READ))],
)
async def brands(
    service: AdminCommerce, page: Page = 1, page_size: PageSize = 20
) -> ResponseModel[PageResult[BrandRead]]:
    return success_response(data=await service.brands(page, page_size), request_id=current_request_id())


@router.get(
    "/admin/brands/{brand_id}",
    response_model=ResponseModel[BrandRead],
    summary="查看品牌详情",
    dependencies=[Depends(require_permission(PermissionCode.BRANDS_READ))],
)
async def brand(brand_id: UUID, service: AdminCommerce) -> ResponseModel[BrandRead]:
    return success_response(data=await service.read_brand(brand_id), request_id=current_request_id())


@router.post(
    "/admin/brands",
    response_model=ResponseModel[BrandRead],
    status_code=201,
    summary="创建品牌",
    dependencies=[Depends(require_admin_csrf), Depends(require_permission(PermissionCode.BRANDS_CREATE))],
)
async def create_brand(payload: BrandInput, service: AdminCommerce) -> ResponseModel[BrandRead]:
    return success_response(data=await service.create_brand(payload), request_id=current_request_id())


@router.put(
    "/admin/brands/{brand_id}",
    response_model=ResponseModel[BrandRead],
    summary="修改品牌及启用状态",
    dependencies=[Depends(require_admin_csrf), Depends(require_permission(PermissionCode.BRANDS_UPDATE))],
)
async def update_brand(brand_id: UUID, payload: BrandUpdate, service: AdminCommerce) -> ResponseModel[BrandRead]:
    return success_response(data=await service.update_brand(brand_id, payload), request_id=current_request_id())


@router.get(
    "/admin/spec-attributes",
    response_model=ResponseModel[PageResult[AttributeRead]],
    summary="分页查看公共属性",
    dependencies=[Depends(require_permission(PermissionCode.SPEC_ATTRIBUTES_READ))],
)
async def attributes(
    service: AdminCommerce,
    page: Page = 1,
    page_size: PageSize = 20,
    search: Annotated[str | None, Query(max_length=100)] = None,
    value_type: Literal["text", "number", "select", "multi_select"] | None = None,
    is_active: bool | None = None,
) -> ResponseModel[PageResult[AttributeRead]]:
    return success_response(
        data=await service.attributes(
            page, page_size, search=search.strip() if search else None, value_type=value_type, is_active=is_active
        ),
        request_id=current_request_id(),
    )


@router.patch(
    "/admin/spec-attributes/status/batch",
    response_model=ResponseModel[BatchCompleted],
    summary="批量启停公共属性，停用影响引用商品可售性",
    dependencies=[Depends(require_admin_csrf), Depends(require_permission(PermissionCode.SPEC_ATTRIBUTES_UPDATE))],
)
async def attributes_status(payload: ActiveStatusBatch, service: AdminCommerce) -> ResponseModel[BatchCompleted]:
    return success_response(data=await service.set_attributes_active(payload), request_id=current_request_id())


@router.patch(
    "/admin/spec-attributes/{attribute_id}/values/status/batch",
    response_model=ResponseModel[BatchCompleted],
    summary="批量启停标准候选值，停用影响引用 SKU 可售性",
    dependencies=[Depends(require_admin_csrf), Depends(require_permission(PermissionCode.SPEC_ATTRIBUTES_UPDATE))],
)
async def values_status(
    attribute_id: UUID, payload: ActiveStatusBatch, service: AdminCommerce
) -> ResponseModel[BatchCompleted]:
    return success_response(
        data=await service.set_values_active(attribute_id, payload), request_id=current_request_id()
    )


@router.put(
    "/admin/products/{product_id}/description-attributes",
    response_model=ResponseModel[ProductRead],
    summary="原子维护描述属性集合，保留历史且不改变 SKU 或库存",
    dependencies=[Depends(require_admin_csrf), Depends(require_permission(PermissionCode.PRODUCTS_UPDATE))],
)
async def descriptions_set(
    product_id: UUID, payload: DescriptionSet, service: AdminCommerce
) -> ResponseModel[ProductRead]:
    return success_response(data=await service.save_descriptions(product_id, payload), request_id=current_request_id())


@router.post(
    "/admin/products/{product_id}/spec-attributes/{adoption_id}/values",
    response_model=ResponseModel[ProductRead],
    summary="向当前商品销售维度追加候选值，不重建 SKU",
    dependencies=[Depends(require_admin_csrf), Depends(require_permission(PermissionCode.PRODUCTS_UPDATE))],
)
async def candidates_append(
    product_id: UUID, adoption_id: UUID, payload: CandidateAppend, service: AdminCommerce
) -> ResponseModel[ProductRead]:
    return success_response(
        data=await service.add_candidates(product_id, adoption_id, payload), request_id=current_request_id()
    )


@router.get(
    "/admin/spec-attributes/{attribute_id}",
    response_model=ResponseModel[AttributeRead],
    summary="查看公共属性定义",
    dependencies=[Depends(require_permission(PermissionCode.SPEC_ATTRIBUTES_READ))],
)
async def attribute(attribute_id: UUID, service: AdminCommerce) -> ResponseModel[AttributeRead]:
    return success_response(data=await service.read_attribute(attribute_id), request_id=current_request_id())


@router.post(
    "/admin/spec-attributes",
    response_model=ResponseModel[AttributeRead],
    status_code=201,
    summary="创建公共属性",
    dependencies=[Depends(require_admin_csrf), Depends(require_permission(PermissionCode.SPEC_ATTRIBUTES_CREATE))],
)
async def create_attribute(payload: AttributeInput, service: AdminCommerce) -> ResponseModel[AttributeRead]:
    return success_response(data=await service.create_attribute(payload), request_id=current_request_id())


@router.put(
    "/admin/spec-attributes/{attribute_id}",
    response_model=ResponseModel[AttributeRead],
    summary="修改公共属性及启用状态",
    dependencies=[Depends(require_admin_csrf), Depends(require_permission(PermissionCode.SPEC_ATTRIBUTES_UPDATE))],
)
async def update_attribute(
    attribute_id: UUID, payload: AttributeUpdate, service: AdminCommerce
) -> ResponseModel[AttributeRead]:
    return success_response(data=await service.update_attribute(attribute_id, payload), request_id=current_request_id())


@router.get(
    "/admin/spec-attributes/{attribute_id}/values",
    response_model=ResponseModel[list[StandardValueRead]],
    summary="查看属性标准值",
    dependencies=[Depends(require_permission(PermissionCode.SPEC_ATTRIBUTES_READ))],
)
async def values(attribute_id: UUID, service: AdminCommerce) -> ResponseModel[list[StandardValueRead]]:
    return success_response(data=await service.values(attribute_id), request_id=current_request_id())


@router.post(
    "/admin/spec-attributes/{attribute_id}/values",
    response_model=ResponseModel[StandardValueRead],
    status_code=201,
    summary="创建属性标准值",
    dependencies=[Depends(require_admin_csrf), Depends(require_permission(PermissionCode.SPEC_ATTRIBUTES_UPDATE))],
)
async def create_value(
    attribute_id: UUID, payload: StandardValueInput, service: AdminCommerce
) -> ResponseModel[StandardValueRead]:
    return success_response(data=await service.create_value(attribute_id, payload), request_id=current_request_id())


@router.put(
    "/admin/spec-attributes/{attribute_id}/values/{value_id}",
    response_model=ResponseModel[StandardValueRead],
    summary="修改属性标准值及启用状态",
    dependencies=[Depends(require_admin_csrf), Depends(require_permission(PermissionCode.SPEC_ATTRIBUTES_UPDATE))],
)
async def update_value(
    attribute_id: UUID, value_id: UUID, payload: StandardValueUpdate, service: AdminCommerce
) -> ResponseModel[StandardValueRead]:
    return success_response(
        data=await service.update_value(attribute_id, value_id, payload), request_id=current_request_id()
    )


@router.get(
    "/admin/product-categories/{category_id}/attributes",
    response_model=ResponseModel[TemplateRead],
    summary="查看分类直接属性模板",
    dependencies=[Depends(require_permission(PermissionCode.PRODUCT_CATEGORIES_READ))],
)
async def template(category_id: UUID, service: AdminCommerce) -> ResponseModel[TemplateRead]:
    return success_response(data=await service.read_template(category_id), request_id=current_request_id())


@router.put(
    "/admin/product-categories/{category_id}/attributes",
    response_model=ResponseModel[TemplateRead],
    summary="原子替换分类直接属性模板",
    dependencies=[Depends(require_admin_csrf), Depends(require_permission(PermissionCode.PRODUCT_CATEGORIES_UPDATE))],
)
async def update_template(
    category_id: UUID, payload: TemplateUpdate, service: AdminCommerce
) -> ResponseModel[TemplateRead]:
    return success_response(data=await service.update_template(category_id, payload), request_id=current_request_id())


@router.post(
    "/admin/products/{product_id}/specification-conversions",
    response_model=ResponseModel[ProductRead],
    summary="原子转换规格并清退旧可用库存",
    description="归档旧 SKU 并保留预占。新 SKU 使用明确初始盘点，不自动复制旧库存。旧商品版本请求返回冲突。",
    dependencies=[Depends(require_admin_csrf), Depends(require_permission(PermissionCode.PRODUCTS_UPDATE))],
)
async def convert_specifications(
    product_id: UUID, payload: SpecificationConversion, service: AdminCommerce
) -> ResponseModel[ProductRead]:
    return success_response(
        data=await service.convert_specifications(product_id, payload), request_id=current_request_id()
    )


@router.put(
    "/admin/products/{product_id}/attribute-values/{adoption_id}",
    response_model=ResponseModel[ProductRead],
    summary="更新描述值并保留原采用历史",
    dependencies=[Depends(require_admin_csrf), Depends(require_permission(PermissionCode.PRODUCTS_UPDATE))],
)
async def update_description(
    product_id: UUID, adoption_id: UUID, payload: DescriptionUpdate, service: AdminCommerce
) -> ResponseModel[ProductRead]:
    return success_response(
        data=await service.update_description(product_id, adoption_id, payload), request_id=current_request_id()
    )
