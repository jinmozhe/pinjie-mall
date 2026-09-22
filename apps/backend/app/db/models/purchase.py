from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ProductPurchaseLimit(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "product_purchase_limits"
    __table_args__ = (
        UniqueConstraint("user_id", "product_id", name="uq_product_purchase_limit_user_product"),
        CheckConstraint("purchased_quantity >= 0 AND reserved_quantity >= 0", name="ck_product_purchase_limit_amounts"),
        CheckConstraint("revision > 0", name="ck_product_purchase_limit_revision"),
        Index("ix_product_purchase_limit_product", "product_id", "id"),
        {"comment": "用户跨 SKU 累计限购账户"},
    )

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    product_id: Mapped[UUID] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"), nullable=False)
    purchased_quantity: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    reserved_quantity: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class ProductPurchaseRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "product_purchase_records"
    __table_args__ = (
        UniqueConstraint("order_id", "product_id", name="uq_product_purchase_record_order_product"),
        CheckConstraint("quantity > 0", name="ck_product_purchase_record_quantity"),
        CheckConstraint(
            "status IN ('reserved', 'confirmed', 'released', 'refunded')", name="ck_product_purchase_record_status"
        ),
        CheckConstraint("limit_snapshot >= 0", name="ck_product_purchase_record_limit"),
        CheckConstraint("revision > 0", name="ck_product_purchase_record_revision"),
        CheckConstraint(
            "(status = 'reserved' AND confirmed_at IS NULL AND released_at IS NULL AND refunded_at IS NULL) OR "
            "(status = 'confirmed' AND confirmed_at IS NOT NULL AND released_at IS NULL AND refunded_at IS NULL) OR "
            "(status = 'released' AND confirmed_at IS NULL AND released_at IS NOT NULL AND refunded_at IS NULL) OR "
            "(status = 'refunded' AND confirmed_at IS NOT NULL AND released_at IS NULL AND refunded_at IS NOT NULL)",
            name="ck_product_purchase_record_timestamps",
        ),
        Index("ix_product_purchase_record_user_product", "user_id", "product_id", "id"),
        {"comment": "订单商品限购预占、成交和退款事实"},
    )

    order_id: Mapped[UUID] = mapped_column(ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    product_id: Mapped[UUID] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"), nullable=False)
    quantity: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="reserved")
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    limit_snapshot: Mapped[int] = mapped_column(Integer, nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
