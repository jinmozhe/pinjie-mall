from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

AreaCode = Annotated[str, Field(pattern=r"^[0-9]{6}$")]


class AddressInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    receiver_name: str = Field(min_length=1, max_length=100, description="收件人姓名")
    mobile: str = Field(pattern=r"^\+?[0-9]{6,20}$", description="收件联系电话，可含国际区号")
    province_code: AreaCode = Field(description="省份行政编码")
    city_code: AreaCode = Field(description="城市行政编码")
    district_code: AreaCode = Field(description="区县行政编码")
    province: str = Field(min_length=1, max_length=100, description="省份名称")
    city: str = Field(min_length=1, max_length=100, description="城市名称")
    district: str = Field(min_length=1, max_length=100, description="区县名称")
    street_address: str = Field(min_length=1, max_length=300, description="详细收货地址")
    is_default: bool = Field(default=False, strict=True, description="是否设为默认地址")


class AddressUpdate(AddressInput):
    revision: int = Field(gt=0, description="读取地址时获得的编辑版本")


class AddressRead(AddressInput):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(description="收货地址 ID")
    revision: int = Field(gt=0, description="当前编辑版本")
