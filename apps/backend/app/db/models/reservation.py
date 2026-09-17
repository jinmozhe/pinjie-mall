from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class InventoryReservation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "inventory_reservations"
    __table_args__ = (
        UniqueConstraint("order_id", "sku_id", name="uq_inventory_reservation_order_sku"),
        CheckConstraint("quantity BETWEEN 1 AND 999", name="ck_inventory_reservation_quantity"),
        CheckConstraint("status IN ('reserved', 'confirmed', 'released')", name="ck_inventory_reservation_status"),
        Index("ix_inventory_reservations_order_id", "order_id"),
        {"comment": "订单库存占用事实与幂等状态"},
    )
    order_id: Mapped[UUID] = mapped_column(ForeignKey("orders.id", ondelete="RESTRICT"), comment="订单标识")
    sku_id: Mapped[UUID] = mapped_column(ForeignKey("product_skus.id", ondelete="RESTRICT"), comment="稳定 SKU")
    quantity: Mapped[int] = mapped_column(Integer, comment="占用数量")
    status: Mapped[str] = mapped_column(String(16), default="reserved", comment="占用、确认或释放")
    revision: Mapped[int] = mapped_column(Integer, default=1, comment="占用版本")
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="释放时间")
