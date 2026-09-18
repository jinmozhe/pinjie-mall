"""有界批量命令的结构契约；业务校验由领域服务执行。"""

from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class VersionedTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(description="明确选中的资源标识")
    revision: int = Field(gt=0, description="用户读取时的资源版本")


class VersionedBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    targets: list[VersionedTarget] = Field(min_length=1, max_length=100, description="一至一百个不重复的目标及版本")

    @model_validator(mode="after")
    def unique_targets(self) -> Self:
        if len({target.id for target in self.targets}) != len(self.targets):
            raise ValueError("批量目标不能重复")
        return self


class ActiveStatusBatch(VersionedBatch):
    is_active: bool = Field(strict=True, description="统一设置的启用状态")


class BatchCompleted(BaseModel):
    completed_count: int = Field(ge=1, le=100, description="原子完成的目标数量")
