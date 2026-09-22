from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class InventoryAdjustment(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    request_id: UUID = Field(description="同 SKU 内唯一的业务幂等号")
    revision: int = Field(gt=0, description="读取库存时获得的版本")
    quantity_delta: int = Field(ge=-1000000000, le=1000000000, description="增加为正，减少为负，禁止零")
    reason: str = Field(min_length=1, max_length=200, description="库存调整原因")

    @field_validator("quantity_delta")
    @classmethod
    def nonzero(cls, value: int) -> int:
        if value == 0:
            raise ValueError("库存调整数量不能为零")
        return value


class InventoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sku_id: UUID = Field(description="SKU 标识")
    available: int = Field(ge=0, description="当前可售库存")
    reserved: int = Field(ge=0, description="订单占用库存")
    revision: int = Field(gt=0, description="库存版本")


class InventoryMovementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(description="流水 ID")
    sku_id: UUID = Field(description="SKU 标识")
    request_id: UUID = Field(description="幂等请求 ID")
    actor_id: UUID | None = Field(description="操作管理员 ID，系统为空")
    actor_type: str
    source_type: str
    source_id: UUID | None
    request_hash: str
    quantity_delta: int = Field(description="调整数量")
    before_available: int = Field(description="调整前可售库存")
    after_available: int = Field(description="调整后可售库存")
    expected_revision: int = Field(description="请求期望版本")
    resulting_revision: int = Field(description="完成后版本")
    reason: str = Field(description="调整原因")
    created_at: datetime = Field(description="流水创建时间")


def adjusted_available(available: int, delta: int) -> int:
    result = available + delta
    if not 0 <= result <= 2147483647:
        raise ValueError("调整后库存必须在零至数据库整数上限之间")
    return result
