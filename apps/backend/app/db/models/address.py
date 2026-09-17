import uuid

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class UserAddress(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "user_addresses"
    __table_args__ = (
        CheckConstraint("revision > 0", name="ck_address_revision"),
        Index("uq_user_address_default", "user_id", unique=True, postgresql_where=text("is_default")),
        Index("ix_user_addresses_user_created", "user_id", "created_at"),
        {"comment": "用户收货地址，订单另存独立快照"},
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, comment="所属用户 ID"
    )
    receiver_name: Mapped[str] = mapped_column(String(100), nullable=False, comment="收件人姓名")
    mobile: Mapped[str] = mapped_column(String(32), nullable=False, comment="收件联系电话")
    province_code: Mapped[str] = mapped_column(String(6), nullable=False, comment="省份行政编码")
    city_code: Mapped[str] = mapped_column(String(6), nullable=False, comment="城市行政编码")
    district_code: Mapped[str] = mapped_column(String(6), nullable=False, comment="区县行政编码")
    province: Mapped[str] = mapped_column(String(100), nullable=False, comment="省份名称")
    city: Mapped[str] = mapped_column(String(100), nullable=False, comment="城市名称")
    district: Mapped[str] = mapped_column(String(100), nullable=False, comment="区县名称")
    street_address: Mapped[str] = mapped_column(String(300), nullable=False, comment="详细地址")
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, comment="是否默认地址")
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="编辑版本")
