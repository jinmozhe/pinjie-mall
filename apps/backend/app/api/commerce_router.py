from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.commerce_dependencies import AdminCommerce, PublicCommerce, UserAddresses
from app.api.dependencies import require_admin_csrf, require_permission, require_web_csrf
from app.core.batch import ActiveStatusBatch, BatchCompleted
from app.core.context import current_request_id
from app.core.pagination import PageResult
from app.core.response import ResponseModel, success_response
from app.domains.addresses import AddressInput, AddressRead, AddressUpdate
from app.domains.admin.permissions import PermissionCode
from app.domains.inventory import InventoryAdjustment, InventoryMovementRead, InventoryRead
from app.domains.products import (
    CategoryInput,
    CategoryRead,
    CategoryUpdate,
    ProductCreate,
    ProductRead,
    ProductStatusUpdate,
    ProductUpdate,
    SkuUpdate,
)
from app.domains.products.schemas import ProductStatusBatch, PublicProductRead, SkuStatusBatch
from app.domains.shipping import ShippingTemplateInput, ShippingTemplateRead
from app.domains.shipping.schemas import FreightQuote, FreightQuoteInput, ShippingTemplateUpdate

router = APIRouter(tags=["商城基础"])
Page = Annotated[int, Query(ge=1, description="页码，从一开始")]
PageSize = Annotated[int, Query(ge=1, le=100, description="每页数量")]


@router.get(
    "/admin/product-categories",
    response_model=ResponseModel[list[CategoryRead]],
    summary="查看全部商品分类",
    dependencies=[Depends(require_permission(PermissionCode.PRODUCT_CATEGORIES_READ))],
)
async def admin_categories(service: AdminCommerce) -> ResponseModel[list[CategoryRead]]:
    return success_response(data=await service.categories(), request_id=current_request_id())


@router.post(
    "/admin/product-categories",
    response_model=ResponseModel[CategoryRead],
    status_code=201,
    summary="创建商品分类",
    dependencies=[Depends(require_admin_csrf), Depends(require_permission(PermissionCode.PRODUCT_CATEGORIES_CREATE))],
)
async def create_category(payload: CategoryInput, service: AdminCommerce) -> ResponseModel[CategoryRead]:
    return success_response(data=await service.create_category(payload), request_id=current_request_id())


@router.put(
    "/admin/product-categories/{category_id}",
    response_model=ResponseModel[CategoryRead],
    summary="修改商品分类",
    dependencies=[Depends(require_admin_csrf), Depends(require_permission(PermissionCode.PRODUCT_CATEGORIES_UPDATE))],
)
async def update_category(
    category_id: UUID, payload: CategoryUpdate, service: AdminCommerce
) -> ResponseModel[CategoryRead]:
    return success_response(data=await service.update_category(category_id, payload), request_id=current_request_id())


@router.get(
    "/admin/products",
    response_model=ResponseModel[PageResult[ProductRead]],
    summary="分页查看商品",
    dependencies=[Depends(require_permission(PermissionCode.PRODUCTS_READ))],
)
async def admin_products(
    service: AdminCommerce,
    page: Page = 1,
    page_size: PageSize = 20,
    search: Annotated[str | None, Query(max_length=200, description="商品名称或 SKU 编码关键词")] = None,
    category_id: Annotated[UUID | None, Query(description="商品所属分类标识")] = None,
    status: Annotated[Literal["draft", "on_sale", "off_sale"] | None, Query(description="商品状态")] = None,
    product_type: Annotated[Literal["physical", "virtual"] | None, Query(description="商品类型")] = None,
) -> ResponseModel[PageResult[ProductRead]]:
    return success_response(
        data=await service.product_page(
            page,
            page_size,
            search=search,
            category_id=category_id,
            status=status,
            product_type=product_type,
        ),
        request_id=current_request_id(),
    )


@router.patch(
    "/admin/product-categories/status/batch",
    response_model=ResponseModel[BatchCompleted],
    summary="原子批量启停商品分类",
    dependencies=[Depends(require_admin_csrf), Depends(require_permission(PermissionCode.PRODUCT_CATEGORIES_UPDATE))],
)
async def categories_status_batch(payload: ActiveStatusBatch, service: AdminCommerce) -> ResponseModel[BatchCompleted]:
    return success_response(data=await service.categories_status_batch(payload), request_id=current_request_id())


@router.patch(
    "/admin/products/status/batch",
    response_model=ResponseModel[BatchCompleted],
    summary="原子批量上下架商品",
    dependencies=[Depends(require_admin_csrf), Depends(require_permission(PermissionCode.PRODUCTS_UPDATE))],
)
async def products_status_batch(payload: ProductStatusBatch, service: AdminCommerce) -> ResponseModel[BatchCompleted]:
    return success_response(data=await service.products_status_batch(payload), request_id=current_request_id())


@router.patch(
    "/admin/shipping-templates/status/batch",
    response_model=ResponseModel[BatchCompleted],
    summary="原子批量启停运费模板",
    dependencies=[Depends(require_admin_csrf), Depends(require_permission(PermissionCode.SHIPPING_UPDATE))],
)
async def shipping_status_batch(payload: ActiveStatusBatch, service: AdminCommerce) -> ResponseModel[BatchCompleted]:
    return success_response(data=await service.shipping_status_batch(payload), request_id=current_request_id())


