from decimal import Decimal, InvalidOperation
from unicodedata import normalize
from uuid import UUID

from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.core.identifiers import new_uuid7
from app.core.pagination import PageResult
from app.db.models.catalog import (
    Brand,
    CategorySpecAttribute,
    ProductSpecAttribute,
    SpecAttribute,
    SpecAttributeValue,
)

from .catalog_schemas import (
    AdoptionInput,
    AdoptionRead,
    AttributeInput,
    AttributeRead,
    AttributeUpdate,
    AttributeValidation,
    BrandInput,
    BrandRead,
    BrandUpdate,
    CandidateRead,
    StandardValueInput,
    StandardValueRead,
    StandardValueUpdate,
    TemplateItem,
    TemplateRead,
    TemplateUpdate,
)
from .repository import ProductRepository


def catalog_conflict(message: str) -> AppException:
    return AppException(status_code=409, code=ErrorCode.CATALOG_CONFLICT, message=message)


def normalized_text(value: str) -> str:
    return normalize("NFC", value).strip()


def specification_key(pairs: list[tuple[UUID, UUID | None, UUID]]) -> str:
    """维度 ID 为公共属性 ID 或商品自建采用 ID，文本不参与身份。"""
    if not pairs:
        return "default"
    if len({item[0] for item in pairs}) != len(pairs):
        raise catalog_conflict("每个规格维度只能选择一个候选值")
    result = "|".join(
        f"{dimension}={'std:' + str(standard) if standard is not None else 'custom:' + str(candidate)}"
        for dimension, standard, candidate in sorted(pairs, key=lambda item: str(item[0]))
    )
    if len(result) > 1000:
        raise catalog_conflict("规格组合标识超过长度限制")
    return result


