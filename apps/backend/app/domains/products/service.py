from typing import Literal, cast
from uuid import UUID

from app.core.batch import ActiveStatusBatch, BatchCompleted
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.core.identifiers import new_uuid7
from app.core.pagination import PageResult
from app.db.models.product import Category, Product, ProductSku

from .repository import ProductRepository
from .schemas import (
    CategoryInput,
    CategoryRead,
    CategoryUpdate,
    CheckoutSku,
    ProductCreate,
    ProductRead,
    ProductStatusUpdate,
    ProductUpdate,
    PublicProductRead,
    SkuInput,
    SkuRead,
    SkuStatusBatch,
    SkuUpdate,
    validate_category_tree,
)


class ProductService:
    def __init__(self, repository: ProductRepository) -> None:
        self.repository = repository

    async def lock_changes(self) -> None:
        await self.repository.lock_catalog()

    async def checkout_skus(self, sku_ids: list[UUID]) -> list[CheckoutSku]:
        rows = await self.repository.checkout_skus(sku_ids)
        if len(rows) != len(set(sku_ids)):
            raise AppException(status_code=409, code=ErrorCode.CHECKOUT_INVALID, message="SKU 不存在")
        visible_categories = {row.id for row in await self.categories(public=True)}
        result: list[CheckoutSku] = []
        for sku, product in rows:
            if product.status != "on_sale" or not sku.is_active or product.category_id not in visible_categories:
                raise AppException(status_code=409, code=ErrorCode.CHECKOUT_INVALID, message="商品、分类或 SKU 不可售")
            result.append(
                CheckoutSku(
                    id=sku.id,
                    product_id=product.id,
                    code=sku.code,
                    specifications=sku.specifications,
                    price=sku.price,
                    weight_grams=sku.weight_grams,
                    product_name=product.name,
                    product_type=cast(Literal["physical", "virtual"], product.product_type),
                    product_revision=product.revision,
                    shipping_template_id=product.shipping_template_id,
                )
            )
        return result

    async def categories(self, *, public: bool = False) -> list[CategoryRead]:
        rows = await self.repository.categories()
        by_id = {row.id: row for row in rows}
        result: list[CategoryRead] = []
        for row in rows:
            if public:
                current: Category | None = row
                visible = True
                while current is not None:
                    if not current.is_active:
                        visible = False
                        break
                    current = by_id.get(current.parent_id) if current.parent_id is not None else None
                if not visible:
                    continue
            result.append(CategoryRead.model_validate(row))
        return result

    async def save_category(self, data: CategoryInput, category_id: UUID | None = None) -> CategoryRead:
        await self.repository.lock_catalog()
        rows = await self.repository.categories()
        if category_id is None:
            if len(rows) >= 1000:
                raise AppException(status_code=409, code=ErrorCode.CATEGORY_LIMIT, message="分类数量达到上限")
            row = Category(id=new_uuid7(), revision=1)
        else:
            found = next((item for item in rows if item.id == category_id), None)
            if found is None:
                raise AppException(status_code=404, code=ErrorCode.CATEGORY_NOT_FOUND, message="分类不存在")
            if not isinstance(data, CategoryUpdate) or found.revision != data.revision:
                raise AppException(status_code=409, code=ErrorCode.CATEGORY_REVISION_CONFLICT, message="分类已变更")
            row = found
            row.revision += 1
        parents = {item.id: item.parent_id for item in rows}
        parents[row.id] = data.parent_id
        try:
            validate_category_tree(parents)
        except ValueError as exc:
            raise AppException(status_code=409, code=ErrorCode.CATEGORY_TREE_REJECTED, message=str(exc)) from exc
        row.name, row.parent_id, row.sort_order, row.is_active = (
            data.name,
            data.parent_id,
            data.sort_order,
            data.is_active,
        )
        await self.repository.save(row)
        return CategoryRead.model_validate(row)

    async def _category(self, category_id: UUID) -> None:
        categories = {row.id: row for row in await self.repository.categories()}
        current: UUID | None = category_id
        while current is not None:
            category = categories.get(current)
            if category is None or not category.is_active:
                raise AppException(
                    status_code=409, code=ErrorCode.CATEGORY_UNAVAILABLE, message="分类或上级分类不存在或已停用"
                )
            current = category.parent_id

    async def _get(self, product_id: UUID, *, lock: bool = False) -> Product:
        row = await self.repository.get(product_id, lock=lock)
        if row is None:
            raise AppException(status_code=404, code=ErrorCode.PRODUCT_NOT_FOUND, message="商品不存在")
        return row

    async def read(self, product_id: UUID) -> ProductRead:
        row = await self._get(product_id)
        return ProductRead(
            id=row.id,
            name=row.name,
            description=row.description,
            product_type=cast(Literal["physical", "virtual"], row.product_type),
            category_id=row.category_id,
            shipping_template_id=row.shipping_template_id,
            status=cast(Literal["draft", "on_sale", "off_sale"], row.status),
            revision=row.revision,
            image_asset_ids=await self.repository.image_ids(row.id),
            skus=[SkuRead.model_validate(sku) for sku in await self.repository.skus(row.id)],
        )

    async def public_read(self, product_id: UUID) -> PublicProductRead:
        row = await self._get(product_id)
        if row.status != "on_sale":
            raise AppException(status_code=404, code=ErrorCode.PRODUCT_NOT_FOUND, message="商品不存在")
        visible_categories = {category.id for category in await self.categories(public=True)}
        if row.category_id not in visible_categories:
            raise AppException(status_code=404, code=ErrorCode.PRODUCT_NOT_FOUND, message="商品不存在")
        return PublicProductRead(
            id=row.id,
            name=row.name,
            description=row.description,
            product_type=cast(Literal["physical", "virtual"], row.product_type),
            category_id=row.category_id,
            images=await self.repository.image_urls(row.id),
            skus=[SkuRead.model_validate(sku) for sku in await self.repository.skus(row.id) if sku.is_active],
        )

    async def page(
        self,
        page: int,
        page_size: int,
        *,
        search: str | None = None,
        category_id: UUID | None = None,
        status: str | None = None,
        product_type: str | None = None,
    ) -> PageResult[ProductRead]:
        rows, total = await self.repository.page(
            page,
            page_size,
            search=search,
            category_id=category_id,
            status=status,
            product_type=product_type,
        )
        variants, image_ids, _ = await self.repository.details([row.id for row in rows])
        return PageResult[ProductRead].create(
            items=[
                ProductRead(
                    id=row.id,
                    name=row.name,
                    description=row.description,
                    product_type=cast(Literal["physical", "virtual"], row.product_type),
                    category_id=row.category_id,
                    shipping_template_id=row.shipping_template_id,
                    status=cast(Literal["draft", "on_sale", "off_sale"], row.status),
                    revision=row.revision,
                    image_asset_ids=image_ids[row.id],
                    skus=[SkuRead.model_validate(sku) for sku in variants[row.id]],
                )
                for row in rows
            ],
            page=page,
            page_size=page_size,
            total=total,
        )

    async def public_page(self, page: int, page_size: int) -> PageResult[PublicProductRead]:
        rows, total = await self.repository.page(page, page_size, public=True)
        variants, _, urls = await self.repository.details([row.id for row in rows])
        return PageResult[PublicProductRead].create(
            items=[
                PublicProductRead(
                    id=row.id,
                    name=row.name,
                    description=row.description,
                    product_type=cast(Literal["physical", "virtual"], row.product_type),
                    category_id=row.category_id,
                    images=urls[row.id],
                    skus=[SkuRead.model_validate(sku) for sku in variants[row.id] if sku.is_active],
                )
                for row in rows
            ],
            page=page,
            page_size=page_size,
            total=total,
        )

    async def create(self, data: ProductCreate) -> ProductRead:
        await self.repository.lock_catalog()
        await self._category(data.category_id)
        row = Product(
            id=new_uuid7(), **data.model_dump(exclude={"skus", "image_asset_ids"}), status="draft", revision=1
        )
        await self.repository.save(row)
        for sku in data.skus:
            await self._write_sku(row.id, sku)
        await self.repository.replace_images(row.id, data.image_asset_ids)
        return await self.read(row.id)

    async def set_categories_active(self, data: ActiveStatusBatch) -> BatchCompleted:
        await self.repository.lock_catalog()
        categories = {row.id: row for row in await self.repository.categories()}
        for target in sorted(data.targets, key=lambda item: item.id):
            row = categories.get(target.id)
            if row is None:
                raise AppException(status_code=404, code=ErrorCode.CATEGORY_NOT_FOUND, message="分类不存在")
            if row.revision != target.revision:
                raise AppException(
                    status_code=409, code=ErrorCode.CATEGORY_REVISION_CONFLICT, message="分类已变更，请刷新后重试"
                )
            row.is_active = data.is_active
            row.revision += 1
            await self.repository.save(row)
        return BatchCompleted(completed_count=len(data.targets))

    async def update(self, product_id: UUID, data: ProductUpdate) -> ProductRead:
        await self.repository.lock_catalog()
        row = await self._get(product_id, lock=True)
        self._check_revision(row, data.revision)
        await self._category(data.category_id)
        if data.product_type != row.product_type:
            raise AppException(status_code=409, code=ErrorCode.PRODUCT_TYPE_IMMUTABLE, message="商品类型创建后不能改变")
        row.name, row.description, row.category_id = data.name, data.description, data.category_id
        row.shipping_template_id = data.shipping_template_id
        row.revision += 1
        await self.repository.replace_images(product_id, data.image_asset_ids)
        await self.repository.save(row)
        if row.status == "on_sale":
            await self.validate_publish(product_id)
        return await self.read(product_id)

    async def write_sku(self, product_id: UUID, data: SkuUpdate, sku_id: UUID | None) -> ProductRead:
        await self.repository.lock_catalog()
        row = await self._get(product_id, lock=True)
        self._check_revision(row, data.revision)
        await self._write_sku(product_id, data, sku_id)
        row.revision += 1
        await self.repository.save(row)
        if row.status == "on_sale":
            await self.validate_publish(product_id)
        return await self.read(product_id)

    async def _write_sku(self, product_id: UUID, data: SkuInput, sku_id: UUID | None = None) -> None:
        rows = await self.repository.skus(product_id)
        if await self.repository.code_exists(data.code, sku_id):
            raise AppException(status_code=409, code=ErrorCode.SKU_CODE_CONFLICT, message="SKU 编码已使用")
        if any(row.id != sku_id and row.specifications == data.specifications for row in rows):
            raise AppException(status_code=409, code=ErrorCode.SKU_SPEC_CONFLICT, message="规格组合已存在")
        if sku_id is None:
            if len(rows) >= 100:
                raise AppException(status_code=409, code=ErrorCode.SKU_LIMIT, message="每商品最多一百个 SKU")
            row = ProductSku(id=new_uuid7(), product_id=product_id)
        else:
            found = next((row for row in rows if row.id == sku_id), None)
            if found is None:
                raise AppException(status_code=404, code=ErrorCode.SKU_NOT_FOUND, message="SKU 不属于此商品")
            row = found
        row.code, row.specifications, row.price = data.code, data.specifications, data.price
        row.weight_grams, row.is_active = data.weight_grams, data.is_active
        await self.repository.save(row)

    async def validate_publish(self, product_id: UUID) -> None:
        row = await self._get(product_id)
        await self._category(row.category_id)
        skus = [sku for sku in await self.repository.skus(product_id) if sku.is_active]
        if not skus or not await self.repository.image_ids(product_id):
            raise AppException(
                status_code=409, code=ErrorCode.PRODUCT_NOT_PUBLISHABLE, message="上架需要启用 SKU 和商品图片"
            )
        if row.product_type == "physical" and (
            row.shipping_template_id is None or any(sku.weight_grams <= 0 for sku in skus)
        ):
            raise AppException(
                status_code=409, code=ErrorCode.PRODUCT_NOT_PUBLISHABLE, message="实物商品上架需要运费模板和正重量"
            )
        if row.product_type == "virtual" and any(sku.weight_grams != 0 for sku in skus):
            raise AppException(status_code=409, code=ErrorCode.PRODUCT_NOT_PUBLISHABLE, message="虚拟商品重量必须为零")

    async def set_skus_active(self, product_id: UUID, data: SkuStatusBatch) -> ProductRead:
        await self.repository.lock_catalog()
        product = await self._get(product_id, lock=True)
        self._check_revision(product, data.revision)
        rows = {sku.id: sku for sku in await self.repository.skus(product_id)}
        if any(sku_id not in rows for sku_id in data.sku_ids):
            raise AppException(status_code=404, code=ErrorCode.SKU_NOT_FOUND, message="SKU 不属于此商品")
        for sku_id in sorted(data.sku_ids):
            rows[sku_id].is_active = data.is_active
            await self.repository.save(rows[sku_id])
        if product.status == "on_sale":
            await self.validate_publish(product_id)
        product.revision += 1
        await self.repository.save(product)
        return await self.read(product_id)

    async def set_status(self, product_id: UUID, data: ProductStatusUpdate) -> ProductRead:
        await self.repository.lock_catalog()
        row = await self._get(product_id, lock=True)
        self._check_revision(row, data.revision)
        if data.status == "on_sale":
            await self.validate_publish(product_id)
        row.status = data.status
        row.revision += 1
        await self.repository.save(row)
        return await self.read(product_id)

    @staticmethod
    def _check_revision(row: Product, revision: int) -> None:
        if row.revision != revision:
            raise AppException(
                status_code=409, code=ErrorCode.PRODUCT_REVISION_CONFLICT, message="商品已变更，请重新读取"
            )