@router.get(
    "/admin/products/{product_id}",
    response_model=ResponseModel[ProductRead],
    summary="查看商品及全部变体",
    dependencies=[Depends(require_permission(PermissionCode.PRODUCTS_READ))],
)
async def admin_product(product_id: UUID, service: AdminCommerce) -> ResponseModel[ProductRead]:
    return success_response(data=await service.product_read(product_id), request_id=current_request_id())


@router.post(
    "/admin/products",
    response_model=ResponseModel[ProductRead],
    status_code=201,
    summary="创建商品属性、变体与初始盘点库存",
    dependencies=[Depends(require_admin_csrf), Depends(require_permission(PermissionCode.PRODUCTS_CREATE))],
)
async def create_product(payload: ProductCreate, service: AdminCommerce) -> ResponseModel[ProductRead]:
    return success_response(data=await service.create_product(payload), request_id=current_request_id())


@router.put(
    "/admin/products/{product_id}",
    response_model=ResponseModel[ProductRead],
    summary="更新商品资料",
    dependencies=[Depends(require_admin_csrf), Depends(require_permission(PermissionCode.PRODUCTS_UPDATE))],
)
async def update_product(
    product_id: UUID, payload: ProductUpdate, service: AdminCommerce
) -> ResponseModel[ProductRead]:
    return success_response(data=await service.update_product(product_id, payload), request_id=current_request_id())


@router.put(
    "/admin/products/{product_id}/status",
    response_model=ResponseModel[ProductRead],
    summary="上架或下架商品",
    dependencies=[Depends(require_admin_csrf), Depends(require_permission(PermissionCode.PRODUCTS_UPDATE))],
)
async def set_product_status(
    product_id: UUID, payload: ProductStatusUpdate, service: AdminCommerce
) -> ResponseModel[ProductRead]:
    return success_response(data=await service.set_product_status(product_id, payload), request_id=current_request_id())


@router.post(
    "/admin/products/{product_id}/skus",
    response_model=ResponseModel[ProductRead],
    status_code=201,
    summary="增加稳定 SKU",
    dependencies=[Depends(require_admin_csrf), Depends(require_permission(PermissionCode.PRODUCTS_UPDATE))],
)
async def create_sku(product_id: UUID, payload: SkuUpdate, service: AdminCommerce) -> ResponseModel[ProductRead]:
    return success_response(data=await service.write_sku(product_id, payload), request_id=current_request_id())


@router.put(
    "/admin/products/{product_id}/skus/{sku_id}",
    response_model=ResponseModel[ProductRead],
    summary="原位更新 SKU",
    dependencies=[Depends(require_admin_csrf), Depends(require_permission(PermissionCode.PRODUCTS_UPDATE))],
)
async def update_sku(
    product_id: UUID, sku_id: UUID, payload: SkuUpdate, service: AdminCommerce
) -> ResponseModel[ProductRead]:
    return success_response(data=await service.write_sku(product_id, payload, sku_id), request_id=current_request_id())


@router.get(
    "/admin/inventory/{sku_id}",
    response_model=ResponseModel[InventoryRead],
    summary="查看 SKU 库存",
    dependencies=[Depends(require_permission(PermissionCode.INVENTORY_READ))],
)
async def inventory_read(sku_id: UUID, service: AdminCommerce) -> ResponseModel[InventoryRead]:
    return success_response(data=await service.inventory_read(sku_id), request_id=current_request_id())


@router.patch(
    "/admin/products/{product_id}/skus/status/batch",
    response_model=ResponseModel[ProductRead],
    summary="原子批量启停商品变体",
    dependencies=[Depends(require_admin_csrf), Depends(require_permission(PermissionCode.PRODUCTS_UPDATE))],
)
async def skus_status_batch(
    product_id: UUID, payload: SkuStatusBatch, service: AdminCommerce
) -> ResponseModel[ProductRead]:
    return success_response(data=await service.skus_status_batch(product_id, payload), request_id=current_request_id())


@router.post(
    "/admin/inventory/{sku_id}/adjustments",
    response_model=ResponseModel[InventoryMovementRead],
    summary="幂等调整库存",
    dependencies=[Depends(require_admin_csrf), Depends(require_permission(PermissionCode.INVENTORY_ADJUST))],
)
async def inventory_adjust(
    sku_id: UUID, payload: InventoryAdjustment, service: AdminCommerce
) -> ResponseModel[InventoryMovementRead]:
    return success_response(data=await service.adjust_inventory(sku_id, payload), request_id=current_request_id())


@router.get(
    "/admin/inventory/{sku_id}/movements",
    response_model=ResponseModel[PageResult[InventoryMovementRead]],
    summary="查看库存流水",
    dependencies=[Depends(require_permission(PermissionCode.INVENTORY_READ))],
)
async def inventory_history(
    sku_id: UUID, service: AdminCommerce, page: Page = 1, page_size: PageSize = 20
) -> ResponseModel[PageResult[InventoryMovementRead]]:
    return success_response(
        data=await service.inventory_history(sku_id, page, page_size), request_id=current_request_id()
    )


