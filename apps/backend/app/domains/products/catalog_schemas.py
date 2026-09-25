"""商品字典及冻结采用的边界契约。"""

from decimal import Decimal
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

Money = Annotated[Decimal, Field(ge=0, max_digits=15, decimal_places=2, allow_inf_nan=False)]
ValueType = Literal["text", "number", "select", "multi_select"]


class CatalogInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class AttributeValidation(CatalogInput):
    schema_version: Literal[1] = 1
    max_length: int | None = Field(default=None, ge=1, le=20000)
    decimal_places: int | None = Field(default=None, ge=0, le=6)
    min: Decimal | None = Field(default=None, allow_inf_nan=False)
    max: Decimal | None = Field(default=None, allow_inf_nan=False)
    max_selected: int | None = Field(default=None, ge=1, le=100)

    def validate_type(self, value_type: str) -> None:
        fields = self.model_dump(exclude_none=True)
        expected = {
            "text": {"schema_version", "max_length"},
            "number": {"schema_version", "decimal_places", "min", "max"},
            "select": {"schema_version"},
            "multi_select": {"schema_version", "max_selected"},
        }[value_type]
        if set(fields) != expected:
            raise ValueError("验证对象必须完整且仅包含当前属性类型的字段")
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError("数值属性最小值不能超过最大值")


class BrandInput(CatalogInput):
    name: str = Field(min_length=1, max_length=100)
    logo_asset_id: UUID | None = None
    description: str = Field(default="", max_length=20000)
    sort_order: int | None = Field(default=None, ge=0)
    is_active: bool = Field(default=True, strict=True)


class BrandUpdate(BrandInput):
    revision: int = Field(gt=0)


class BrandRead(BrandInput):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    revision: int


class AttributeInput(CatalogInput):
    code: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=100)
    value_type: ValueType
    unit: str | None = Field(default=None, min_length=1, max_length=32)
    validation: AttributeValidation
    sort_order: int | None = Field(default=None, ge=0)
    is_active: bool = Field(default=True, strict=True)

    @model_validator(mode="after")
    def type_rules(self) -> Self:
        self.validation.validate_type(self.value_type)
        if self.unit is not None and self.value_type != "number":
            raise ValueError("只有数值属性可以指定单位")
        return self


class AttributeUpdate(AttributeInput):
    revision: int = Field(gt=0)


class AttributeRead(AttributeInput):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    revision: int


class StandardValueInput(CatalogInput):
    attribute_revision: int = Field(gt=0, description="所属公共属性当前版本")
    code: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=100)
    sort_order: int | None = Field(default=None, ge=0)
    is_active: bool = Field(default=True, strict=True)


class StandardValueUpdate(StandardValueInput):
    revision: int = Field(gt=0)


class StandardValueRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    attribute_id: UUID
    code: str
    name: str
    sort_order: int | None
    is_active: bool
    revision: int


class TemplateItem(CatalogInput):
    attribute_id: UUID
    is_variant: bool = Field(default=False, strict=True)
    is_required: bool = Field(default=False, strict=True)
    sort_order: int | None = Field(default=None, ge=0)
    allow_custom_value: bool = Field(default=False, strict=True)


class TemplateUpdate(CatalogInput):
    revision: int = Field(gt=0, description="分类当前版本")
    attributes: list[TemplateItem] = Field(max_length=50)

    @model_validator(mode="after")
    def unique_attributes(self) -> Self:
        if len({item.attribute_id for item in self.attributes}) != len(self.attributes):
            raise ValueError("分类模板属性不能重复")
        if sum(item.is_variant for item in self.attributes) > 10:
            raise ValueError("销售规格最多十个维度")
        return self


class TemplateRead(BaseModel):
    category_id: UUID
    revision: int
    attributes: list[TemplateItem]


class CandidateInput(CatalogInput):
    key: str = Field(min_length=1, max_length=64, description="本次请求内候选值引用键，不是数据库 ID")
    value_id: UUID | None = None
    display_value: str | None = Field(default=None, min_length=1, max_length=100)

    @model_validator(mode="after")
    def source(self) -> Self:
        if (self.value_id is None) == (self.display_value is None):
            raise ValueError("候选值必须且只能选择公共值或输入局部文本")
        return self


class AdoptionInput(CatalogInput):
    key: str = Field(min_length=1, max_length=64, description="本次请求内属性引用键")
    attribute_id: UUID | None = None
    source_attribute_revision: int | None = Field(default=None, gt=0)
    name: str | None = Field(default=None, min_length=1, max_length=100)
    value_type: ValueType | None = None
    unit: str | None = Field(default=None, min_length=1, max_length=32)
    validation: AttributeValidation | None = None
    is_variant: bool = Field(default=False, strict=True)
    is_required: bool = Field(default=False, strict=True)
    candidates: list[CandidateInput] = Field(default_factory=list, max_length=100)
    value: str | list[UUID] | None = Field(
        default=None, description="描述值；数值为十进制字符串，单选为标准值 UUID 字符串"
    )

    @model_validator(mode="after")
    def validate_source(self) -> Self:
        if self.attribute_id is None:
            if self.name is None or self.value_type is None or self.validation is None:
                raise ValueError("商品自建属性必须指定名称、类型及验证对象")
            if self.source_attribute_revision is not None:
                raise ValueError("商品自建属性没有公共来源版本")
            self.validation.validate_type(self.value_type)
            if self.unit is not None and self.value_type != "number":
                raise ValueError("只有数值属性可以指定单位")
            if not self.is_variant and self.value_type in {"select", "multi_select"}:
                raise ValueError("描述枚举必须引用公共属性及标准值")
        elif self.source_attribute_revision is None or any(
            value is not None for value in (self.name, self.value_type, self.unit, self.validation)
        ):
            raise ValueError("公共属性必须提供来源版本，名称及类型由服务端冻结")
        if self.is_variant:
            if not self.candidates or self.value is not None:
                raise ValueError("销售规格必须提供候选值且不能提交描述值")
            if self.value_type not in {None, "select"}:
                raise ValueError("销售规格只能使用单选类型")
        elif self.candidates:
            raise ValueError("描述属性不接受销售候选值")
        if len({item.key for item in self.candidates}) != len(self.candidates):
            raise ValueError("同属性内候选引用键不能重复")
        return self


class CandidateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    adoption_id: UUID
    value_id: UUID | None
    display_value: str
    is_current: bool


class AdoptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    attribute_id: UUID | None
    adoption_version: int
    name_snapshot: str
    value_type_snapshot: str
    unit_snapshot: str | None
    validation_snapshot: dict[str, object]
    source_category_id: UUID | None
    source_category_revision: int | None
    source_attribute_revision: int | None
    is_variant: bool
    is_required: bool
    allow_custom_value: bool
    is_current: bool
    candidates: list[CandidateRead] = Field(default_factory=list)
    value: str | list[str] | None = None
    display_snapshot: dict[str, str] = Field(default_factory=dict)


class WholesalePrice(CatalogInput):
    min_quantity: int = Field(ge=2, le=999, strict=True)
    unit_price: Money


class SkuFields(CatalogInput):
    code: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    price: Money
    cost_price: Money | None = None
    market_price: Money | None = None
    wholesale_prices: list[WholesalePrice] = Field(default_factory=list, max_length=10)
    weight_grams: int | None = Field(default=None, ge=0, le=1000000000)
    is_active: bool = Field(default=True, strict=True)

    @model_validator(mode="after")
    def validate_wholesale(self) -> Self:
        previous_quantity, previous_price = 1, self.price
        for index, tier in enumerate(self.wholesale_prices):
            if (
                tier.min_quantity <= previous_quantity
                or tier.unit_price > previous_price
                or (index > 0 and tier.unit_price == previous_price)
            ):
                raise ValueError("批发数量必须严格递增，价格不高于基础价且逐档严格递减")
            previous_quantity, previous_price = tier.min_quantity, tier.unit_price
        return self


class NewSkuInput(SkuFields):
    selections: dict[str, str] = Field(
        default_factory=dict, max_length=10, description="属性请求键到候选请求键的完整组合"
    )
    initial_quantity: int = Field(default=0, ge=0, le=1000000000, strict=True, description="本次明确盘点的初始库存")


class SpecificationSet(CatalogInput):
    attributes: list[AdoptionInput] = Field(default_factory=list, max_length=50)
    skus: list[NewSkuInput] = Field(min_length=1, max_length=100)
    category_revision: int = Field(gt=0, description="采用时所属分类及模板版本")

    @model_validator(mode="after")
    def valid_set(self) -> Self:
        if len({item.key for item in self.attributes}) != len(self.attributes):
            raise ValueError("属性引用键不能重复")
        public_ids = [item.attribute_id for item in self.attributes if item.attribute_id is not None]
        if len(set(public_ids)) != len(public_ids):
            raise ValueError("公共属性不能重复采用")
        variants = {item.key: {value.key for value in item.candidates} for item in self.attributes if item.is_variant}
        if len(variants) > 10:
            raise ValueError("销售规格最多十个维度")
        combinations: set[tuple[tuple[str, str], ...]] = set()
        for sku in self.skus:
            if set(sku.selections) != set(variants) or any(
                value not in variants[key] for key, value in sku.selections.items()
            ):
                raise ValueError("SKU 必须对每个销售维度选择恰好一个本商品候选值")
            combination = tuple(sorted(sku.selections.items()))
            if combination in combinations:
                raise ValueError("规格组合不能重复")
            combinations.add(combination)
        if len({sku.code for sku in self.skus}) != len(self.skus):
            raise ValueError("SKU 编码不能重复")
        return self


class SpecificationConversion(SpecificationSet):
    revision: int = Field(gt=0, description="商品当前版本，转换整体原子提交")


class DescriptionUpdate(CatalogInput):
    revision: int = Field(gt=0, description="商品当前版本")
    value: str | list[UUID] | None


class ExistingDescription(CatalogInput):
    adoption_id: UUID
    value: str | list[UUID] | None


class DescriptionSet(CatalogInput):
    revision: int = Field(gt=0)
    category_revision: int = Field(gt=0)
    existing: list[ExistingDescription] = Field(default_factory=list, max_length=50)
    added: list[AdoptionInput] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def descriptions_only(self) -> Self:
        if len({row.adoption_id for row in self.existing}) != len(self.existing):
            raise ValueError("描述采用不能重复")
        if any(row.is_variant for row in self.added):
            raise ValueError("描述集合不能包含销售规格")
        if len(self.existing) + len(self.added) > 50:
            raise ValueError("商品属性最多五十项")
        return self


class CandidateAppend(CatalogInput):
    revision: int = Field(gt=0)
    source_attribute_revision: int | None = Field(default=None, gt=0)
    candidates: list[CandidateInput] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique_keys(self) -> Self:
        if len({row.key for row in self.candidates}) != len(self.candidates):
            raise ValueError("候选引用键不能重复")
        return self
