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


class InventoryReservationEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "inventory_reservation_events"
    __table_args__ = (
        UniqueConstraint("reservation_id", "revision", name="uq_inventory_reservation_event_revision"),
        CheckConstraint(
            "to_status IN ('reserved', 'confirmed', 'released')", name="ck_inventory_reservation_event_status"
        ),
        CheckConstraint(
            "before_available >= 0 AND after_available >= 0 AND before_reserved >= 0 AND after_reserved >= 0",
            name="ck_inventory_reservation_event_balances",
        ),
        CheckConstraint(
            "revision > 0 AND resulting_inventory_revision > 0", name="ck_inventory_reservation_event_revisions"
        ),
        {"comment": "不可变订单库存占用、确认与释放流水"},
    )
    reservation_id: Mapped[UUID] = mapped_column(
        ForeignKey("inventory_reservations.id", ondelete="RESTRICT"), comment="库存占用标识"
    )
    revision: Mapped[int] = mapped_column(Integer, comment="占用状态版本")
    to_status: Mapped[str] = mapped_column(String(16), comment="占用、确认或释放")
    before_available: Mapped[int] = mapped_column(Integer, comment="变动前可售库存")
    after_available: Mapped[int] = mapped_column(Integer, comment="变动后可售库存")
    before_reserved: Mapped[int] = mapped_column(Integer, comment="变动前占用库存")
    after_reserved: Mapped[int] = mapped_column(Integer, comment="变动后占用库存")
    resulting_inventory_revision: Mapped[int] = mapped_column(Integer, comment="变动后库存账户版本")
