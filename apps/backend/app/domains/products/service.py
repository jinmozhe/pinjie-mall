from typing import Literal, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.batch import ActiveStatusBatch, BatchCompleted
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.core.identifiers import new_uuid7
from app.core.pagination import PageResult
from app.db.models.product import Category, Product

from .catalog_schemas import CandidateAppend, DescriptionSet, DescriptionUpdate, SpecificationConversion
from .catalog_service import catalog_conflict
from .repository import ProductRepository
from .schemas import (
    CategoryInput,
    CategoryRead,
    CategoryUpdate,
    CheckoutSku,
    ProductCreate,
    ProductDetailRead,
    ProductImageRead,
    ProductRead,
    ProductStatusUpdate,
    ProductUpdate,
    PublicDetailImageRead,
    PublicProductDetailRead,
    PublicProductRead,
    PublicSkuRead,
    SkuInput,
    SkuRead,
    SkuStatusBatch,
    SkuUpdate,
    validate_category_tree,
)
from .specification_service import SpecificationService


class ProductService(SpecificationService):
    def __init__(self, repository: ProductRepository) -> None:
        self.repository = repository

    @classmethod
    def for_session(cls, session: AsyncSession) -> "ProductService":
        return cls(ProductRepository(session))

    async def lock_changes(self) -> None:
        await self.repository.lock_catalog()

    async def checkout_skus(self, sku_ids: list[UUID]) -> list[CheckoutSku]:
        rows = await self.repository.checkout_skus(sorted(set(sku_ids), key=lambda item: item.hex))
        if len(rows) != len(set(sku_ids)):
            raise AppException(status_code=404, code=ErrorCode.SKU_NOT_FOUND, message="SKU 不存在")
        categories = {category.id: category for category in await self.repository.categories()}
        result: list[CheckoutSku] = []
        for sku, product in rows:
            if product.status != "on_sale":
                raise AppException(status_code=409, code=ErrorCode.CHECKOUT_INVALID, message="SKU 当前不可销售")
            category_id: UUID | None = product.category_id
            while category_id is not None:
                category = categories.get(category_id)
                if category is None or not category.is_active:
                    raise AppException(
                        status_code=409, code=ErrorCode.CATEGORY_UNAVAILABLE, message="商品分类当前不可用"
                    )
                category_id = category.parent_id
            if not await self.sku_is_available(
                sku, await self.repository.adoptions(product.id), await self.repository.sku_selections(product.id)
            ):
                raise AppException(status_code=409, code=ErrorCode.CHECKOUT_INVALID, message="SKU 当前不可销售")
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
            brand_id=row.brand_id,
            purchase_limit_quantity=row.purchase_limit_quantity,
            status=cast(Literal["draft", "on_sale", "off_sale"], row.status),
            revision=row.revision,
            image_asset_ids=await self.repository.image_ids(row.id),
            skus=await self._sku_reads(row.id),
            attributes=await self.adoption_reads(row.id),
        )

    async def detail_read(self, product_id: UUID) -> ProductDetailRead:
        product = await self.read(product_id)
        images = await self._image_reads(product_id, detail=False)
        details = await self._image_reads(product_id, detail=True)
        return ProductDetailRead(
            **product.model_dump(),
            image_assets=images,
            detail_image_asset_ids=[image.asset_id for image in details],
            detail_images=details,
        )

    async def _image_reads(self, product_id: UUID, *, detail: bool) -> list[ProductImageRead]:
        return [
            ProductImageRead(
                asset_id=asset.id,
                url=asset.url,
                original_name=asset.original_name,
                file_size=asset.file_size,
                width=asset.width,
                height=asset.height,
                frame_count=asset.frame_count,
            )
            for asset in await self.repository.image_assets(product_id, detail=detail)
        ]

    async def public_detail_read(self, product_id: UUID) -> PublicProductDetailRead:
        product = await self.public_read(product_id)
        details = await self._image_reads(product_id, detail=True)
        images: list[PublicDetailImageRead] = []
        for image in details:
            if image.width is None or image.height is None or image.frame_count != 1:
                raise AppException(
                    status_code=409,
                    code=ErrorCode.PRODUCT_IMAGE_REJECTED,
                    message="商品详情图片元数据无效，请联系管理员",
                )
            images.append(PublicDetailImageRead(url=image.url, width=image.width, height=image.height))
        return PublicProductDetailRead(**product.model_dump(), detail_images=images)

    async def public_read(self, product_id: UUID) -> PublicProductRead:
        row = await self._get(product_id)
        if row.status != "on_sale":
            raise AppException(status_code=404, code=ErrorCode.PRODUCT_NOT_FOUND, message="商品不存在")
        visible_categories = {category.id for category in await self.categories(public=True)}
        if row.category_id not in visible_categories:
            raise AppException(status_code=404, code=ErrorCode.PRODUCT_NOT_FOUND, message="商品不存在")
        adoptions = await self.repository.adoptions(row.id)
        selections = await self.repository.sku_selections(row.id)
        visible_skus = [
            PublicSkuRead.model_validate(sku)
            for sku in await self.repository.skus(row.id)
            if await self.sku_is_available(sku, adoptions, selections)
        ]
        return PublicProductRead(
            id=row.id,
            name=row.name,
            description=row.description,
            product_type=cast(Literal["physical", "virtual"], row.product_type),
            category_id=row.category_id,
            brand_id=row.brand_id,
            images=await self.repository.image_urls(row.id),
            skus=visible_skus,
            attributes=await self.adoption_reads(row.id, current_only=True),
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
        return PageResult[ProductRead].create(
            items=[await self.read(row.id) for row in rows],
            page=page,
            page_size=page_size,
            total=total,
        )

    async def public_page(self, page: int, page_size: int) -> PageResult[PublicProductRead]:
        rows, total = await self.repository.page(page, page_size, public=True)
        return PageResult[PublicProductRead].create(
            items=[await self.public_read(row.id) for row in rows],
            page=page,
            page_size=page_size,
            total=total,
        )

    async def create(self, data: ProductCreate) -> ProductRead:
        await self.repository.lock_catalog()
        await self._category(data.category_id)
        await self._brand(data.brand_id)
        row = Product(
            id=new_uuid7(),
            **data.model_dump(
                exclude={"skus", "image_asset_ids", "detail_image_asset_ids", "attributes", "category_revision"}
            ),
            status="draft",
            revision=1,
        )
        await self.repository.save(row)
        await self.build_specifications(row, data)
        await self.repository.replace_images(row.id, data.image_asset_ids)
        await self.repository.replace_detail_images(row.id, data.detail_image_asset_ids)
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
        if data.category_id != row.category_id:
            template = await self.repository.template(data.category_id)
            adoptions = {
                item.attribute_id: item
                for item in await self.repository.adoptions(row.id)
                if item.is_current and item.attribute_id is not None
            }
            if any(item.is_required and item.attribute_id not in adoptions for item in template) or any(
                item.attribute_id in adoptions
                and (
                    item.is_variant != adoptions[item.attribute_id].is_variant
                    or item.is_required != adoptions[item.attribute_id].is_required
                    or item.allow_custom_value != adoptions[item.attribute_id].allow_custom_value
                )
                for item in template
            ):
                raise catalog_conflict("新分类模板与当前采用不符，请先调整规格采用")
        if data.brand_id != row.brand_id:
            await self._brand(data.brand_id)
        row.name, row.description, row.category_id = data.name, data.description, data.category_id
        row.brand_id, row.purchase_limit_quantity = data.brand_id, data.purchase_limit_quantity
        row.revision += 1
        await self.repository.replace_images(product_id, data.image_asset_ids)
        await self.repository.replace_detail_images(product_id, data.detail_image_asset_ids)
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
        rows = [row for row in await self.repository.skus(product_id) if row.archived_at is None]
        if await self.repository.code_exists(data.code, sku_id):
            raise AppException(status_code=409, code=ErrorCode.SKU_CODE_CONFLICT, message="SKU 编码已使用")
        key, _, candidates = await self.combination(product_id, data.spec_value_ids)
        if any(row.id != sku_id and row.specification_key == key for row in rows):
            raise AppException(status_code=409, code=ErrorCode.SKU_SPEC_CONFLICT, message="规格组合已存在")
        if sku_id is None:
            if len(rows) >= 100:
                raise AppException(status_code=409, code=ErrorCode.SKU_LIMIT, message="每商品最多一百个 SKU")
            await self.insert_sku(
                product_id,
                data,
                data.spec_value_ids,
                max((row.sku_no for row in rows), default=0) + 1 if candidates else 0,
            )
            return
        else:
            found = next((row for row in rows if row.id == sku_id), None)
            if found is None:
                raise AppException(status_code=404, code=ErrorCode.SKU_NOT_FOUND, message="SKU 不属于此商品")
            row = found
            if row.specification_key != key:
                raise catalog_conflict("货品规格身份不可原位修改，请使用规格转换")
        self.set_sku_fields(row, data)
        await self.repository.save(row)

    async def validate_publish(self, product_id: UUID) -> None:
        row = await self._get(product_id)
        await self._category(row.category_id)
        all_skus = [sku for sku in await self.repository.skus(product_id) if sku.archived_at is None]
        adoptions = await self.repository.adoptions(product_id)
        selections = await self.repository.sku_selections(product_id)
        variants = [item for item in adoptions if item.is_current and item.is_variant]
        if (not variants and (len(all_skus) != 1 or all_skus[0].sku_no != 0)) or (
            variants and (not all_skus or any(sku.sku_no <= 0 for sku in all_skus))
        ):
            raise catalog_conflict("默认 SKU 与多规格集合不符合当前采用")
        for sku in all_skus:
            key, display, _ = await self.combination(
                product_id, [item.spec_value_id for item in selections if item.sku_id == sku.id]
            )
            if key != sku.specification_key or display != sku.specifications:
                raise catalog_conflict("SKU 规格关系与展示快照不一致")
        skus = [sku for sku in all_skus if await self.sku_is_available(sku, adoptions, selections)]
        if not skus or not await self.repository.image_ids(product_id):
            raise AppException(
                status_code=409, code=ErrorCode.PRODUCT_NOT_PUBLISHABLE, message="上架需要启用 SKU 和商品图片"
            )

    async def set_skus_active(self, product_id: UUID, data: SkuStatusBatch) -> ProductRead:
        await self.repository.lock_catalog()
        product = await self._get(product_id, lock=True)
        self._check_revision(product, data.revision)
        rows = {sku.id: sku for sku in await self.repository.skus(product_id) if sku.archived_at is None}
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

    async def _sku_reads(self, product_id: UUID) -> list[SkuRead]:
        selections = await self.repository.sku_selections(product_id)
        result: list[SkuRead] = []
        for sku in await self.repository.skus(product_id):
            item = SkuRead.model_validate(sku)
            item.spec_value_ids = [row.spec_value_id for row in selections if row.sku_id == sku.id]
            result.append(item)
        return result

    async def _brand(self, brand_id: UUID | None) -> None:
        if brand_id is not None:
            brand = await self.repository.brand(brand_id)
            if brand is None or not brand.is_active:
                raise catalog_conflict("新关联品牌必须存在且启用")

    async def convert_specifications(
        self, product_id: UUID, data: SpecificationConversion
    ) -> tuple[ProductRead, list[UUID]]:
        await self.repository.lock_catalog()
        product = await self._get(product_id, lock=True)
        self._check_revision(product, data.revision)
        await self._category(product.category_id)
        retired = await self.retire_specifications(product_id)
        await self.build_specifications(product, data)
        product.revision += 1
        await self.repository.save(product)
        if product.status == "on_sale":
            await self.validate_publish(product_id)
        return await self.read(product_id), retired

    async def save_descriptions(self, product_id: UUID, data: DescriptionSet) -> ProductRead:
        await self.repository.lock_catalog()
        product = await self._get(product_id, lock=True)
        self._check_revision(product, data.revision)
        await self.set_descriptions(product, data)
        product.revision += 1
        await self.repository.save(product)
        if product.status == "on_sale":
            await self.validate_publish(product_id)
        return await self.read(product_id)

    async def add_candidates(self, product_id: UUID, adoption_id: UUID, data: CandidateAppend) -> ProductRead:
        await self.repository.lock_catalog()
        product = await self._get(product_id, lock=True)
        self._check_revision(product, data.revision)
        await self.append_candidates(product, adoption_id, data)
        product.revision += 1
        await self.repository.save(product)
        return await self.read(product_id)

    async def update_description(self, product_id: UUID, adoption_id: UUID, data: DescriptionUpdate) -> ProductRead:
        await self.repository.lock_catalog()
        product = await self._get(product_id, lock=True)
        self._check_revision(product, data.revision)
        await self.replace_description(product, adoption_id, data)
        product.revision += 1
        await self.repository.save(product)
        if product.status == "on_sale":
            await self.validate_publish(product_id)
        return await self.read(product_id)

    async def require_current_sku(self, sku_id: UUID) -> None:
        await self.repository.lock_catalog()
        rows = await self.repository.checkout_skus([sku_id])
        if not rows or rows[0][0].archived_at is not None:
            raise catalog_conflict("SKU 不存在或已归档，不能人工调整库存")

    async def archived_sku_ids(self, sku_ids: list[UUID]) -> set[UUID]:
        await self.repository.lock_catalog()
        return {sku.id for sku, _ in await self.repository.checkout_skus(sku_ids) if sku.archived_at is not None}
