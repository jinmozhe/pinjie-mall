import uuid
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ShippingTemplate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "shipping_templates"
    __table_args__ = (
        CheckConstraint("pricing_method IN ('piece', 'weight')", name="ck_shipping_pricing_method"),
        CheckConstraint("revision > 0", name="ck_shipping_revision"),
        CheckConstraint(
            "free_shipping_threshold IS NULL OR free_shipping_threshold >= 0", name="ck_shipping_threshold"
        ),
        CheckConstraint("jsonb_typeof(regions) = 'array'", name="ck_shipping_regions"),
        CheckConstraint("jsonb_typeof(excluded_provinces) = 'array'", name="ck_shipping_exclusions"),
        {"comment": "运费模板与确定性地区计费规则"},
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="模板名称")
    pricing_method: Mapped[str] = mapped_column(String(10), nullable=False, comment="piece 按件，weight 按克")
    regions: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False, comment="地区及默认计费规则")
    free_shipping_threshold: Mapped[Decimal | None] = mapped_column(
        Numeric(15, 2), nullable=True, comment="包邮商品金额门槛"
    )
    excluded_provinces: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, comment="不参与满额包邮的省份"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, comment="是否允许新商品绑定和结算")
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="编辑版本")
    updated_by_id: Mapped[uuid.UUID] = mapped_column(nullable=False, comment="最后操作管理员 ID")
