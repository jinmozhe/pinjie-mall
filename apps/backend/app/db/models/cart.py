from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class CartItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "cart_items"
    __table_args__ = (
        UniqueConstraint("user_id", "sku_id", name="uq_cart_user_sku"),
        CheckConstraint("quantity BETWEEN 1 AND 999", name="ck_cart_quantity"),
        CheckConstraint("revision > 0", name="ck_cart_revision"),
        {"comment": "用户购物车意图，不占用库存也不保存权威价格"},
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), comment="所属用户")
    sku_id: Mapped[UUID] = mapped_column(ForeignKey("product_skus.id", ondelete="RESTRICT"), comment="稳定 SKU")
    quantity: Mapped[int] = mapped_column(Integer, comment="购买意向数量")
    selected: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否勾选")
    revision: Mapped[int] = mapped_column(Integer, default=1, comment="购物车条目版本")