class CatalogService:
    def __init__(self, repository: ProductRepository) -> None:
        self.repository = repository

    async def brands(self, page: int, page_size: int) -> PageResult[BrandRead]:
        rows, total = await self.repository.brand_page(page, page_size)
        return PageResult[BrandRead].create(
            items=[BrandRead.model_validate(row) for row in rows], total=total, page=page, page_size=page_size
        )

    async def read_brand(self, brand_id: UUID) -> BrandRead:
        row = await self.repository.brand(brand_id)
        if row is None:
            raise AppException(status_code=404, code=ErrorCode.NOT_FOUND, message="品牌不存在")
        return BrandRead.model_validate(row)

    async def save_brand(self, data: BrandInput, brand_id: UUID | None = None) -> BrandRead:
        await self.repository.lock_catalog()
        if brand_id is None:
            row = Brand(id=new_uuid7(), revision=1)
        else:
            found = await self.repository.brand(brand_id)
            if found is None:
                raise AppException(status_code=404, code=ErrorCode.NOT_FOUND, message="品牌不存在")
            if not isinstance(data, BrandUpdate) or data.revision != found.revision:
                raise catalog_conflict("品牌版本已变更")
            row = found
            row.revision += 1
        row.name, row.logo_asset_id, row.description = data.name, data.logo_asset_id, data.description
        row.is_active, row.sort_order = data.is_active, data.sort_order
        await self.repository.save_entity(row)
        return BrandRead.model_validate(row)

    async def attributes(self, page: int, page_size: int) -> PageResult[AttributeRead]:
        rows, total = await self.repository.attribute_page(page, page_size)
        return PageResult[AttributeRead].create(
            items=[AttributeRead.model_validate(row) for row in rows], total=total, page=page, page_size=page_size
        )

    async def require_attribute(self, attribute_id: UUID) -> SpecAttribute:
        row = await self.repository.attribute(attribute_id)
        if row is None:
            raise AppException(status_code=404, code=ErrorCode.NOT_FOUND, message="公共属性不存在")
        return row

    async def read_attribute(self, attribute_id: UUID) -> AttributeRead:
        return AttributeRead.model_validate(await self.require_attribute(attribute_id))

    async def save_attribute(self, data: AttributeInput, attribute_id: UUID | None = None) -> AttributeRead:
        await self.repository.lock_catalog()
        duplicate = await self.repository.attribute_by_code(data.code)
        if duplicate is not None and duplicate.id != attribute_id:
            raise catalog_conflict("公共属性编码已存在")
        if attribute_id is None:
            row = SpecAttribute(id=new_uuid7(), revision=1)
        else:
            row = await self.require_attribute(attribute_id)
            if not isinstance(data, AttributeUpdate) or data.revision != row.revision:
                raise catalog_conflict("公共属性版本已变更")
            row.revision += 1
        row.code, row.name, row.value_type, row.unit = data.code, data.name, data.value_type, data.unit
        row.validation = data.validation.model_dump(mode="json", exclude_none=True)
        row.sort_order, row.is_active = data.sort_order, data.is_active
        await self.repository.save_entity(row)
        return AttributeRead.model_validate(row)

    async def values(self, attribute_id: UUID) -> list[StandardValueRead]:
        await self.require_attribute(attribute_id)
        return [StandardValueRead.model_validate(row) for row in await self.repository.standard_values(attribute_id)]

    async def save_value(
        self, attribute_id: UUID, data: StandardValueInput, value_id: UUID | None = None
    ) -> StandardValueRead:
        await self.repository.lock_catalog()
        attribute = await self.require_attribute(attribute_id)
        if attribute.revision != data.attribute_revision:
            raise catalog_conflict("公共属性版本已变更")
        if attribute.value_type not in {"select", "multi_select"}:
            raise catalog_conflict("只有枚举属性可以维护标准候选值")
        values = await self.repository.standard_values(attribute_id)
        if any(row.code == data.code and row.id != value_id for row in values):
            raise catalog_conflict("同属性下候选编码已存在")
        if value_id is None:
            if len(values) >= 100:
                raise catalog_conflict("每个公共属性最多一百个标准候选值")
            row = SpecAttributeValue(id=new_uuid7(), attribute_id=attribute_id, revision=1)
        else:
            found = next((item for item in values if item.id == value_id), None)
            if found is None:
                raise AppException(status_code=404, code=ErrorCode.NOT_FOUND, message="标准值不属于此属性")
            row = found
            if not isinstance(data, StandardValueUpdate) or row.revision != data.revision:
                raise catalog_conflict("标准候选值版本已变更")
            row.revision += 1
        row.code, row.name, row.sort_order, row.is_active = data.code, data.name, data.sort_order, data.is_active
        attribute.revision += 1
        await self.repository.save_entity(row)
        return StandardValueRead.model_validate(row)

    async def read_template(self, category_id: UUID) -> TemplateRead:
        category = next((item for item in await self.repository.categories() if item.id == category_id), None)
        if category is None:
            raise AppException(status_code=404, code=ErrorCode.CATEGORY_NOT_FOUND, message="分类不存在")
        rows = await self.repository.template(category_id)
        return TemplateRead(
            category_id=category_id,
            revision=category.revision,
            attributes=[TemplateItem.model_validate(row, from_attributes=True) for row in rows],
        )

    async def save_template(self, category_id: UUID, data: TemplateUpdate) -> TemplateRead:
        await self.repository.lock_catalog()
        categories = {row.id: row for row in await self.repository.categories()}
        category = categories.get(category_id)
        if category is None:
            raise AppException(status_code=404, code=ErrorCode.CATEGORY_NOT_FOUND, message="分类不存在")
        if data.revision != category.revision:
            raise catalog_conflict("分类及模板版本已变更")
        for item in sorted(data.attributes, key=lambda item: item.attribute_id):
            attribute = await self.require_attribute(item.attribute_id)
            if not attribute.is_active or (item.is_variant and attribute.value_type != "select"):
                raise catalog_conflict("模板必须引用启用属性，销售规格必须为单选")
            if not item.is_variant and item.allow_custom_value:
                raise catalog_conflict("描述枚举不支持局部候选值")
        await self.repository.replace_template(
            category_id,
            [CategorySpecAttribute(category_id=category_id, **item.model_dump()) for item in data.attributes],
        )
        category.revision += 1
        await self.repository.save(category)
        return await self.read_template(category_id)

    async def adoption_reads(self, product_id: UUID, *, current_only: bool = False) -> list[AdoptionRead]:
        candidates = await self.repository.candidates(product_id)
        descriptions = {row.adoption_id: row for row in await self.repository.descriptions(product_id)}
        result: list[AdoptionRead] = []
        for row in await self.repository.adoptions(product_id):
            if current_only and not row.is_current:
                continue
            item = AdoptionRead.model_validate(row)
            item.candidates = [
                CandidateRead.model_validate(value) for value in candidates if value.adoption_id == row.id
            ]
            description = descriptions.get(row.id)
            if description is not None:
                # 冻结的值仅有字符串与字符串数组，验证存量而不隐式猜测格式。
                item = AdoptionRead.model_validate(
                    {**item.model_dump(), "value": description.value, "display_snapshot": description.display_snapshot}
                )
            result.append(item)
        return result

    async def make_adoption(
        self,
        product_id: UUID,
        category_id: UUID,
        category_revision: int,
        version: int,
        data: AdoptionInput,
        template: CategorySpecAttribute | None,
    ) -> ProductSpecAttribute:
        if data.attribute_id is not None:
            attribute = await self.require_attribute(data.attribute_id)
            if not attribute.is_active or attribute.revision != data.source_attribute_revision:
                raise catalog_conflict("公共属性已停用或版本已变更，请重新读取")
            name, value_type, unit, validation = (
                attribute.name,
                attribute.value_type,
                attribute.unit,
                attribute.validation,
            )
        else:
            if data.name is None or data.value_type is None or data.validation is None:
                raise catalog_conflict("商品自建属性定义不完整")
            name, value_type, unit = data.name, data.value_type, data.unit
            validation = data.validation.model_dump(mode="json", exclude_none=True)
        if data.is_variant and value_type != "select":
            raise catalog_conflict("销售规格只能采用单选属性")
        if template is not None and (
            template.is_variant != data.is_variant or template.is_required != data.is_required
        ):
            raise catalog_conflict("商品采用必须遵守直接分类模板的销售及必填规则")
        row = ProductSpecAttribute(
            id=new_uuid7(),
            product_id=product_id,
            attribute_id=data.attribute_id,
            adoption_version=version,
            name_snapshot=normalized_text(name),
            value_type_snapshot=value_type,
            unit_snapshot=unit,
            validation_snapshot=validation,
            source_category_id=category_id if template is not None else None,
            source_category_revision=category_revision if template is not None else None,
            source_attribute_revision=data.source_attribute_revision,
            is_required=data.is_required,
            is_variant=data.is_variant,
            is_current=True,
            allow_custom_value=data.attribute_id is None or (template is not None and template.allow_custom_value),
        )
        return row

    async def description_value(
        self, adoption: ProductSpecAttribute, value: str | list[UUID] | None
    ) -> tuple[str | list[str] | None, dict[str, str]]:
        rules = AttributeValidation.model_validate(adoption.validation_snapshot)
        rules.validate_type(adoption.value_type_snapshot)
        if value is None:
            if adoption.is_required:
                raise catalog_conflict("必填描述属性缺少值")
            return None, {}
        if adoption.value_type_snapshot == "text":
            if (
                not isinstance(value, str)
                or rules.max_length is None
                or len(value) > rules.max_length
                or (adoption.is_required and not value.strip())
            ):
                raise catalog_conflict("文本描述长度或类型无效")
            return value, {}
        if adoption.value_type_snapshot == "number":
            if not isinstance(value, str):
                raise catalog_conflict("数值描述必须使用十进制字符串")
            try:
                number = Decimal(value)
            except InvalidOperation as exc:
                raise catalog_conflict("数值描述格式无效") from exc
            if not number.is_finite() or rules.min is None or rules.max is None or rules.decimal_places is None:
                raise catalog_conflict("数值描述或验证规则无效")
            exponent = number.as_tuple().exponent
            if (
                not rules.min <= number <= rules.max
                or not isinstance(exponent, int)
                or exponent < -rules.decimal_places
            ):
                raise catalog_conflict("数值描述超出范围或精度")
            return format(number, "f"), {}
        if adoption.attribute_id is None:
            raise catalog_conflict("描述枚举必须引用公共属性")
        if adoption.value_type_snapshot == "select":
            if not isinstance(value, str):
                raise catalog_conflict("单选描述必须使用标准值 UUID")
            try:
                selected = [UUID(value)]
            except ValueError as exc:
                raise catalog_conflict("单选描述标识无效") from exc
        else:
            if (
                not isinstance(value, list)
                or rules.max_selected is None
                or len(value) > rules.max_selected
                or (adoption.is_required and not value)
            ):
                raise catalog_conflict("多选描述数量或类型无效")
            selected = value
        if len(set(selected)) != len(selected):
            raise catalog_conflict("描述标准值不能重复")
        snapshot: dict[str, str] = {}
        for value_id in selected:
            standard = await self.repository.standard_value(value_id)
            if standard is None or standard.attribute_id != adoption.attribute_id or not standard.is_active:
                raise catalog_conflict("描述标准值不存在、归属错误或已停用")
            snapshot[str(value_id)] = standard.name
        result = [str(value_id) for value_id in selected]
        return (result[0] if adoption.value_type_snapshot == "select" else result), snapshot
