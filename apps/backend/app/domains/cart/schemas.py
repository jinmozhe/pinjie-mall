from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CartItemInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sku_id: UUID
    quantity: int = Field(ge=1, le=999)


class CartItemUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(gt=0, description="读取购物车条目时获得的版本")
    quantity: int | None = Field(default=None, ge=1, le=999)
    selected: bool | None = None


class CartItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    sku_id: UUID
    quantity: int
    selected: bool
    revision: int
