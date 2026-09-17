"""Create payment, fulfillment, refund, review, and reconciliation tables.

Revision ID: 20260917_03
Revises: 20260917_02
This revision is a frozen PostgreSQL DDL snapshot and never imports runtime models.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260917_03"
down_revision: str | None = "20260917_02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "payment_attempts",
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("merchant_reference", sa.String(80), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("channel_transaction_id", sa.String(160), nullable=True),
        sa.Column("unavailable_reason", sa.String(200), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("user_id", "request_id", name="uq_payment_attempt_user_request"),
        sa.UniqueConstraint("merchant_reference", name="uq_payment_attempt_merchant_reference"),
        sa.UniqueConstraint("channel", "channel_transaction_id", name="uq_payment_attempt_channel_transaction"),
        sa.CheckConstraint("channel IN ('wechat', 'alipay')", name="ck_payment_attempt_channel"),
        sa.CheckConstraint(
            "status IN ('created', 'unavailable', 'pending', 'succeeded', 'closed', 'unknown')",
            name="ck_payment_attempt_status",
        ),
        sa.CheckConstraint("amount > 0", name="ck_payment_attempt_amount"),
        sa.CheckConstraint("currency = 'CNY'", name="ck_payment_attempt_currency"),
        comment="支付意图与渠道确认事实",
    )
    op.create_index("ix_payment_attempt_order_created", "payment_attempts", ["order_id", "created_at", "id"])
    op.create_table(
        "payment_events",
        sa.Column("payment_attempt_id", sa.Uuid(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("from_status", sa.String(16), nullable=True),
        sa.Column("to_status", sa.String(16), nullable=False),
        sa.Column("reason", sa.String(200), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["payment_attempt_id"], ["payment_attempts.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("payment_attempt_id", "revision", name="uq_payment_event_revision"),
        sa.CheckConstraint(
            "to_status IN ('created', 'unavailable', 'pending', 'succeeded', 'closed', 'unknown')",
            name="ck_payment_event_status",
        ),
        comment="支付意图状态事件",
    )
    op.create_table(
        "fulfillments",
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("product_type", sa.String(16), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("carrier", sa.String(80), nullable=True),
        sa.Column("tracking_number", sa.String(120), nullable=True),
        sa.Column("delivery_reference", sa.String(200), nullable=True),
        sa.Column("shipped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("auto_confirm_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("order_id", name="uq_fulfillment_order"),
        sa.CheckConstraint("product_type IN ('physical', 'virtual')", name="ck_fulfillment_product_type"),
        sa.CheckConstraint(
            "status IN ('awaiting_shipment', 'shipped', 'awaiting_delivery', 'delivered')",
            name="ck_fulfillment_status",
        ),
        comment="订单履约状态与物流或虚拟交付引用",
    )
    op.execute(
        "CREATE INDEX ix_fulfillment_auto_confirm ON fulfillments (auto_confirm_at, id) WHERE status = 'shipped'"
    )
    op.create_table(
        "fulfillment_events",
        sa.Column("fulfillment_id", sa.Uuid(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("from_status", sa.String(24), nullable=True),
        sa.Column("to_status", sa.String(24), nullable=False),
        sa.Column("actor_type", sa.String(16), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("reason", sa.String(200), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["fulfillment_id"], ["fulfillments.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("fulfillment_id", "revision", name="uq_fulfillment_event_revision"),
        sa.CheckConstraint(
            "to_status IN ('awaiting_shipment', 'shipped', 'awaiting_delivery', 'delivered')",
            name="ck_fulfillment_event_status",
        ),
        sa.CheckConstraint("actor_type IN ('admin', 'user', 'system', 'payment')", name="ck_fulfillment_event_actor"),
        comment="履约状态事件",
    )
    op.create_table(
        "refund_requests",
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("reason", sa.String(300), nullable=False),
        sa.Column("review_note", sa.String(300), nullable=True),
        sa.Column("reviewed_by_id", sa.Uuid(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("channel_refund_id", sa.String(160), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("user_id", "request_id", name="uq_refund_request_user_request"),
        sa.UniqueConstraint("channel_refund_id", name="uq_refund_request_channel_refund"),
        sa.CheckConstraint(
            "status IN ('requested', 'approved', 'rejected', 'processing', 'succeeded', 'unknown')",
            name="ck_refund_request_status",
        ),
        sa.CheckConstraint("amount > 0", name="ck_refund_request_amount"),
        sa.CheckConstraint("currency = 'CNY'", name="ck_refund_request_currency"),
        comment="退款申请与渠道退款确认事实",
    )
    op.create_index("ix_refund_request_order_created", "refund_requests", ["order_id", "created_at", "id"])
    op.create_table(
        "refund_events",
        sa.Column("refund_request_id", sa.Uuid(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("from_status", sa.String(16), nullable=True),
        sa.Column("to_status", sa.String(16), nullable=False),
        sa.Column("actor_type", sa.String(16), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("reason", sa.String(300), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["refund_request_id"], ["refund_requests.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("refund_request_id", "revision", name="uq_refund_event_revision"),
        sa.CheckConstraint(
            "to_status IN ('requested', 'approved', 'rejected', 'processing', 'succeeded', 'unknown')",
            name="ck_refund_event_status",
        ),
        sa.CheckConstraint("actor_type IN ('admin', 'user', 'payment')", name="ck_refund_event_actor"),
        comment="退款申请状态事件",
    )
    op.create_table(
        "refund_items",
        sa.Column("refund_request_id", sa.Uuid(), nullable=False),
        sa.Column("order_item_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["refund_request_id"], ["refund_requests.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["order_item_id"], ["order_items.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("refund_request_id", "order_item_id", name="uq_refund_item_request_order_item"),
        sa.CheckConstraint("quantity BETWEEN 1 AND 999", name="ck_refund_item_quantity"),
        sa.CheckConstraint("amount > 0", name="ck_refund_item_amount"),
        comment="退款覆盖的订单明细数量和商品金额",
    )
    op.create_table(
        "product_reviews",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("order_item_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("content", sa.String(1000), nullable=False),
        sa.Column("is_published", sa.Boolean(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["order_item_id"], ["order_items.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("user_id", "order_item_id", name="uq_product_review_user_order_item"),
        sa.CheckConstraint("rating BETWEEN 1 AND 5", name="ck_product_review_rating"),
        comment="已交付订单明细的公开评价",
    )
    op.create_table(
        "reconciliation_records",
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("channel_transaction_id", sa.String(160), nullable=False),
        sa.Column("source_reference", sa.String(160), nullable=False),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("payment_attempt_id", sa.Uuid(), nullable=True),
        sa.Column("note", sa.String(300), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["payment_attempt_id"], ["payment_attempts.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("channel", "channel_transaction_id", name="uq_reconciliation_channel_transaction"),
        sa.CheckConstraint("channel IN ('wechat', 'alipay')", name="ck_reconciliation_channel"),
        sa.CheckConstraint("status IN ('matched', 'discrepancy')", name="ck_reconciliation_status"),
        sa.CheckConstraint("amount > 0", name="ck_reconciliation_amount"),
        sa.CheckConstraint("currency = 'CNY'", name="ck_reconciliation_currency"),
        comment="渠道账单与本地支付事实对账记录",
    )
    op.create_index("ix_reconciliation_occurred", "reconciliation_records", ["occurred_at", "id"])


def downgrade() -> None:
    raise RuntimeError("支付和售后表包含渠道与资金事实，禁止自动删表降级；请使用备份恢复或前向修复。")
