"""Create versioned commission policies and durable task foundations.

Revision ID: 20260922_03
Revises: 20260922_02
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260922_03"
down_revision: str | None = "20260922_02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COMMISSION_CONTROL_ID = "0198f8a0-0000-7000-8000-000000000005"


def _reject_legacy_financial_facts() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM commission_records)
             OR EXISTS (SELECT 1 FROM commission_recoveries)
             OR EXISTS (SELECT 1 FROM wallet_ledgers)
             OR EXISTS (SELECT 1 FROM withdrawal_requests) THEN
            RAISE EXCEPTION 'cannot upgrade legacy financial facts to the target commission model; restore a clean development database or perform a reviewed forward migration';
          END IF;
        END $$;
        """
    )


def upgrade() -> None:
    _reject_legacy_financial_facts()
    op.create_table(
        "commission_policies",
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("default_mode", sa.String(16), nullable=True),
        sa.Column("default_amount_per_unit", sa.Numeric(15, 2), nullable=True),
        sa.Column("default_percentage_rate", sa.Numeric(7, 6), nullable=True),
        sa.Column("max_depth", sa.Integer(), nullable=False),
        sa.Column("settle_delay_days", sa.Integer(), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("content_version", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["updated_by"], ["admins.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("content_version", name="uq_commission_policy_content_version"),
        sa.CheckConstraint("status IN ('draft', 'active', 'retired')", name="ck_commission_policy_status"),
        sa.CheckConstraint("max_depth BETWEEN 1 AND 3", name="ck_commission_policy_max_depth"),
        sa.CheckConstraint("settle_delay_days >= 0", name="ck_commission_policy_settle_delay"),
        sa.CheckConstraint("content_version > 0", name="ck_commission_policy_content_version"),
        sa.CheckConstraint("revision > 0", name="ck_commission_policy_revision"),
        sa.CheckConstraint(
            "(default_mode IS NULL AND default_amount_per_unit IS NULL AND default_percentage_rate IS NULL) OR "
            "(default_mode = 'fixed_amount' AND default_amount_per_unit IS NOT NULL AND default_amount_per_unit >= 0 AND default_percentage_rate IS NULL) OR "
            "(default_mode = 'percentage' AND default_percentage_rate IS NOT NULL AND default_percentage_rate >= 0 AND default_percentage_rate <= 1 AND default_amount_per_unit IS NULL) OR "
            "(default_mode = 'disabled' AND default_amount_per_unit IS NULL AND default_percentage_rate IS NULL)",
            name="ck_commission_policy_default_value",
        ),
        comment="可发布且内容冻结的三级预算分佣政策",
    )
    op.create_index(
        "uq_commission_policy_active",
        "commission_policies",
        ["status"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_index("ix_commission_policy_status", "commission_policies", ["status", "id"])
    op.create_table(
        "commission_amount_rules",
        sa.Column("policy_id", sa.Uuid(), nullable=False),
        sa.Column("buyer_scope", sa.String(8), nullable=False),
        sa.Column("buyer_level_id", sa.Uuid(), nullable=True),
        sa.Column("product_id", sa.Uuid(), nullable=True),
        sa.Column("sku_id", sa.Uuid(), nullable=True),
        sa.Column("rule_mode", sa.String(16), nullable=False),
        sa.Column("amount_per_unit", sa.Numeric(15, 2), nullable=True),
        sa.Column("percentage_rate", sa.Numeric(7, 6), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["policy_id"], ["commission_policies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["buyer_level_id"], ["member_levels.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["sku_id"], ["product_skus.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("buyer_scope IN ('any', 'level')", name="ck_commission_amount_rule_buyer_scope"),
        sa.CheckConstraint(
            "rule_mode IN ('fixed_amount', 'percentage', 'disabled')", name="ck_commission_amount_rule_mode"
        ),
        sa.CheckConstraint(
            "(buyer_scope = 'any' AND buyer_level_id IS NULL) OR (buyer_scope = 'level' AND buyer_level_id IS NOT NULL)",
            name="ck_commission_amount_rule_buyer_level",
        ),
        sa.CheckConstraint(
            "(product_id IS NOT NULL AND sku_id IS NULL) OR (product_id IS NULL AND sku_id IS NOT NULL)",
            name="ck_commission_amount_rule_target",
        ),
        sa.CheckConstraint(
            "(rule_mode = 'fixed_amount' AND amount_per_unit IS NOT NULL AND amount_per_unit >= 0 AND percentage_rate IS NULL) OR "
            "(rule_mode = 'percentage' AND percentage_rate IS NOT NULL AND percentage_rate >= 0 AND percentage_rate <= 1 AND amount_per_unit IS NULL) OR "
            "(rule_mode = 'disabled' AND amount_per_unit IS NULL AND percentage_rate IS NULL)",
            name="ck_commission_amount_rule_value",
        ),
        comment="商品或 SKU 的佣金来源预算规则",
    )
    op.create_index(
        "uq_commission_amount_rule_product_any",
        "commission_amount_rules",
        ["policy_id", "product_id"],
        unique=True,
        postgresql_where=sa.text("product_id IS NOT NULL AND buyer_scope = 'any'"),
    )
    op.create_index(
        "uq_commission_amount_rule_product_level",
        "commission_amount_rules",
        ["policy_id", "product_id", "buyer_level_id"],
        unique=True,
        postgresql_where=sa.text("product_id IS NOT NULL AND buyer_scope = 'level'"),
    )
    op.create_index(
        "uq_commission_amount_rule_sku_any",
        "commission_amount_rules",
        ["policy_id", "sku_id"],
        unique=True,
        postgresql_where=sa.text("sku_id IS NOT NULL AND buyer_scope = 'any'"),
    )
    op.create_index(
        "uq_commission_amount_rule_sku_level",
        "commission_amount_rules",
        ["policy_id", "sku_id", "buyer_level_id"],
        unique=True,
        postgresql_where=sa.text("sku_id IS NOT NULL AND buyer_scope = 'level'"),
    )
    op.create_index("ix_commission_amount_rule_policy", "commission_amount_rules", ["policy_id", "id"])
    op.create_table(
        "commission_distribution_rules",
        sa.Column("policy_id", sa.Uuid(), nullable=False),
        sa.Column("buyer_level_id", sa.Uuid(), nullable=False),
        sa.Column("ancestor_depth", sa.Integer(), nullable=False),
        sa.Column("beneficiary_level_id", sa.Uuid(), nullable=False),
        sa.Column("allocation_mode", sa.String(16), nullable=False),
        sa.Column("rate", sa.Numeric(7, 6), nullable=True),
        sa.Column("amount_per_unit", sa.Numeric(15, 2), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["policy_id"], ["commission_policies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["buyer_level_id"], ["member_levels.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["beneficiary_level_id"], ["member_levels.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "policy_id",
            "buyer_level_id",
            "ancestor_depth",
            "beneficiary_level_id",
            name="uq_commission_distribution_rule",
        ),
        sa.CheckConstraint("ancestor_depth BETWEEN 1 AND 3", name="ck_commission_distribution_rule_depth"),
        sa.CheckConstraint(
            "allocation_mode IN ('percentage', 'fixed_amount')", name="ck_commission_distribution_rule_mode"
        ),
        sa.CheckConstraint(
            "(allocation_mode = 'percentage' AND rate IS NOT NULL AND rate >= 0 AND rate <= 1 AND amount_per_unit IS NULL) OR "
            "(allocation_mode = 'fixed_amount' AND amount_per_unit IS NOT NULL AND amount_per_unit >= 0 AND rate IS NULL)",
            name="ck_commission_distribution_rule_value",
        ),
        comment="按买家等级和真实推荐距离匹配的佣金矩阵",
    )
    op.create_index(
        "ix_commission_distribution_rule_policy", "commission_distribution_rules", ["policy_id", "ancestor_depth", "id"]
    )
    op.create_table(
        "durable_tasks",
        sa.Column("task_type", sa.String(64), nullable=False),
        sa.Column("business_key", sa.String(160), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("failure_count", sa.Integer(), nullable=False),
        sa.Column("max_failures", sa.Integer(), nullable=False),
        sa.Column("lease_token", sa.Uuid(), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(64), nullable=True),
        sa.Column("last_error_summary", sa.String(500), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_type", "business_key", name="uq_durable_task_type_business_key"),
        sa.CheckConstraint("status IN ('pending', 'running', 'succeeded', 'attention')", name="ck_durable_task_status"),
        sa.CheckConstraint("attempt_count >= 0", name="ck_durable_task_attempt_count"),
        sa.CheckConstraint("failure_count >= 0", name="ck_durable_task_failure_count"),
        sa.CheckConstraint("max_failures > 0", name="ck_durable_task_max_failures"),
        sa.CheckConstraint("revision > 0", name="ck_durable_task_revision"),
        sa.CheckConstraint("jsonb_typeof(payload) = 'object'", name="ck_durable_task_payload_object"),
        sa.CheckConstraint(
            "(status = 'running' AND lease_token IS NOT NULL AND lease_until IS NOT NULL AND completed_at IS NULL) OR "
            "(status = 'succeeded' AND lease_token IS NULL AND lease_until IS NULL AND completed_at IS NOT NULL) OR "
            "(status IN ('pending', 'attention') AND lease_token IS NULL AND lease_until IS NULL AND completed_at IS NULL)",
            name="ck_durable_task_state_columns",
        ),
        comment="可恢复且带租约的数据库持久任务",
    )
    op.create_index(
        "ix_durable_task_pending",
        "durable_tasks",
        ["available_at", "id"],
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_index(
        "ix_durable_task_running",
        "durable_tasks",
        ["lease_until", "id"],
        postgresql_where=sa.text("status = 'running'"),
    )
    op.drop_constraint("uq_commission_order_level", "commission_records", type_="unique")
    op.drop_constraint("ck_commission_level", "commission_records", type_="check")
    op.drop_constraint("ck_commission_rate", "commission_records", type_="check")
    op.add_column("commission_records", sa.Column("order_item_id", sa.Uuid(), nullable=False))
    op.add_column("commission_records", sa.Column("policy_id", sa.Uuid(), nullable=False))
    op.add_column("commission_records", sa.Column("revision", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("commission_records", sa.Column("rule_snapshot", postgresql.JSONB(), nullable=False))
    op.alter_column("commission_records", "rate", existing_type=sa.Numeric(5, 4), type_=sa.Numeric(7, 6), nullable=True)
    op.alter_column("commission_records", "revision", server_default=None)
    op.create_foreign_key(
        "fk_commission_records_order_item",
        "commission_records",
        "order_items",
        ["order_item_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_commission_records_policy",
        "commission_records",
        "commission_policies",
        ["policy_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint("uq_commission_order_item_level", "commission_records", ["order_item_id", "level"])
    op.create_check_constraint("ck_commission_level", "commission_records", "level BETWEEN 1 AND 3")
    op.create_check_constraint("ck_commission_revision", "commission_records", "revision > 0")
    op.drop_index("ix_commission_beneficiary", table_name="commission_records")
    op.create_index("ix_commission_beneficiary", "commission_records", ["beneficiary_user_id", "id"])
    op.add_column(
        "commission_recoveries",
        sa.Column("cancelled_frozen_amount", sa.Numeric(15, 2), nullable=False, server_default="0.00"),
    )
    op.add_column(
        "commission_recoveries",
        sa.Column("wallet_deducted_amount", sa.Numeric(15, 2), nullable=False, server_default="0.00"),
    )
    op.add_column(
        "commission_recoveries",
        sa.Column("debt_created_amount", sa.Numeric(15, 2), nullable=False, server_default="0.00"),
    )
    op.alter_column("commission_recoveries", "cancelled_frozen_amount", server_default=None)
    op.alter_column("commission_recoveries", "wallet_deducted_amount", server_default=None)
    op.alter_column("commission_recoveries", "debt_created_amount", server_default=None)
    op.create_check_constraint(
        "ck_commission_recovery_components",
        "commission_recoveries",
        "cancelled_frozen_amount >= 0 AND wallet_deducted_amount >= 0 AND debt_created_amount >= 0 AND amount = cancelled_frozen_amount + wallet_deducted_amount + debt_created_amount",
    )
    op.create_unique_constraint("uq_wallet_account_id_user", "wallet_accounts", ["id", "user_id"])
    op.create_check_constraint("ck_wallet_account_revision", "wallet_accounts", "revision > 0")
    op.drop_constraint("ck_wallet_ledger_entry_type", "wallet_ledgers", type_="check")
    op.create_check_constraint(
        "ck_wallet_ledger_entry_type",
        "wallet_ledgers",
        "entry_type IN ('commission_settlement', 'commission_recovery', 'withdrawal_freeze', 'withdrawal_release', 'withdrawal_paid')",
    )
    op.add_column("wallet_ledgers", sa.Column("wallet_revision", sa.Integer(), nullable=False))
    op.add_column("wallet_ledgers", sa.Column("balance_after", postgresql.JSONB(), nullable=False))
    op.create_unique_constraint("uq_wallet_ledger_wallet_revision", "wallet_ledgers", ["wallet_id", "wallet_revision"])
    op.add_column("withdrawal_requests", sa.Column("merchant_reference", sa.String(80), nullable=False))
    op.add_column("withdrawal_requests", sa.Column("channel", sa.String(16), nullable=False))
    op.add_column("withdrawal_requests", sa.Column("channel_context", postgresql.JSONB(), nullable=False))
    op.add_column("withdrawal_requests", sa.Column("channel_paid_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("withdrawal_requests", sa.Column("payload_hash", sa.String(64), nullable=True))
    op.create_unique_constraint("uq_withdrawal_merchant_reference", "withdrawal_requests", ["merchant_reference"])
    settings = sa.table(
        "system_settings",
        sa.column("id", sa.Uuid()),
        sa.column("setting_group", sa.String()),
        sa.column("setting_value", postgresql.JSONB()),
        sa.column("revision", sa.Integer()),
        sa.column("updated_by", sa.Uuid()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    now = datetime.now(UTC)
    op.bulk_insert(
        settings,
        [
            {
                "id": uuid.UUID(_COMMISSION_CONTROL_ID),
                "setting_group": "commission_control",
                "setting_value": {"schema_version": 1, "commissions_enabled": False},
                "revision": 1,
                "updated_by": None,
                "created_at": now,
                "updated_at": now,
            }
        ],
    )


def downgrade() -> None:
    raise RuntimeError("分佣政策、钱包账链和持久任务可能已被资金事实引用，禁止自动破坏性降级；请前向修复或恢复备份。")
