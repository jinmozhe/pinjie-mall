from decimal import Decimal
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class CategoryInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=100, description="分类名称")
    parent_id: UUID | None = Field(default=None, description="父分类 ID，根分类为空")
    sort_order: int = Field(default=0, ge=-1000000, le=1000000, description="排序值")
    is_active: bool = Field(default=True, strict=True, description="分类是否启用")


class CategoryUpdate(CategoryInput):
    revision: int = Field(gt=0, description="读取分类时获得的版本")


class CategoryRead(CategoryInput):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(description="分类 ID")
    revision: int = Field(description="分类版本")


class SkuInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    code: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$", description="全局唯一 SKU 编码")
    specifications: dict[str, str] = Field(default_factory=dict, description="规格组合，无规格为默认 SKU")
    price: Decimal = Field(ge=0, max_digits=15, decimal_places=2, description="基础售价人民币元")
    weight_grams: int = Field(ge=0, le=1000000000, description="重量克数，虚拟商品为零")
    is_active: bool = Field(default=True, strict=True, description="是否启用 SKU")

    @field_validator("specifications")
    @classmethod
    def bounded_specs(cls, values: dict[str, str]) -> dict[str, str]:
        if len(values) > 10 or any(
            not key.strip() or not value.strip() or len(key) > 50 or len(value) > 100 for key, value in values.items()
        ):
            raise ValueError("规格最多十项，名称和取值必须非空并符合长度限制")
        return values


class SkuRead(SkuInput):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(description="稳定 SKU ID")


class CheckoutSku(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    product_id: UUID
    code: str
    specifications: dict[str, str]
    price: Decimal
    weight_grams: int
    product_name: str
    product_type: Literal["physical", "virtual"]
    product_revision: int
    shipping_template_id: UUID | None


class SkuUpdate(SkuInput):
    revision: int = Field(gt=0, description="商品当前版本，变体编辑共用商品版本")


class ProductInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=200, description="商品名称")
    description: str = Field(default="", max_length=20000, description="纯文本商品说明")
    product_type: Literal["physical", "virtual"] = Field(description="实物或虚拟商品")
    category_id: UUID = Field(description="所属分类 ID")
    shipping_template_id: UUID | None = Field(default=None, description="实物运费模板，虚拟商品为空")
    image_asset_ids: list[UUID] = Field(default_factory=list, max_length=20, description="有序图片资产 ID，首张为主图")

    @model_validator(mode="after")
    def check_product(self) -> Self:
        if self.product_type == "virtual" and self.shipping_template_id is not None:
            raise ValueError("虚拟商品不能绑定物流运费模板")
        if len(self.image_asset_ids) != len(set(self.image_asset_ids)):
            raise ValueError("商品图片不能重复")
        return self


class ProductCreate(ProductInput):
    skus: list[SkuInput] = Field(min_length=1, max_length=100, description="初始 SKU，无规格也需默认 SKU")

    @model_validator(mode="after")
    def unique_variants(self) -> Self:
        if len({sku.code for sku in self.skus}) != len(self.skus):
            raise ValueError("SKU 编码不能重复")
        specs = [tuple(sorted(sku.specifications.items())) for sku in self.skus]
        if len(set(specs)) != len(specs):
            raise ValueError("规格组合不能重复")
        return self


class ProductUpdate(ProductInput):
    revision: int = Field(gt=0, description="读取商品时获得的版本")


class ProductStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision: int = Field(gt=0, description="读取商品时获得的版本")
    status: Literal["on_sale", "off_sale"] = Field(description="上架或下架")


class ProductRead(ProductInput):
    id: UUID = Field(description="商品 ID")
    status: Literal["draft", "on_sale", "off_sale"] = Field(description="商品状态")
    revision: int = Field(description="商品版本")
    skus: list[SkuRead] = Field(description="商品全部 SKU")


class PublicProductRead(BaseModel):
    id: UUID = Field(description="商品 ID")
    name: str = Field(description="商品名称")
    description: str = Field(description="商品纯文本说明")
    product_type: Literal["physical", "virtual"] = Field(description="商品类型")
    category_id: UUID = Field(description="分类 ID")
    images: list[str] = Field(description="图片公开地址")
    skus: list[SkuRead] = Field(description="启用中的商品变体")


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
