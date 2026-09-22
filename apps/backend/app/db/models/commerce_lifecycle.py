from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class PaymentAttempt(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "payment_attempts"
    __table_args__ = (
        UniqueConstraint("user_id", "request_id", name="uq_payment_attempt_user_request"),
        UniqueConstraint("merchant_reference", name="uq_payment_attempt_merchant_reference"),
        UniqueConstraint("channel", "channel_transaction_id", name="uq_payment_attempt_channel_transaction"),
        CheckConstraint("channel IN ('wechat', 'alipay')", name="ck_payment_attempt_channel"),
        CheckConstraint(
            "status IN ('created', 'unavailable', 'pending', 'succeeded', 'closed', 'unknown')",
            name="ck_payment_attempt_status",
        ),
        CheckConstraint("amount > 0", name="ck_payment_attempt_amount"),
        CheckConstraint("currency = 'CNY'", name="ck_payment_attempt_currency"),
        Index("ix_payment_attempt_order_created", "order_id", "created_at", "id"),
        {"comment": "支付意图与渠道确认事实"},
    )

    order_id: Mapped[UUID] = mapped_column(ForeignKey("orders.id", ondelete="RESTRICT"), comment="待支付订单")
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), comment="付款用户")
    request_id: Mapped[UUID] = mapped_column(comment="用户支付请求幂等标识")
    request_hash: Mapped[str] = mapped_column(String(64), comment="规范化支付请求摘要")
    channel: Mapped[str] = mapped_column(String(16), comment="支付渠道")
    merchant_reference: Mapped[str] = mapped_column(String(80), comment="商户侧支付意图标识")
    status: Mapped[str] = mapped_column(String(16), default="created", comment="支付意图状态")
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), comment="应支付金额")
    currency: Mapped[str] = mapped_column(String(3), default="CNY", comment="币种")
    channel_transaction_id: Mapped[str | None] = mapped_column(String(160), nullable=True, comment="渠道交易流水")
    channel_paid_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="渠道实际收款时间"
    )
    channel_context: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, comment="非秘密渠道配置快照")
    unavailable_reason: Mapped[str | None] = mapped_column(String(200), nullable=True, comment="渠道不可用原因")
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="可信确认时间"
    )
    revision: Mapped[int] = mapped_column(Integer, default=1, comment="状态版本")


class PaymentEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "payment_events"
    __table_args__ = (
        UniqueConstraint("payment_attempt_id", "revision", name="uq_payment_event_revision"),
        CheckConstraint(
            "to_status IN ('created', 'unavailable', 'pending', 'succeeded', 'closed', 'unknown')",
            name="ck_payment_event_status",
        ),
        {"comment": "支付意图状态事件"},
    )

    payment_attempt_id: Mapped[UUID] = mapped_column(
        ForeignKey("payment_attempts.id", ondelete="RESTRICT"), comment="支付意图"
    )
    revision: Mapped[int] = mapped_column(Integer, comment="对应支付意图版本")
    from_status: Mapped[str | None] = mapped_column(String(16), nullable=True, comment="原状态")
    to_status: Mapped[str] = mapped_column(String(16), comment="目标状态")
    reason: Mapped[str] = mapped_column(String(200), comment="状态原因")
    payload_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="已验签载荷摘要")


class Fulfillment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "fulfillments"
    __table_args__ = (
        UniqueConstraint("order_id", name="uq_fulfillment_order"),
        CheckConstraint("product_type IN ('physical', 'virtual')", name="ck_fulfillment_product_type"),
        CheckConstraint(
            "status IN ('awaiting_shipment', 'shipped', 'awaiting_delivery', 'delivered', 'cancelled')",
            name="ck_fulfillment_status",
        ),
        Index("ix_fulfillment_auto_confirm", "auto_confirm_at", "id", postgresql_where="status = 'shipped'"),
        {"comment": "订单履约状态与物流或虚拟交付引用"},
    )

    order_id: Mapped[UUID] = mapped_column(ForeignKey("orders.id", ondelete="RESTRICT"), comment="已支付订单")
    product_type: Mapped[str] = mapped_column(String(16), comment="实物或虚拟")
    status: Mapped[str] = mapped_column(String(24), comment="履约状态")
    carrier: Mapped[str | None] = mapped_column(String(80), nullable=True, comment="物流公司")
    tracking_number: Mapped[str | None] = mapped_column(String(120), nullable=True, comment="物流单号")
    delivery_reference: Mapped[str | None] = mapped_column(String(200), nullable=True, comment="虚拟交付引用")
    shipped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="发货时间")
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="交付完成时间"
    )
    auto_confirm_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="实物自动确认收货时间"
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_by_id: Mapped[UUID | None] = mapped_column(nullable=True, comment="最后操作管理员")
    revision: Mapped[int] = mapped_column(Integer, default=1, comment="状态版本")


class FulfillmentEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "fulfillment_events"
    __table_args__ = (
        UniqueConstraint("fulfillment_id", "revision", name="uq_fulfillment_event_revision"),
        CheckConstraint(
            "to_status IN ('awaiting_shipment', 'shipped', 'awaiting_delivery', 'delivered', 'cancelled')",
            name="ck_fulfillment_event_status",
        ),
        CheckConstraint("actor_type IN ('admin', 'user', 'system', 'payment')", name="ck_fulfillment_event_actor"),
        {"comment": "履约状态事件"},
    )

    fulfillment_id: Mapped[UUID] = mapped_column(ForeignKey("fulfillments.id", ondelete="RESTRICT"), comment="履约单")
    revision: Mapped[int] = mapped_column(Integer, comment="对应履约版本")
    from_status: Mapped[str | None] = mapped_column(String(24), nullable=True, comment="原状态")
    to_status: Mapped[str] = mapped_column(String(24), comment="目标状态")
    actor_type: Mapped[str] = mapped_column(String(16), comment="操作者类型")
    actor_id: Mapped[UUID | None] = mapped_column(nullable=True, comment="操作者标识")
    reason: Mapped[str] = mapped_column(String(200), comment="状态原因")


class RefundRequest(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "refund_requests"
    __table_args__ = (
        UniqueConstraint("user_id", "request_id", name="uq_refund_request_user_request"),
        CheckConstraint(
            "status IN ('requested', 'approved', 'rejected', 'completed')", name="ck_refund_request_status"
        ),
        CheckConstraint("review_mode IN ('automatic', 'manual')", name="ck_refund_request_review_mode"),
        CheckConstraint(
            "items_amount >= 0 AND freight_amount >= 0 AND amount = items_amount + freight_amount",
            name="ck_refund_request_amount",
        ),
        CheckConstraint("currency = 'CNY'", name="ck_refund_request_currency"),
        Index("ix_refund_request_order_created", "order_id", "created_at", "id"),
        Index(
            "uq_refund_request_order_active",
            "order_id",
            unique=True,
            postgresql_where=text("status <> 'rejected'"),
        ),
        {"comment": "整单退款申请和审核事实"},
    )

    order_id: Mapped[UUID] = mapped_column(ForeignKey("orders.id", ondelete="RESTRICT"), comment="原订单")
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), comment="申请用户")
    request_id: Mapped[UUID] = mapped_column(comment="退款请求幂等标识")
    request_hash: Mapped[str] = mapped_column(String(64), comment="规范化退款请求摘要")
    status: Mapped[str] = mapped_column(String(16), default="requested", comment="退款状态")
    review_mode: Mapped[str] = mapped_column(String(16), comment="自动或人工审核")
    items_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), comment="原商品实付金额")
    freight_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), comment="原订单运费")
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), comment="整单退款总金额")
    currency: Mapped[str] = mapped_column(String(3), default="CNY", comment="币种")
    reason: Mapped[str] = mapped_column(String(300), comment="用户申请原因")
    review_note: Mapped[str | None] = mapped_column(String(300), nullable=True, comment="审核说明")
    reviewed_by_id: Mapped[UUID | None] = mapped_column(nullable=True, comment="审核管理员")
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="审核时间")
    fulfillment_status_snapshot: Mapped[str] = mapped_column(String(24), comment="申请时履约状态")
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="售后完成时间"
    )
    revision: Mapped[int] = mapped_column(Integer, default=1, comment="状态版本")


