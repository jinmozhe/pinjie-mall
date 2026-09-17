import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class InventoryAccount(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "inventory_accounts"
    __table_args__ = (
        CheckConstraint("available >= 0 AND reserved >= 0", name="ck_inventory_quantities"),
        CheckConstraint("revision > 0", name="ck_inventory_revision"),
        {"comment": "SKU 库存账户，独立于商品资料"},
    )
    sku_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("product_skus.id", ondelete="RESTRICT"), nullable=False, unique=True, comment="稳定 SKU ID"
    )
    available: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="可售数量")
    reserved: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="订单占用数量")
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="库存版本")


class InventoryMovement(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "inventory_movements"
    __table_args__ = (
        UniqueConstraint("sku_id", "request_id", name="uq_inventory_movement_request"),
        CheckConstraint("quantity_delta <> 0", name="ck_inventory_delta"),
        CheckConstraint("before_available >= 0 AND after_available >= 0", name="ck_inventory_movement_balance"),
        CheckConstraint("after_available = before_available + quantity_delta", name="ck_inventory_movement_equation"),
        {"comment": "不可变人工库存调整流水与幂等结果"},
    )
    sku_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("product_skus.id", ondelete="RESTRICT"), nullable=False, index=True, comment="变动 SKU ID"
    )
    request_id: Mapped[uuid.UUID] = mapped_column(nullable=False, comment="调用方业务幂等号，同 SKU 内唯一")
    actor_id: Mapped[uuid.UUID] = mapped_column(nullable=False, comment="操作管理员 ID")
    quantity_delta: Mapped[int] = mapped_column(Integer, nullable=False, comment="增减数量")
    before_available: Mapped[int] = mapped_column(Integer, nullable=False, comment="变动前可售库存")
    after_available: Mapped[int] = mapped_column(Integer, nullable=False, comment="变动后可售库存")
    expected_revision: Mapped[int] = mapped_column(Integer, nullable=False, comment="原请求期望版本")
    resulting_revision: Mapped[int] = mapped_column(Integer, nullable=False, comment="完成后的库存版本")
    reason: Mapped[str] = mapped_column(String(200), nullable=False, comment="调整原因")
