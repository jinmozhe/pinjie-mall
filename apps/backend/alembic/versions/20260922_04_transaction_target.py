"""Create purchase limits and align transaction tables with the target model.

Revision ID: 20260922_04
Revises: 20260922_03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260922_04"
down_revision: str | None = "20260922_03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "product_purchase_limits",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("purchased_quantity", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("reserved_quantity", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("user_id", "product_id", name="uq_product_purchase_limit_user_product"),
        sa.CheckConstraint(
            "purchased_quantity >= 0 AND reserved_quantity >= 0", name="ck_product_purchase_limit_amounts"
        ),
        sa.CheckConstraint("revision > 0", name="ck_product_purchase_limit_revision"),
        comment="用户跨 SKU 累计限购账户",
    )
    op.create_index("ix_product_purchase_limit_product", "product_purchase_limits", ["product_id", "id"])
    op.create_table(
        "product_purchase_records",
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("limit_snapshot", sa.Integer(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("order_id", "product_id", name="uq_product_purchase_record_order_product"),
        sa.CheckConstraint("quantity > 0", name="ck_product_purchase_record_quantity"),
        sa.CheckConstraint(
            "status IN ('reserved', 'confirmed', 'released', 'refunded')", name="ck_product_purchase_record_status"
        ),
        sa.CheckConstraint("limit_snapshot >= 0", name="ck_product_purchase_record_limit"),
        sa.CheckConstraint("revision > 0", name="ck_product_purchase_record_revision"),
        sa.CheckConstraint(
            "(status = 'reserved' AND confirmed_at IS NULL AND released_at IS NULL AND refunded_at IS NULL) OR "
            "(status = 'confirmed' AND confirmed_at IS NOT NULL AND released_at IS NULL AND refunded_at IS NULL) OR "
            "(status = 'released' AND confirmed_at IS NULL AND released_at IS NOT NULL AND refunded_at IS NULL) OR "
            "(status = 'refunded' AND confirmed_at IS NOT NULL AND released_at IS NULL AND refunded_at IS NOT NULL)",
            name="ck_product_purchase_record_timestamps",
        ),
        comment="订单商品限购预占、成交和退款事实",
    )
    op.create_index(
        "ix_product_purchase_record_user_product", "product_purchase_records", ["user_id", "product_id", "id"]
    )

    op.drop_constraint("uq_orders_payment_reference", "orders", type_="unique")
    op.drop_constraint("ck_order_shipping_snapshot", "orders", type_="check")
    op.drop_constraint("ck_order_paid_fact", "orders", type_="check")
    op.add_column("orders", sa.Column("buyer_level_id", sa.Uuid(), nullable=True))
    op.add_column("orders", sa.Column("buyer_level_snapshot", postgresql.JSONB(), nullable=False))
    op.add_column("orders", sa.Column("commission_policy_id", sa.Uuid(), nullable=True))
    op.add_column("orders", sa.Column("commission_result_snapshot", postgresql.JSONB(), nullable=True))
    op.add_column("orders", sa.Column("accepted_payment_attempt_id", sa.Uuid(), nullable=True))
    op.add_column("orders", sa.Column("settlement_kind", sa.String(16), nullable=True))
    op.add_column("orders", sa.Column("zero_confirmation_id", sa.Uuid(), nullable=True))
    op.add_column("orders", sa.Column("acceptance_status", sa.String(16), nullable=False, server_default="pending"))
    op.add_column("orders", sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("orders", sa.Column("accepted_by_id", sa.Uuid(), nullable=True))
    op.drop_column("orders", "payment_reference")
    op.alter_column("orders", "shipping_snapshot", type_=postgresql.JSONB(), existing_type=postgresql.JSONB())
    op.create_foreign_key(
        "fk_orders_buyer_level", "orders", "member_levels", ["buyer_level_id"], ["id"], ondelete="RESTRICT"
    )
    op.create_foreign_key(
        "fk_orders_commission_policy",
        "orders",
        "commission_policies",
        ["commission_policy_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_orders_payment_attempt",
        "orders",
        "payment_attempts",
        ["accepted_payment_attempt_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key("fk_orders_accepted_by", "orders", "admins", ["accepted_by_id"], ["id"], ondelete="RESTRICT")
    op.create_unique_constraint("uq_orders_accepted_payment_attempt", "orders", ["accepted_payment_attempt_id"])
    op.create_unique_constraint("uq_orders_zero_confirmation", "orders", ["zero_confirmation_id"])
    op.create_check_constraint("ck_order_shipping_snapshot", "orders", "jsonb_typeof(shipping_snapshot) = 'object'")
    op.create_check_constraint(
        "ck_order_buyer_level_snapshot", "orders", "jsonb_typeof(buyer_level_snapshot) = 'object'"
    )
    op.create_check_constraint(
        "ck_order_commission_result_snapshot",
        "orders",
        "commission_result_snapshot IS NULL OR jsonb_typeof(commission_result_snapshot) = 'object'",
    )
    op.create_check_constraint(
        "ck_order_paid_fact",
        "orders",
        "(status = 'paid' AND paid_at IS NOT NULL AND settlement_kind IS NOT NULL) OR (status <> 'paid' AND paid_at IS NULL AND settlement_kind IS NULL)",
    )
    op.create_check_constraint(
        "ck_order_settlement_fact",
        "orders",
        "(settlement_kind = 'channel' AND accepted_payment_attempt_id IS NOT NULL AND zero_confirmation_id IS NULL) OR (settlement_kind = 'zero_amount' AND accepted_payment_attempt_id IS NULL AND zero_confirmation_id IS NOT NULL) OR (settlement_kind IS NULL AND accepted_payment_attempt_id IS NULL AND zero_confirmation_id IS NULL)",
    )
    op.create_check_constraint(
        "ck_order_acceptance_fact",
        "orders",
        "(acceptance_status = 'pending' AND accepted_at IS NULL AND accepted_by_id IS NULL) OR (acceptance_status = 'accepted' AND accepted_at IS NOT NULL AND accepted_by_id IS NOT NULL)",
    )
    op.alter_column("orders", "acceptance_status", server_default=None)

    op.add_column("order_items", sa.Column("price_snapshot", postgresql.JSONB(), nullable=False))
    op.add_column("order_items", sa.Column("commission_snapshot", postgresql.JSONB(), nullable=False))
    op.add_column("order_items", sa.Column("category_snapshot", postgresql.JSONB(), nullable=False))
    op.add_column("order_items", sa.Column("brand_snapshot", postgresql.JSONB(), nullable=True))
    op.alter_column("order_items", "weight_grams", nullable=True)
    op.add_column("order_events", sa.Column("event_type", sa.String(32), nullable=False))

    op.add_column("payment_attempts", sa.Column("channel_paid_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("payment_attempts", sa.Column("channel_context", postgresql.JSONB(), nullable=False))
    op.add_column("fulfillments", sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True))
    op.drop_constraint("ck_fulfillment_status", "fulfillments", type_="check")
    op.create_check_constraint(
        "ck_fulfillment_status",
        "fulfillments",
        "status IN ('awaiting_shipment', 'shipped', 'awaiting_delivery', 'delivered', 'cancelled')",
    )
    op.drop_constraint("ck_fulfillment_event_status", "fulfillment_events", type_="check")
    op.create_check_constraint(
        "ck_fulfillment_event_status",
        "fulfillment_events",
        "to_status IN ('awaiting_shipment', 'shipped', 'awaiting_delivery', 'delivered', 'cancelled')",
    )


def downgrade() -> None:
    raise RuntimeError("交易快照、限购和支付确认可能已被不可变业务事实引用，禁止自动破坏性降级；请前向修复或恢复备份。")
