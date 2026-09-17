"""Create membership distribution, dual-wallet, and withdrawal tables.

Revision ID: 20260917_04
Revises: 20260917_03
This revision is a frozen PostgreSQL DDL snapshot and never imports runtime models.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260917_04"
down_revision: str | None = "20260917_03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "member_profiles",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("invitation_code", sa.String(16), nullable=False),
        sa.Column("level_code", sa.String(32), nullable=False),
        sa.Column("inviter_id", sa.Uuid(), nullable=True),
        sa.Column("bound_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["inviter_id"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("user_id", name="uq_member_profile_user"),
        sa.UniqueConstraint("invitation_code", name="uq_member_profile_invitation_code"),
        sa.CheckConstraint("level_code = 'standard'", name="ck_member_profile_initial_level"),
        comment="会员档案与不可变首次推荐关系",
    )
    op.create_index("ix_member_profile_inviter", "member_profiles", ["inviter_id", "id"])
    op.create_table(
        "wallet_accounts",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("wallet_type", sa.String(16), nullable=False),
        sa.Column("available_amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("frozen_amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("debt_amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("user_id", "wallet_type", name="uq_wallet_account_user_type"),
        sa.CheckConstraint("wallet_type IN ('commission', 'consumption')", name="ck_wallet_account_type"),
        sa.CheckConstraint("available_amount >= 0", name="ck_wallet_account_available_nonnegative"),
        sa.CheckConstraint("frozen_amount >= 0", name="ck_wallet_account_frozen_nonnegative"),
        sa.CheckConstraint("debt_amount >= 0", name="ck_wallet_account_debt_nonnegative"),
        comment="双轨钱包账户余额与追回欠款",
    )
    op.create_table(
        "commission_records",
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("source_user_id", sa.Uuid(), nullable=False),
        sa.Column("beneficiary_user_id", sa.Uuid(), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("base_amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("rate", sa.Numeric(5, 4), nullable=False),
        sa.Column("amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("recovered_amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("settle_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recovered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["beneficiary_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("order_id", "level", name="uq_commission_order_level"),
        sa.CheckConstraint("level IN (1, 2)", name="ck_commission_level"),
        sa.CheckConstraint("rate IN (0.1000, 0.0500)", name="ck_commission_rate"),
        sa.CheckConstraint("base_amount > 0", name="ck_commission_base_positive"),
        sa.CheckConstraint("amount > 0", name="ck_commission_amount_positive"),
        sa.CheckConstraint(
            "recovered_amount >= 0 AND recovered_amount <= amount", name="ck_commission_recovered_range"
        ),
        sa.CheckConstraint("status IN ('frozen', 'settled', 'recovered')", name="ck_commission_status"),
        comment="两级分佣规则快照与生命周期",
    )
    op.create_index("ix_commission_settle_due", "commission_records", ["status", "settle_after", "id"])
    op.create_index("ix_commission_beneficiary", "commission_records", ["beneficiary_user_id", "created_at", "id"])
    op.create_table(
        "commission_recoveries",
        sa.Column("commission_id", sa.Uuid(), nullable=False),
        sa.Column("refund_request_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["commission_id"], ["commission_records.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["refund_request_id"], ["refund_requests.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("commission_id", "refund_request_id", name="uq_commission_recovery_refund"),
        sa.CheckConstraint("amount > 0", name="ck_commission_recovery_amount_positive"),
        comment="退款与佣金追回的幂等关联",
    )
    op.create_table(
        "wallet_ledgers",
        sa.Column("wallet_id", sa.Uuid(), nullable=False),
        sa.Column("entry_type", sa.String(32), nullable=False),
        sa.Column("amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("frozen_delta", sa.Numeric(15, 2), nullable=False),
        sa.Column("debt_delta", sa.Numeric(15, 2), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("reference_type", sa.String(32), nullable=False),
        sa.Column("reference_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["wallet_id"], ["wallet_accounts.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("idempotency_key", name="uq_wallet_ledger_idempotency"),
        sa.CheckConstraint(
            "entry_type IN ('commission_settlement', 'commission_recovery', 'withdrawal_freeze', 'withdrawal_release')",
            name="ck_wallet_ledger_entry_type",
        ),
        sa.CheckConstraint(
            "amount <> 0 OR frozen_delta <> 0 OR debt_delta <> 0", name="ck_wallet_ledger_delta_nonzero"
        ),
        comment="钱包不可变业务流水",
    )
    op.create_index("ix_wallet_ledger_wallet_created", "wallet_ledgers", ["wallet_id", "created_at", "id"])
    op.create_table(
        "withdrawal_requests",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("wallet_id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("destination_reference", sa.String(180), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("review_note", sa.String(300), nullable=True),
        sa.Column("reviewed_by_id", sa.Uuid(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("channel_reference", sa.String(160), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["wallet_id"], ["wallet_accounts.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("user_id", "request_id", name="uq_withdrawal_user_request"),
        sa.UniqueConstraint("channel_reference", name="uq_withdrawal_channel_reference"),
        sa.CheckConstraint(
            "status IN ('requested', 'approved', 'rejected', 'processing', 'succeeded', 'unknown')",
            name="ck_withdrawal_status",
        ),
        sa.CheckConstraint("amount > 0", name="ck_withdrawal_amount_positive"),
        sa.CheckConstraint("currency = 'CNY'", name="ck_withdrawal_currency"),
        comment="佣金钱包提现申请与渠道执行状态",
    )
    op.create_index("ix_withdrawal_status_created", "withdrawal_requests", ["status", "created_at", "id"])


def downgrade() -> None:
    raise RuntimeError("分销与钱包表包含资金追溯事实，禁止自动删表降级；请使用备份恢复或前向修复。")
