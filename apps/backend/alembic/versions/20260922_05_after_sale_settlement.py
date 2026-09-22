"""Separate after-sale execution facts and settlement reconciliation.

Revision ID: 20260922_05
Revises: 20260922_04
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260922_05"
down_revision: str | None = "20260922_04"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Legacy partial-refund rows cannot truthfully become target-model whole-order facts.
    # Operators must reset the confirmed local development database or perform a separately
    # authorized historical-data migration before adopting this revision.
    op.execute(
        """
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM refund_requests)
               OR EXISTS (SELECT 1 FROM refund_events)
               OR EXISTS (SELECT 1 FROM refund_items)
               OR EXISTS (SELECT 1 FROM reconciliation_records) THEN
                RAISE EXCEPTION 'stage 5 target migration requires empty legacy refund and reconciliation tables';
            END IF;
        END $$
        """
    )

    op.create_table(
        "refund_attempts",
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("payment_attempt_id", sa.Uuid(), nullable=False),
        sa.Column("refund_request_id", sa.Uuid(), nullable=True),
        sa.Column("purpose", sa.String(24), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("merchant_refund_reference", sa.String(80), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="CNY"),
        sa.Column("channel_refund_id", sa.String(160), nullable=True),
        sa.Column("amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="created"),
        sa.Column("channel_refunded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["payment_attempt_id"], ["payment_attempts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["refund_request_id"], ["refund_requests.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("merchant_refund_reference", name="uq_refund_attempt_merchant_reference"),
        sa.UniqueConstraint("channel", "channel_refund_id", name="uq_refund_attempt_channel_refund"),
        sa.UniqueConstraint("payment_attempt_id", "purpose", "attempt_no", name="uq_refund_attempt_payment_purpose_no"),
        sa.CheckConstraint(
            "purpose IN ('after_sale', 'duplicate_payment', 'late_payment')", name="ck_refund_attempt_purpose"
        ),
        sa.CheckConstraint("channel IN ('wechat', 'alipay')", name="ck_refund_attempt_channel"),
        sa.CheckConstraint(
            "status IN ('created', 'processing', 'succeeded', 'abnormal', 'unknown', 'closed')",
            name="ck_refund_attempt_status",
        ),
        sa.CheckConstraint("amount > 0", name="ck_refund_attempt_amount"),
        sa.CheckConstraint("currency = 'CNY'", name="ck_refund_attempt_currency"),
        sa.CheckConstraint("attempt_no > 0 AND revision > 0", name="ck_refund_attempt_revision"),
        sa.CheckConstraint(
            "(purpose = 'after_sale' AND refund_request_id IS NOT NULL) OR "
            "(purpose <> 'after_sale' AND refund_request_id IS NULL)",
            name="ck_refund_attempt_request_purpose",
        ),
        comment="渠道退款执行意图和可信资金确认事实",
    )
    op.create_index("ix_refund_attempt_payment", "refund_attempts", ["payment_attempt_id", "id"])
    op.create_index("ix_refund_attempt_request", "refund_attempts", ["refund_request_id", "id"])
    op.create_index("ix_refund_attempt_status", "refund_attempts", ["status", "id"])
    op.alter_column("refund_attempts", "currency", server_default=None)
    op.alter_column("refund_attempts", "status", server_default=None)
    op.alter_column("refund_attempts", "revision", server_default=None)

    op.drop_constraint("uq_refund_request_channel_refund", "refund_requests", type_="unique")
    op.drop_constraint("ck_refund_request_channel", "refund_requests", type_="check")
    op.drop_constraint("ck_refund_request_status", "refund_requests", type_="check")
    op.drop_constraint("ck_refund_request_amount", "refund_requests", type_="check")
    op.drop_column("refund_requests", "channel_refund_id")
    op.drop_column("refund_requests", "channel")
    op.drop_column("refund_requests", "confirmed_at")
    op.add_column("refund_requests", sa.Column("review_mode", sa.String(16), nullable=False))
    op.add_column("refund_requests", sa.Column("items_amount", sa.Numeric(15, 2), nullable=False))
    op.add_column("refund_requests", sa.Column("freight_amount", sa.Numeric(15, 2), nullable=False))
    op.add_column("refund_requests", sa.Column("fulfillment_status_snapshot", sa.String(24), nullable=False))
    op.add_column("refund_requests", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint(
        "ck_refund_request_status", "refund_requests", "status IN ('requested', 'approved', 'rejected', 'completed')"
    )
    op.create_check_constraint(
        "ck_refund_request_review_mode", "refund_requests", "review_mode IN ('automatic', 'manual')"
    )
    op.create_check_constraint(
        "ck_refund_request_amount",
        "refund_requests",
        "items_amount >= 0 AND freight_amount >= 0 AND amount = items_amount + freight_amount",
    )
    op.create_index(
        "uq_refund_request_order_active",
        "refund_requests",
        ["order_id"],
        unique=True,
        postgresql_where=sa.text("status <> 'rejected'"),
    )

    op.drop_constraint("ck_refund_item_amount", "refund_items", type_="check")
    op.create_check_constraint("ck_refund_item_amount", "refund_items", "amount >= 0")

    op.drop_constraint("uq_refund_event_revision", "refund_events", type_="unique")
    op.drop_constraint("ck_refund_event_status", "refund_events", type_="check")
    op.drop_constraint("ck_refund_event_actor", "refund_events", type_="check")
    op.alter_column("refund_events", "refund_request_id", nullable=True)
    op.add_column("refund_events", sa.Column("refund_attempt_id", sa.Uuid(), nullable=True))
    op.add_column("refund_events", sa.Column("event_scope", sa.String(16), nullable=False))
    op.add_column(
        "refund_events", sa.Column("event_type", sa.String(32), nullable=False, server_default="state_changed")
    )
    op.create_foreign_key(
        "fk_refund_events_attempt",
        "refund_events",
        "refund_attempts",
        ["refund_attempt_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint("uq_refund_event_request_revision", "refund_events", ["refund_request_id", "revision"])
    op.create_unique_constraint("uq_refund_event_attempt_revision", "refund_events", ["refund_attempt_id", "revision"])
    op.create_check_constraint(
        "ck_refund_event_status",
        "refund_events",
        "to_status IN ('requested', 'approved', 'rejected', 'completed', 'created', 'processing', "
        "'succeeded', 'abnormal', 'unknown', 'closed')",
    )
    op.create_check_constraint(
        "ck_refund_event_actor", "refund_events", "actor_type IN ('admin', 'user', 'system', 'channel')"
    )
    op.create_check_constraint("ck_refund_event_scope", "refund_events", "event_scope IN ('request', 'attempt')")
    op.create_check_constraint(
        "ck_refund_event_target",
        "refund_events",
        "(event_scope = 'request' AND refund_request_id IS NOT NULL AND refund_attempt_id IS NULL) OR "
        "(event_scope = 'attempt' AND refund_request_id IS NULL AND refund_attempt_id IS NOT NULL)",
    )
    op.alter_column("refund_events", "event_type", server_default=None)

    op.drop_constraint("uq_reconciliation_channel_transaction", "reconciliation_records", type_="unique")
    op.add_column("reconciliation_records", sa.Column("record_type", sa.String(16), nullable=False))
    op.add_column("reconciliation_records", sa.Column("refund_attempt_id", sa.Uuid(), nullable=True))
    op.add_column("reconciliation_records", sa.Column("withdrawal_request_id", sa.Uuid(), nullable=True))
    op.add_column(
        "reconciliation_records", sa.Column("resolution_status", sa.String(16), nullable=False, server_default="open")
    )
    op.add_column("reconciliation_records", sa.Column("resolution_note", sa.String(500), nullable=True))
    op.add_column("reconciliation_records", sa.Column("resolved_by_id", sa.Uuid(), nullable=True))
    op.add_column("reconciliation_records", sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("reconciliation_records", sa.Column("revision", sa.Integer(), nullable=False, server_default="1"))
    op.create_foreign_key(
        "fk_reconciliation_refund_attempt",
        "reconciliation_records",
        "refund_attempts",
        ["refund_attempt_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_reconciliation_withdrawal",
        "reconciliation_records",
        "withdrawal_requests",
        ["withdrawal_request_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_reconciliation_resolved_by",
        "reconciliation_records",
        "admins",
        ["resolved_by_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_reconciliation_channel_record",
        "reconciliation_records",
        ["channel", "record_type", "channel_transaction_id"],
    )
    op.create_check_constraint(
        "ck_reconciliation_record_type", "reconciliation_records", "record_type IN ('payment', 'refund', 'withdrawal')"
    )
    op.create_check_constraint(
        "ck_reconciliation_resolution_status", "reconciliation_records", "resolution_status IN ('open', 'resolved')"
    )
    op.create_check_constraint(
        "ck_reconciliation_record_target",
        "reconciliation_records",
        "(record_type = 'payment' AND refund_attempt_id IS NULL AND withdrawal_request_id IS NULL) OR "
        "(record_type = 'refund' AND payment_attempt_id IS NULL AND withdrawal_request_id IS NULL) OR "
        "(record_type = 'withdrawal' AND payment_attempt_id IS NULL AND refund_attempt_id IS NULL)",
    )
    op.alter_column("reconciliation_records", "resolution_status", server_default=None)
    op.alter_column("reconciliation_records", "revision", server_default=None)


def downgrade() -> None:
    raise RuntimeError("退款执行、钱包和对账事实不能安全降级；请前向修复或恢复已授权备份。")
