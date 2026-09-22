"""Add membership qualification and points ledger domain tables.

Revision ID: 20260922_06
Revises: 20260922_05
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260922_06"
down_revision: str | None = "20260922_05"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "member_level_conditions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("level_id", sa.Uuid(), nullable=False),
        sa.Column("metric", sa.String(24), nullable=False),
        sa.Column("aggregation", sa.String(16), nullable=False),
        sa.Column("amount_threshold", sa.Numeric(15, 2), nullable=True),
        sa.Column("count_threshold", sa.BigInteger(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["level_id"], ["member_levels.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["updated_by"], ["admins.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("level_id", "metric", "aggregation", name="uq_member_level_condition"),
        sa.CheckConstraint(
            "metric IN ('consumption', 'invite_count', 'points')", name="ck_member_level_condition_metric"
        ),
        sa.CheckConstraint("aggregation IN ('single', 'cumulative')", name="ck_member_level_condition_aggregation"),
        sa.CheckConstraint(
            "(metric = 'consumption' AND amount_threshold IS NOT NULL AND amount_threshold >= 0 "
            "AND count_threshold IS NULL) OR "
            "(metric IN ('invite_count', 'points') AND count_threshold IS NOT NULL AND count_threshold >= 0 "
            "AND amount_threshold IS NULL)",
            name="ck_member_level_condition_threshold",
        ),
        sa.CheckConstraint("revision > 0", name="ck_member_level_condition_revision"),
        comment="会员自动资格评估条件",
    )
    op.create_index("ix_member_level_condition_level", "member_level_conditions", ["level_id", "is_active", "id"])

    op.create_table(
        "membership_qualification_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("metric", sa.String(24), nullable=False),
        sa.Column("source_type", sa.String(24), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=True),
        sa.Column("amount_delta", sa.Numeric(15, 2), nullable=True),
        sa.Column("count_delta", sa.BigInteger(), nullable=True),
        sa.Column("reverses_event_id", sa.Uuid(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reverses_event_id"], ["membership_qualification_events.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("idempotency_key", name="uq_membership_qualification_event_idempotency"),
        sa.UniqueConstraint("user_id", "source_type", "source_id", "metric", name="uq_membership_qualification_source"),
        sa.CheckConstraint(
            "metric IN ('consumption', 'invite_count', 'points')", name="ck_membership_qualification_metric"
        ),
        sa.CheckConstraint(
            "source_type IN ('order_confirm', 'refund', 'invite_validated', 'points_grant', 'points_reverse', 'manual')",
            name="ck_membership_qualification_source_type",
        ),
        sa.CheckConstraint(
            "(amount_delta IS NOT NULL AND amount_delta <> 0 AND count_delta IS NULL) OR "
            "(amount_delta IS NULL AND count_delta IS NOT NULL AND count_delta <> 0)",
            name="ck_membership_qualification_delta",
        ),
        comment="可冲销的会员资格贡献事实",
    )
    op.create_index(
        "ix_membership_qualification_user_metric", "membership_qualification_events", ["user_id", "metric", "id"]
    )

    op.create_table(
        "member_level_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("from_level_id", sa.Uuid(), nullable=True),
        sa.Column("to_level_id", sa.Uuid(), nullable=True),
        sa.Column("trigger_type", sa.String(24), nullable=False),
        sa.Column("trigger_id", sa.Uuid(), nullable=True),
        sa.Column("qualification_snapshot", sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column("profile_revision", sa.Integer(), nullable=False),
        sa.Column("operator_id", sa.Uuid(), nullable=True),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["from_level_id"], ["member_levels.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["to_level_id"], ["member_levels.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["operator_id"], ["admins.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("idempotency_key", name="uq_member_level_event_idempotency"),
        sa.UniqueConstraint("user_id", "profile_revision", name="uq_member_level_event_profile_revision"),
        sa.CheckConstraint(
            "trigger_type IN ('manual', 'order', 'refund', 'invite', 'policy_reassessment', 'points')",
            name="ck_member_level_event_trigger",
        ),
        sa.CheckConstraint("profile_revision > 0", name="ck_member_level_event_profile_revision"),
        sa.CheckConstraint("from_level_id IS DISTINCT FROM to_level_id", name="ck_member_level_event_change"),
        comment="会员等级变更的不可变历史",
    )
    op.create_index("ix_member_level_event_user", "member_level_events", ["user_id", "id"])

    op.create_table(
        "points_accounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("available_points", sa.BigInteger(), nullable=False),
        sa.Column("frozen_points", sa.BigInteger(), nullable=False),
        sa.Column("debt_points", sa.BigInteger(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("user_id", name="uq_points_account_user"),
        sa.CheckConstraint("available_points >= 0", name="ck_points_account_available"),
        sa.CheckConstraint("frozen_points >= 0", name="ck_points_account_frozen"),
        sa.CheckConstraint("debt_points >= 0", name="ck_points_account_debt"),
        sa.CheckConstraint("revision > 0", name="ck_points_account_revision"),
        comment="用户积分余额，不属于人民币钱包",
    )

    op.create_table(
        "points_ledgers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("entry_type", sa.String(24), nullable=False),
        sa.Column("available_delta", sa.BigInteger(), nullable=False),
        sa.Column("frozen_delta", sa.BigInteger(), nullable=False),
        sa.Column("debt_delta", sa.BigInteger(), nullable=False),
        sa.Column("source_type", sa.String(24), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("reverses_ledger_id", sa.Uuid(), nullable=True),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("note", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["account_id"], ["points_accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reverses_ledger_id"], ["points_ledgers.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("idempotency_key", name="uq_points_ledger_idempotency"),
        sa.CheckConstraint(
            "entry_type IN ('grant', 'spend', 'freeze', 'release', 'reverse', 'expire')", name="ck_points_ledger_type"
        ),
        sa.CheckConstraint(
            "source_type IN ('invite', 'order', 'refund', 'redemption', 'manual')", name="ck_points_ledger_source"
        ),
        sa.CheckConstraint(
            "available_delta <> 0 OR frozen_delta <> 0 OR debt_delta <> 0", name="ck_points_ledger_delta"
        ),
        comment="不可变积分收支与冲销流水",
    )
    op.create_index("ix_points_ledger_account", "points_ledgers", ["account_id", "id"])


def downgrade() -> None:
    raise RuntimeError("会员资格和积分账本事实不能安全降级；请前向修复或恢复已授权备份。")
