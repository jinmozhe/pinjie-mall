from datetime import datetime
from decimal import Decimal
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.batch import VersionedBatch

from .catalog_schemas import AdoptionRead, SkuFields, SpecificationSet, WholesalePrice


class CategoryInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=100, description="分类名称")
    parent_id: UUID | None = Field(default=None, description="父分类 ID，根分类为空")
    sort_order: int | None = Field(default=None, ge=0, description="排序权重，值越小越靠前，不填则自动排最后")
    is_active: bool = Field(default=True, strict=True, description="分类是否启用")


class CategoryUpdate(CategoryInput):
    revision: int = Field(gt=0, description="读取分类时获得的版本")


class CategoryRead(CategoryInput):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(description="分类 ID")
    revision: int = Field(description="分类版本")


class SkuInput(SkuFields):
    spec_value_ids: list[UUID] = Field(
        default_factory=list, max_length=10, description="当前商品采用版本的候选值 ID，无规格为空"
    )

    @field_validator("spec_value_ids")
    @classmethod
    def unique_values(cls, values: list[UUID]) -> list[UUID]:
        if len(set(values)) != len(values):
            raise ValueError("规格候选值不能重复")
        return values


class SkuRead(SkuInput):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(description="稳定 SKU ID")
    sku_no: int
    specifications: dict[str, str]
    specification_key: str
    archived_at: datetime | None


class PublicSkuRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    code: str
    sku_no: int
    specifications: dict[str, str]
    price: Decimal
    market_price: Decimal | None
    wholesale_prices: list[WholesalePrice]
    weight_grams: int | None
    is_active: bool


class CheckoutSku(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    product_id: UUID
    code: str
    specifications: dict[str, str]
    price: Decimal
    weight_grams: int | None
    product_name: str
    product_type: Literal["physical", "virtual"]
    product_revision: int


class SkuUpdate(SkuInput):
    revision: int = Field(gt=0, description="商品当前版本，变体编辑共用商品版本")


class ProductInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=200, description="商品名称")
    description: str = Field(default="", max_length=20000, description="纯文本商品说明")
    product_type: Literal["physical", "virtual"] = Field(description="实物或虚拟商品")
    category_id: UUID = Field(description="所属分类 ID")
    brand_id: UUID | None = Field(default=None, description="可选品牌")
    purchase_limit_quantity: int = Field(
        default=0, ge=0, le=2147483647, description="每用户累计限购配置，交易阶段实施计数"
    )
    image_asset_ids: list[UUID] = Field(default_factory=list, max_length=20, description="有序图片资产 ID，首张为主图")

    @model_validator(mode="after")
    def check_product(self) -> Self:
        if len(self.image_asset_ids) != len(set(self.image_asset_ids)):
            raise ValueError("商品图片不能重复")
        return self


class ProductCreate(ProductInput, SpecificationSet):
    pass


class ProductUpdate(ProductInput):
    revision: int = Field(gt=0, description="读取商品时获得的版本")


class ProductStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision: int = Field(gt=0, description="读取商品时获得的版本")
    status: Literal["on_sale", "off_sale"] = Field(description="上架或下架")


class ProductStatusBatch(VersionedBatch):
    status: Literal["on_sale", "off_sale"] = Field(description="统一设置的商品上下架状态")


class SkuStatusBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sku_ids: list[UUID] = Field(min_length=1, max_length=100, description="同一商品内明确选中的变体标识")
    revision: int = Field(gt=0, description="读取商品时的共享版本")
    is_active: bool = Field(strict=True, description="统一设置的变体启用状态")

    @field_validator("sku_ids")
    @classmethod
    def unique_ids(cls, values: list[UUID]) -> list[UUID]:
        if len(values) != len(set(values)):
            raise ValueError("SKU 标识不能重复")
        return values


class ProductRead(ProductInput):
    id: UUID = Field(description="商品 ID")
    status: Literal["draft", "on_sale", "off_sale"] = Field(description="商品状态")
    revision: int = Field(description="商品版本")
    skus: list[SkuRead] = Field(description="商品全部 SKU")
    attributes: list[AdoptionRead] = Field(description="当前及历史属性采用")


class PublicProductRead(BaseModel):
    id: UUID = Field(description="商品 ID")
    name: str = Field(description="商品名称")
    description: str = Field(description="商品纯文本说明")
    product_type: Literal["physical", "virtual"] = Field(description="商品类型")
    category_id: UUID = Field(description="分类 ID")
    brand_id: UUID | None
    images: list[str] = Field(description="图片公开地址")
    skus: list[PublicSkuRead] = Field(description="启用且未归档的商品变体，无成本字段")
    attributes: list[AdoptionRead] = Field(description="当前采用定义及描述值")


def validate_category_tree(parents: dict[UUID, UUID | None]) -> None:
    for category_id in parents:
        seen: set[UUID] = set()
        current: UUID | None = category_id
        while current is not None:
            if current in seen:
                raise ValueError("分类不能构成循环")
            if current not in parents:
                raise ValueError("父分类不存在")
            seen.add(current)
            if len(seen) > 3:
                raise ValueError("分类最多三级")
            current = parents[current]
