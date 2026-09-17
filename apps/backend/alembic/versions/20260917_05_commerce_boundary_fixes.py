"""Add inventory transition evidence and channel-scoped refund confirmation.

Revision ID: 20260917_05
Revises: 20260917_04
Historical inventory events are not fabricated. Ambiguous old refund facts fail closed.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260917_05"
down_revision: str | None = "20260917_04"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_inventory_total_capacity", "inventory_accounts", "CAST(available AS BIGINT) + reserved <= 2147483647"
    )
    op.alter_column(
        "orders", "payment_reference", existing_type=sa.String(160), type_=sa.String(167), existing_nullable=True
    )
    op.add_column(
        "refund_requests", sa.Column("channel", sa.String(16), nullable=True, comment="已核对原支付的退款渠道")
    )
    op.add_column(
        "refund_events", sa.Column("payload_hash", sa.String(64), nullable=True, comment="已核对退款载荷摘要")
    )
    op.execute("""
        UPDATE refund_requests AS refund
        SET channel = payment.channel
        FROM payment_attempts AS payment
        WHERE refund.channel_refund_id IS NOT NULL
          AND payment.order_id = refund.order_id AND payment.status = 'succeeded'
          AND (SELECT count(*) FROM payment_attempts AS candidate
               WHERE candidate.order_id = refund.order_id AND candidate.status = 'succeeded') = 1
    """)
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM refund_requests WHERE channel_refund_id IS NOT NULL AND channel IS NULL) THEN
                RAISE EXCEPTION 'Refund channel backfill requires an unambiguous successful payment; reconcile before upgrade';
            END IF;
        END $$
    """)
    op.drop_constraint("uq_refund_request_channel_refund", "refund_requests", type_="unique")
    op.create_unique_constraint("uq_refund_request_channel_refund", "refund_requests", ["channel", "channel_refund_id"])
    op.create_check_constraint(
        "ck_refund_request_channel", "refund_requests", "channel IS NULL OR channel IN ('wechat', 'alipay')"
    )
    op.create_table(
        "inventory_reservation_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reservation_id", sa.Uuid(), nullable=False, comment="库存占用标识"),
        sa.Column("revision", sa.Integer(), nullable=False, comment="占用状态版本"),
        sa.Column("to_status", sa.String(16), nullable=False, comment="占用、确认或释放"),
        sa.Column("before_available", sa.Integer(), nullable=False, comment="变动前可售库存"),
        sa.Column("after_available", sa.Integer(), nullable=False, comment="变动后可售库存"),
        sa.Column("before_reserved", sa.Integer(), nullable=False, comment="变动前占用库存"),
        sa.Column("after_reserved", sa.Integer(), nullable=False, comment="变动后占用库存"),
        sa.Column("resulting_inventory_revision", sa.Integer(), nullable=False, comment="变动后库存账户版本"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["reservation_id"], ["inventory_reservations.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("reservation_id", "revision", name="uq_inventory_reservation_event_revision"),
        sa.CheckConstraint(
            "to_status IN ('reserved', 'confirmed', 'released')", name="ck_inventory_reservation_event_status"
        ),
        sa.CheckConstraint(
            "before_available >= 0 AND after_available >= 0 AND before_reserved >= 0 AND after_reserved >= 0",
            name="ck_inventory_reservation_event_balances",
        ),
        sa.CheckConstraint(
            "revision > 0 AND resulting_inventory_revision > 0", name="ck_inventory_reservation_event_revisions"
        ),
        comment="不可变订单库存占用、确认与释放流水",
    )


def downgrade() -> None:
    raise RuntimeError("Irreversible audit evidence migration; use a forward fix or an authorized database restore")
