from decimal import ROUND_CEILING, Decimal
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

Money = Annotated[Decimal, Field(ge=0, max_digits=15, decimal_places=2)]
ProvinceCode = Annotated[str, Field(pattern=r"^[0-9]{6}$")]


class ShippingRegion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provinces: list[ProvinceCode] = Field(max_length=100, description="省份行政编码，空数组表示唯一默认地区")
    first_unit: int = Field(gt=0, le=1000000000, description="首件数或首重克数")
    first_price: Money = Field(description="首费，人民币元")
    additional_unit: int = Field(gt=0, le=1000000000, description="续件数或续重克数")
    additional_price: Money = Field(description="每续单位费用，人民币元")


class ShippingTemplateInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=100, description="模板名称")
    pricing_method: Literal["piece", "weight"] = Field(description="按件或按克计价")
    regions: list[ShippingRegion] = Field(min_length=1, max_length=100, description="含唯一默认地区的计费规则")
    free_shipping_threshold: Money | None = Field(default=None, description="包邮商品金额门槛，空表示不设置")
    excluded_provinces: list[ProvinceCode] = Field(
        default_factory=list, max_length=100, description="不参与满额包邮的省份"
    )
    is_active: bool = Field(default=True, strict=True, description="是否允许使用")

    @model_validator(mode="after")
    def check_regions(self) -> Self:
        if sum(not region.provinces for region in self.regions) != 1:
            raise ValueError("必须配置且只能配置一条默认地区规则")
        codes = [code for region in self.regions for code in region.provinces]
        if len(codes) != len(set(codes)):
            raise ValueError("省份不能重复归属")
        if len(self.excluded_provinces) != len(set(self.excluded_provinces)):
            raise ValueError("包邮排除省份不能重复")
        return self


class ShippingTemplateUpdate(ShippingTemplateInput):
    revision: int = Field(gt=0, description="读取模板时获得的编辑版本")


class ShippingTemplateRead(ShippingTemplateInput):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID = Field(description="运费模板 ID")
    revision: int = Field(gt=0, description="当前编辑版本")


class FreightQuoteInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    province_code: ProvinceCode = Field(description="收货省份行政编码")
    pieces: int = Field(gt=0, le=1000000, description="总件数")
    weight_grams: int = Field(ge=0, le=49950000000000, description="总重量克数，覆盖五十种 SKU 各九百九十九件")
    items_amount: Money = Field(description="商品金额，不含运费")


class FreightQuote(BaseModel):
    template_id: UUID = Field(description="运费模板 ID")
    revision: int = Field(description="计费规则版本")
    freight: Money = Field(description="运费人民币元")
    free_shipping: bool = Field(description="是否满足包邮条件")


def calculate_freight(template: ShippingTemplateInput, quote: FreightQuoteInput) -> Decimal:
    if not template.is_active:
        raise ValueError("运费模板已停用")
    if template.pricing_method == "weight" and quote.weight_grams <= 0:
        raise ValueError("按重量计费必须提供正重量")
    if (
        template.free_shipping_threshold is not None
        and quote.items_amount >= template.free_shipping_threshold
        and quote.province_code not in template.excluded_provinces
    ):
        return Decimal("0.00")
    default = next(region for region in template.regions if not region.provinces)
    rule = next((region for region in template.regions if quote.province_code in region.provinces), default)
    total = quote.pieces if template.pricing_method == "piece" else quote.weight_grams
    overflow = max(0, total - rule.first_unit)
    count = (Decimal(overflow) / Decimal(rule.additional_unit)).to_integral_value(rounding=ROUND_CEILING)
    freight = (rule.first_price + count * rule.additional_price).quantize(Decimal("0.01"))
    if freight > Decimal("9999999999999.99"):
        raise ValueError("运费超过金额上限")
    return freight