@router.get(
    "/admin/shipping-templates",
    response_model=ResponseModel[PageResult[ShippingTemplateRead]],
    summary="查看运费模板",
    dependencies=[Depends(require_permission(PermissionCode.SHIPPING_READ))],
)
async def shipping_page(
    service: AdminCommerce, page: Page = 1, page_size: PageSize = 20
) -> ResponseModel[PageResult[ShippingTemplateRead]]:
    return success_response(data=await service.shipping_page(page, page_size), request_id=current_request_id())


@router.get(
    "/admin/shipping-templates/{template_id}",
    response_model=ResponseModel[ShippingTemplateRead],
    summary="查看运费模板详情",
    dependencies=[Depends(require_permission(PermissionCode.SHIPPING_READ))],
)
async def shipping_read(template_id: UUID, service: AdminCommerce) -> ResponseModel[ShippingTemplateRead]:
    return success_response(data=await service.shipping_read(template_id), request_id=current_request_id())


@router.post(
    "/admin/shipping-templates",
    response_model=ResponseModel[ShippingTemplateRead],
    status_code=201,
    summary="创建运费模板",
    dependencies=[Depends(require_admin_csrf), Depends(require_permission(PermissionCode.SHIPPING_CREATE))],
)
async def shipping_create(
    payload: ShippingTemplateInput, service: AdminCommerce
) -> ResponseModel[ShippingTemplateRead]:
    return success_response(data=await service.create_shipping(payload), request_id=current_request_id())


@router.put(
    "/admin/shipping-templates/{template_id}",
    response_model=ResponseModel[ShippingTemplateRead],
    summary="更新运费模板",
    dependencies=[Depends(require_admin_csrf), Depends(require_permission(PermissionCode.SHIPPING_UPDATE))],
)
async def shipping_update(
    template_id: UUID, payload: ShippingTemplateUpdate, service: AdminCommerce
) -> ResponseModel[ShippingTemplateRead]:
    return success_response(data=await service.update_shipping(template_id, payload), request_id=current_request_id())


@router.post(
    "/admin/shipping-templates/{template_id}/quote",
    response_model=ResponseModel[FreightQuote],
    summary="试算运费",
    dependencies=[Depends(require_admin_csrf), Depends(require_permission(PermissionCode.SHIPPING_READ))],
)
async def shipping_quote(
    template_id: UUID, payload: FreightQuoteInput, service: AdminCommerce
) -> ResponseModel[FreightQuote]:
    return success_response(data=await service.shipping_quote(template_id, payload), request_id=current_request_id())


@router.get("/product-categories", response_model=ResponseModel[list[CategoryRead]], summary="查看启用商品分类")
async def public_categories(service: PublicCommerce) -> ResponseModel[list[CategoryRead]]:
    return success_response(data=await service.categories(public=True), request_id=current_request_id())


@router.get("/products", response_model=ResponseModel[PageResult[PublicProductRead]], summary="查看上架商品")
async def public_products(
    service: PublicCommerce, page: Page = 1, page_size: PageSize = 20
) -> ResponseModel[PageResult[PublicProductRead]]:
    return success_response(data=await service.public_product_page(page, page_size), request_id=current_request_id())


@router.get("/products/{product_id}", response_model=ResponseModel[PublicProductRead], summary="查看上架商品详情")
async def public_product(product_id: UUID, service: PublicCommerce) -> ResponseModel[PublicProductRead]:
    return success_response(data=await service.public_product_read(product_id), request_id=current_request_id())


@router.get("/addresses", response_model=ResponseModel[list[AddressRead]], summary="查看本人收货地址")
async def addresses_list(service: UserAddresses) -> ResponseModel[list[AddressRead]]:
    return success_response(data=await service.list_addresses(), request_id=current_request_id())


@router.post(
    "/addresses",
    response_model=ResponseModel[AddressRead],
    status_code=201,
    summary="新增本人收货地址",
    dependencies=[Depends(require_web_csrf)],
)
async def address_create(payload: AddressInput, service: UserAddresses) -> ResponseModel[AddressRead]:
    return success_response(data=await service.create(payload), request_id=current_request_id())


@router.put(
    "/addresses/{address_id}",
    response_model=ResponseModel[AddressRead],
    summary="更新本人收货地址",
    dependencies=[Depends(require_web_csrf)],
)
async def address_update(
    address_id: UUID, payload: AddressUpdate, service: UserAddresses
) -> ResponseModel[AddressRead]:
    return success_response(data=await service.update(address_id, payload), request_id=current_request_id())


@router.delete(
    "/addresses/{address_id}",
    response_model=ResponseModel[None],
    summary="删除本人收货地址",
    dependencies=[Depends(require_web_csrf)],
)
async def address_delete(
    address_id: UUID, revision: Annotated[int, Query(gt=0)], service: UserAddresses
) -> ResponseModel[None]:
    await service.delete(address_id, revision)
    return success_response(data=None, request_id=current_request_id())
