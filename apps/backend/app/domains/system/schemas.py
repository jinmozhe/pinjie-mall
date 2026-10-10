from typing import Literal

from pydantic import BaseModel, ConfigDict


class SystemStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["available", "unavailable"]


class LiveStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["alive"]


class ReadinessStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ready", "unavailable"]
    checks: dict[str, str]


class ConsumerHelpRead(BaseModel):
    phone: str | None
    email: str | None
