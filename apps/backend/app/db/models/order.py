from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Order(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("user_id", "request_id", name="uq_order_user_request"),
        UniqueConstraint("payment_reference", name="uq_orders_payment_reference"),
        CheckConstraint("status IN ('pending_payment', 'paid', 'cancelled')", name="ck_order_status"),
        CheckConstraint("product_type IN ('physical', 'virtual')", name="ck_order_product_type"),
        CheckConstraint(
            "items_amount >= 0 AND freight_amount >= 0 AND total_amount = items_amount + freight_amount",
            name="ck_order_amounts",
        ),
        CheckConstraint("currency = 'CNY'", name="ck_order_currency"),
        CheckConstraint("revision > 0", name="ck_order_revision"),
        CheckConstraint("jsonb_typeof(shipping_snapshot) = 'array'", name="ck_order_shipping_snapshot"),
        CheckConstraint(
            "(product_type = 'physical' AND address_snapshot IS NOT NULL AND jsonb_typeof(address_snapshot) = 'object') OR (product_type = 'virtual' AND address_snapshot IS NULL)",
            name="ck_order_address_snapshot",
        ),
        CheckConstraint(
            "(status = 'paid' AND paid_at IS NOT NULL AND payment_reference IS NOT NULL) OR (status <> 'paid' AND paid_at IS NULL AND payment_reference IS NULL)",
            name="ck_order_paid_fact",
        ),
        CheckConstraint(
            "(status = 'cancelled' AND cancelled_at IS NOT NULL AND cancel_reason IS NOT NULL) OR (status <> 'cancelled' AND cancelled_at IS NULL AND cancel_reason IS NULL)",
            name="ck_order_cancel_fact",
        ),
        Index("ix_orders_user_created", "user_id", "created_at", "id"),
        Index("ix_orders_expiry", "expires_at", "id", postgresql_where="status = 'pending_payment'"),
        {"comment": "交易订单与不可变计价快照"},
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), comment="下单用户")
    request_id: Mapped[UUID] = mapped_column(comment="用户范围幂等请求号")
    request_hash: Mapped[str] = mapped_column(String(64), comment="规范化请求摘要")
    quote_fingerprint: Mapped[str] = mapped_column(String(64), comment="成交报价指纹")
    product_type: Mapped[str] = mapped_column(String(16), comment="实物或虚拟，禁止混单")
    status: Mapped[str] = mapped_column(String(24), default="pending_payment", comment="订单状态")
    currency: Mapped[str] = mapped_column(String(3), default="CNY", comment="币种")
    items_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), comment="商品金额")
    freight_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), comment="运费")
    total_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), comment="应付金额")
    address_snapshot: Mapped[dict[str, object] | None] = mapped_column(
        JSONB(none_as_null=True), nullable=True, comment="收货地址快照"
    )
    shipping_snapshot: Mapped[list[dict[str, object]]] = mapped_column(JSONB, comment="分组运费与规则快照")
    pricing_version: Mapped[str] = mapped_column(String(32), comment="计价规则版本")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), comment="待付款截止时间")
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="可信支付确认时间")
    payment_reference: Mapped[str | None] = mapped_column(
        String(160), nullable=True, comment="支付领域提供的唯一确认标识"
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="取消时间")
    cancel_reason: Mapped[str | None] = mapped_column(String(200), nullable=True, comment="取消原因")
    revision: Mapped[int] = mapped_column(Integer, default=1, comment="状态版本")


class OrderItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "order_items"
    __table_args__ = (
        UniqueConstraint("order_id", "sku_id", name="uq_order_item_sku"),
        CheckConstraint("quantity BETWEEN 1 AND 999", name="ck_order_item_quantity"),
        CheckConstraint("unit_price >= 0 AND line_amount = unit_price * quantity", name="ck_order_item_amount"),
        CheckConstraint("jsonb_typeof(specifications) = 'object'", name="ck_order_item_specs"),
        {"comment": "订单明细快照，后续退款与评价的稳定标识"},
    )
    order_id: Mapped[UUID] = mapped_column(ForeignKey("orders.id", ondelete="RESTRICT"), comment="所属订单")
    product_id: Mapped[UUID] = mapped_column(comment="原商品标识，不用于读取历史价格")
    sku_id: Mapped[UUID] = mapped_column(comment="原稳定 SKU 标识")
    product_name: Mapped[str] = mapped_column(String(200), comment="成交商品名称")
    sku_code: Mapped[str] = mapped_column(String(100), comment="成交 SKU 编码")
    specifications: Mapped[dict[str, str]] = mapped_column(JSONB, comment="成交规格")
    quantity: Mapped[int] = mapped_column(Integer, comment="成交数量")
    unit_price: Mapped[Decimal] = mapped_column(Numeric(15, 2), comment="成交单价")
    line_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), comment="成交行金额")
    weight_grams: Mapped[int] = mapped_column(Integer, comment="单件重量克数")
    product_revision: Mapped[int] = mapped_column(Integer, comment="成交商品资料版本")


class OrderEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "order_events"
    __table_args__ = (
        UniqueConstraint("order_id", "revision", name="uq_order_event_revision"),
        CheckConstraint("actor_type IN ('user', 'system', 'payment')", name="ck_order_event_actor"),
        CheckConstraint("to_status IN ('pending_payment', 'paid', 'cancelled')", name="ck_order_event_status"),
        {"comment": "订单状态变更事实，与订单和库存同事务写入"},
    )
    order_id: Mapped[UUID] = mapped_column(ForeignKey("orders.id", ondelete="RESTRICT"), comment="订单标识")
    revision: Mapped[int] = mapped_column(Integer, comment="对应订单版本")
    from_status: Mapped[str | None] = mapped_column(String(24), nullable=True, comment="原状态，创建为空")
    to_status: Mapped[str] = mapped_column(String(24), comment="目标状态")
    actor_type: Mapped[str] = mapped_column(String(16), comment="操作者类型")
    actor_id: Mapped[UUID | None] = mapped_column(nullable=True, comment="操作者用户 ID")
    reason: Mapped[str] = mapped_column(String(200), comment="状态变更原因")
