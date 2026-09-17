from collections.abc import Awaitable, Callable
from typing import TypeVar
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.core.pagination import PageResult
from app.db.repositories.commerce_access import CommerceAccessRepository
from app.db.transaction import transaction_scope
from app.domains.addresses import AddressInput, AddressRead, AddressService, AddressUpdate
from app.domains.admin.permissions import PERMISSION_CODES, PermissionCode
from app.domains.inventory import InventoryAdjustment, InventoryMovementRead, InventoryRead, InventoryService
from app.domains.products import (
    CategoryInput,
    CategoryRead,
    CategoryUpdate,
    ProductCreate,
    ProductRead,
    ProductService,
    ProductStatusUpdate,
    ProductUpdate,
    SkuUpdate,
)
from app.domains.products.schemas import PublicProductRead
from app.domains.shipping import ShippingService, ShippingTemplateInput, ShippingTemplateRead
from app.domains.shipping.schemas import FreightQuote, FreightQuoteInput, ShippingTemplateUpdate
from app.services.security_events import AuditCoordinator

T = TypeVar("T")


class CommerceService:
    """商品基础跨领域应用用例，管理写事务由审计协调器统一拥有。"""

    def __init__(
        self,
        *,
        products: ProductService,
        inventory: InventoryService,
        shipping: ShippingService,
        access: CommerceAccessRepository,
        audit: AuditCoordinator | None = None,
        actor_id: UUID | None = None,
    ) -> None:
        self.products, self.inventory, self.shipping = products, inventory, shipping
        self.access, self.audit, self.actor_id = access, audit, actor_id

    async def _write(
        self, permission: PermissionCode, target_id: UUID | None, operation: Callable[[], Awaitable[T]]
    ) -> T:
        if self.audit is None or self.actor_id is None:
            raise AppException(status_code=403, code=ErrorCode.PERMISSION_DENIED, message="需要管理员权限")
        actor_id = self.actor_id

        async def authorized() -> T:
            admin = await self.access.get_admin_for_update(actor_id)
            if admin is None or not admin.is_active or permission.value not in PERMISSION_CODES:
                raise AppException(status_code=403, code=ErrorCode.PERMISSION_DENIED, message="当前管理员权限已失效")
            granted = admin.is_superuser or any(
                role.is_active and any(item.is_active and item.code == permission.value for item in role.permissions)
                for role in admin.roles
            )
            if not granted:
                raise AppException(status_code=403, code=ErrorCode.PERMISSION_DENIED, message="当前管理员权限已失效")
            return await operation()

        return await self.audit.execute(
            action=permission.value,
            target_type=permission.value.split(":")[0],
            target_id=target_id,
            changed_fields={"operation": permission.value},
            operation=authorized,
        )

    def _actor(self) -> UUID:
        if self.actor_id is None:
            raise AppException(status_code=403, code=ErrorCode.PERMISSION_DENIED, message="需要管理员身份")
        return self.actor_id

    async def categories(self, *, public: bool = False) -> list[CategoryRead]:
        return await self.products.categories(public=public)

    async def create_category(self, data: CategoryInput) -> CategoryRead:
        return await self._write(
            PermissionCode.PRODUCT_CATEGORIES_CREATE, None, lambda: self.products.save_category(data)
        )

    async def update_category(self, category_id: UUID, data: CategoryUpdate) -> CategoryRead:
        return await self._write(
            PermissionCode.PRODUCT_CATEGORIES_UPDATE,
            category_id,
            lambda: self.products.save_category(data, category_id),
        )

    async def product_page(self, page: int, page_size: int) -> PageResult[ProductRead]:
        return await self.products.page(page, page_size)

    async def product_read(self, product_id: UUID) -> ProductRead:
        return await self.products.read(product_id)

    async def public_product_page(self, page: int, page_size: int) -> PageResult[PublicProductRead]:
        return await self.products.public_page(page, page_size)

    async def public_product_read(self, product_id: UUID) -> PublicProductRead:
        return await self.products.public_read(product_id)

    async def _product_dependencies(self, image_ids: list[UUID], shipping_id: UUID | None) -> None:
        await self.products.lock_changes()
        assets = await self.access.get_images_for_update(image_ids)
        if len(assets) != len(image_ids) or any(
            asset.uploader_type not in {"admin", "system"}
            or asset.mime_type not in {"image/jpeg", "image/png", "image/webp"}
            for asset in assets
        ):
            raise AppException(
                status_code=409, code=ErrorCode.PRODUCT_IMAGE_REJECTED, message="商品图片必须为现存管理端图片资产"
            )
        if shipping_id is not None:
            await self.shipping.require_active(shipping_id)

    async def create_product(self, data: ProductCreate) -> ProductRead:
        async def operation() -> ProductRead:
            await self._product_dependencies(data.image_asset_ids, data.shipping_template_id)
            result = await self.products.create(data)
            for sku in result.skus:
                await self.inventory.initialize(sku.id)
            return result

        return await self._write(PermissionCode.PRODUCTS_CREATE, None, operation)

    async def update_product(self, product_id: UUID, data: ProductUpdate) -> ProductRead:
        async def operation() -> ProductRead:
            await self._product_dependencies(data.image_asset_ids, data.shipping_template_id)
            return await self.products.update(product_id, data)

        return await self._write(PermissionCode.PRODUCTS_UPDATE, product_id, operation)

    async def write_sku(self, product_id: UUID, data: SkuUpdate, sku_id: UUID | None = None) -> ProductRead:
        async def operation() -> ProductRead:
            await self.products.lock_changes()
            before = await self.products.read(product_id)
            if before.shipping_template_id is not None:
                await self.shipping.require_active(before.shipping_template_id)
            result = await self.products.write_sku(product_id, data, sku_id)
            previous_ids = {sku.id for sku in before.skus}
            for sku in result.skus:
                if sku.id not in previous_ids:
                    await self.inventory.initialize(sku.id)
            return result

        return await self._write(PermissionCode.PRODUCTS_UPDATE, product_id, operation)

    async def set_product_status(self, product_id: UUID, data: ProductStatusUpdate) -> ProductRead:
        async def operation() -> ProductRead:
            await self.products.lock_changes()
            if data.status == "on_sale":
                product = await self.products.read(product_id)
                await self._product_dependencies(product.image_asset_ids, product.shipping_template_id)
            return await self.products.set_status(product_id, data)

        return await self._write(PermissionCode.PRODUCTS_UPDATE, product_id, operation)

    async def inventory_read(self, sku_id: UUID) -> InventoryRead:
        return await self.inventory.read(sku_id)

    async def adjust_inventory(self, sku_id: UUID, data: InventoryAdjustment) -> InventoryMovementRead:
        return await self._write(
            PermissionCode.INVENTORY_ADJUST, sku_id, lambda: self.inventory.adjust(sku_id, data, self._actor())
        )

    async def inventory_history(self, sku_id: UUID, page: int, page_size: int) -> PageResult[InventoryMovementRead]:
        return await self.inventory.history(sku_id, page, page_size)

    async def shipping_page(self, page: int, page_size: int) -> PageResult[ShippingTemplateRead]:
        return await self.shipping.page(page, page_size)

    async def shipping_read(self, template_id: UUID) -> ShippingTemplateRead:
        return await self.shipping.read(template_id)

    async def create_shipping(self, data: ShippingTemplateInput) -> ShippingTemplateRead:
        return await self._write(
            PermissionCode.SHIPPING_CREATE, None, lambda: self.shipping.create(data, self._actor())
        )

    async def update_shipping(self, template_id: UUID, data: ShippingTemplateUpdate) -> ShippingTemplateRead:
        return await self._write(
            PermissionCode.SHIPPING_UPDATE, template_id, lambda: self.shipping.update(template_id, data, self._actor())
        )

    async def shipping_quote(self, template_id: UUID, data: FreightQuoteInput) -> FreightQuote:
        return await self.shipping.quote(template_id, data)


class AddressApplicationService:
    def __init__(
        self, session: AsyncSession, addresses: AddressService, access: CommerceAccessRepository, user_id: UUID
    ) -> None:
        self.session, self.addresses, self.access, self.user_id = session, addresses, access, user_id

    async def list_addresses(self) -> list[AddressRead]:
        return await self.addresses.list_for_user(self.user_id)

    async def _write(self, operation: Callable[[], Awaitable[T]]) -> T:
        async with transaction_scope(self.session):
            user = await self.access.get_user_for_update(self.user_id)
            if user is None or not user.is_active or user.deleted_at is not None:
                raise AppException(status_code=403, code=ErrorCode.AUTH_ACCOUNT_DISABLED, message="用户已停用")
            return await operation()

    async def create(self, data: AddressInput) -> AddressRead:
        return await self._write(lambda: self.addresses.create(self.user_id, data))

    async def update(self, address_id: UUID, data: AddressUpdate) -> AddressRead:
        return await self._write(lambda: self.addresses.update(self.user_id, address_id, data))

    async def delete(self, address_id: UUID, revision: int) -> None:
        await self._write(lambda: self.addresses.delete(self.user_id, address_id, revision))