class RefundAttempt(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "refund_attempts"
    __table_args__ = (
        UniqueConstraint("merchant_refund_reference", name="uq_refund_attempt_merchant_reference"),
        UniqueConstraint("channel", "channel_refund_id", name="uq_refund_attempt_channel_refund"),
        UniqueConstraint("payment_attempt_id", "purpose", "attempt_no", name="uq_refund_attempt_payment_purpose_no"),
        CheckConstraint(
            "purpose IN ('after_sale', 'duplicate_payment', 'late_payment')", name="ck_refund_attempt_purpose"
        ),
        CheckConstraint("channel IN ('wechat', 'alipay')", name="ck_refund_attempt_channel"),
        CheckConstraint(
            "status IN ('created', 'processing', 'succeeded', 'abnormal', 'unknown', 'closed')",
            name="ck_refund_attempt_status",
        ),
        CheckConstraint("amount > 0", name="ck_refund_attempt_amount"),
        CheckConstraint("currency = 'CNY'", name="ck_refund_attempt_currency"),
        CheckConstraint("attempt_no > 0 AND revision > 0", name="ck_refund_attempt_revision"),
        CheckConstraint(
            "(purpose = 'after_sale' AND refund_request_id IS NOT NULL) OR "
            "(purpose <> 'after_sale' AND refund_request_id IS NULL)",
            name="ck_refund_attempt_request_purpose",
        ),
        Index("ix_refund_attempt_payment", "payment_attempt_id", "id"),
        Index("ix_refund_attempt_request", "refund_request_id", "id"),
        Index("ix_refund_attempt_status", "status", "id"),
        {"comment": "渠道退款执行意图和可信资金确认事实"},
    )

    order_id: Mapped[UUID] = mapped_column(ForeignKey("orders.id", ondelete="RESTRICT"), comment="关联订单")
    payment_attempt_id: Mapped[UUID] = mapped_column(
        ForeignKey("payment_attempts.id", ondelete="RESTRICT"), comment="原支付意图"
    )
    refund_request_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("refund_requests.id", ondelete="RESTRICT"), nullable=True, comment="整单售后申请"
    )
    purpose: Mapped[str] = mapped_column(String(24), comment="售后或异常收款退款用途")
    attempt_no: Mapped[int] = mapped_column(Integer, comment="原支付下执行序号")
    merchant_refund_reference: Mapped[str] = mapped_column(String(80), comment="商户退款号")
    request_hash: Mapped[str] = mapped_column(String(64), comment="固定退款意图摘要")
    channel: Mapped[str] = mapped_column(String(16), comment="原支付渠道")
    currency: Mapped[str] = mapped_column(String(3), default="CNY", comment="币种")
    channel_refund_id: Mapped[str | None] = mapped_column(String(160), nullable=True, comment="渠道退款流水")
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), comment="本次退款金额")
    status: Mapped[str] = mapped_column(String(24), default="created", comment="退款执行状态")
    channel_refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revision: Mapped[int] = mapped_column(Integer, default=1, comment="执行状态版本")
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RefundEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "refund_events"
    __table_args__ = (
        UniqueConstraint("refund_request_id", "revision", name="uq_refund_event_request_revision"),
        UniqueConstraint("refund_attempt_id", "revision", name="uq_refund_event_attempt_revision"),
        CheckConstraint(
            "to_status IN ('requested', 'approved', 'rejected', 'completed', 'created', 'processing', "
            "'succeeded', 'abnormal', 'unknown', 'closed')",
            name="ck_refund_event_status",
        ),
        CheckConstraint("actor_type IN ('admin', 'user', 'system', 'channel')", name="ck_refund_event_actor"),
        CheckConstraint("event_scope IN ('request', 'attempt')", name="ck_refund_event_scope"),
        CheckConstraint(
            "(event_scope = 'request' AND refund_request_id IS NOT NULL AND refund_attempt_id IS NULL) OR "
            "(event_scope = 'attempt' AND refund_request_id IS NULL AND refund_attempt_id IS NOT NULL)",
            name="ck_refund_event_target",
        ),
        {"comment": "退款申请或资金执行状态事件"},
    )

    refund_request_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("refund_requests.id", ondelete="RESTRICT"), nullable=True, comment="退款申请"
    )
    refund_attempt_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("refund_attempts.id", ondelete="RESTRICT"), nullable=True, comment="退款执行"
    )
    event_scope: Mapped[str] = mapped_column(String(16), comment="申请或执行")
    event_type: Mapped[str] = mapped_column(String(32), default="state_changed", comment="事件类型")
    revision: Mapped[int] = mapped_column(Integer, comment="对应退款版本")
    from_status: Mapped[str | None] = mapped_column(String(16), nullable=True, comment="原状态")
    to_status: Mapped[str] = mapped_column(String(16), comment="目标状态")
    actor_type: Mapped[str] = mapped_column(String(16), comment="操作者类型")
    actor_id: Mapped[UUID | None] = mapped_column(nullable=True, comment="操作者标识")
    reason: Mapped[str] = mapped_column(String(300), comment="状态原因")
    payload_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="已核对退款载荷摘要")


class RefundItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "refund_items"
    __table_args__ = (
        UniqueConstraint("refund_request_id", "order_item_id", name="uq_refund_item_request_order_item"),
        CheckConstraint("quantity BETWEEN 1 AND 999", name="ck_refund_item_quantity"),
        CheckConstraint("amount >= 0", name="ck_refund_item_amount"),
        {"comment": "退款覆盖的订单明细数量和商品金额"},
    )

    refund_request_id: Mapped[UUID] = mapped_column(
        ForeignKey("refund_requests.id", ondelete="RESTRICT"), comment="退款申请"
    )
    order_item_id: Mapped[UUID] = mapped_column(ForeignKey("order_items.id", ondelete="RESTRICT"), comment="订单明细")
    quantity: Mapped[int] = mapped_column(Integer, comment="退款数量")
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), comment="退款商品金额")


class ProductReview(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "product_reviews"
    __table_args__ = (
        UniqueConstraint("user_id", "order_item_id", name="uq_product_review_user_order_item"),
        CheckConstraint("rating BETWEEN 1 AND 5", name="ck_product_review_rating"),
        {"comment": "已交付订单明细的公开评价"},
    )

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), comment="评价用户")
    order_item_id: Mapped[UUID] = mapped_column(ForeignKey("order_items.id", ondelete="RESTRICT"), comment="订单明细")
    product_id: Mapped[UUID] = mapped_column(comment="商品标识")
    rating: Mapped[int] = mapped_column(Integer, comment="星级")
    content: Mapped[str] = mapped_column(String(1000), default="", comment="评价正文")
    is_published: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否公开展示")
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), comment="公开时间")


class ReconciliationRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "reconciliation_records"
    __table_args__ = (
        UniqueConstraint("channel", "record_type", "channel_transaction_id", name="uq_reconciliation_channel_record"),
        CheckConstraint("channel IN ('wechat', 'alipay')", name="ck_reconciliation_channel"),
        CheckConstraint("record_type IN ('payment', 'refund', 'withdrawal')", name="ck_reconciliation_record_type"),
        CheckConstraint("status IN ('matched', 'discrepancy')", name="ck_reconciliation_status"),
        CheckConstraint("resolution_status IN ('open', 'resolved')", name="ck_reconciliation_resolution_status"),
        CheckConstraint("amount > 0", name="ck_reconciliation_amount"),
        CheckConstraint("currency = 'CNY'", name="ck_reconciliation_currency"),
        CheckConstraint(
            "(record_type = 'payment' AND refund_attempt_id IS NULL AND withdrawal_request_id IS NULL) OR "
            "(record_type = 'refund' AND payment_attempt_id IS NULL AND withdrawal_request_id IS NULL) OR "
            "(record_type = 'withdrawal' AND payment_attempt_id IS NULL AND refund_attempt_id IS NULL)",
            name="ck_reconciliation_record_target",
        ),
        Index("ix_reconciliation_occurred", "occurred_at", "id"),
        {"comment": "渠道账单与本地支付事实对账记录"},
    )

    channel: Mapped[str] = mapped_column(String(16), comment="渠道")
    channel_transaction_id: Mapped[str] = mapped_column(String(160), comment="渠道交易流水")
    record_type: Mapped[str] = mapped_column(String(16), comment="收款、退款或提现")
    source_reference: Mapped[str] = mapped_column(String(160), comment="账单来源或批次引用")
    source_hash: Mapped[str] = mapped_column(String(64), comment="账单行摘要")
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), comment="渠道金额")
    currency: Mapped[str] = mapped_column(String(3), default="CNY", comment="币种")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), comment="渠道发生时间")
    status: Mapped[str] = mapped_column(String(16), comment="匹配或差异")
    payment_attempt_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("payment_attempts.id", ondelete="RESTRICT"), nullable=True, comment="匹配的支付意图"
    )
    refund_attempt_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("refund_attempts.id", ondelete="RESTRICT"), nullable=True, comment="匹配的退款执行"
    )
    withdrawal_request_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("withdrawal_requests.id", ondelete="RESTRICT"), nullable=True, comment="匹配的提现申请"
    )
    resolution_status: Mapped[str] = mapped_column(String(16), default="open", comment="人工处置状态")
    resolution_note: Mapped[str | None] = mapped_column(String(500), nullable=True, comment="处置说明与证据引用")
    resolved_by_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("admins.id", ondelete="RESTRICT"), nullable=True, comment="处置管理员"
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revision: Mapped[int] = mapped_column(Integer, default=1, comment="处置版本")
    note: Mapped[str | None] = mapped_column(String(300), nullable=True, comment="差异说明")
