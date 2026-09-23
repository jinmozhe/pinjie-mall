"""enforce financial ownership facts and audited reconciliation resolution

Revision ID: 20260923_02
Revises: 20260923_01
Create Date: 2026-09-23 00:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260923_02"
down_revision: str | None = "20260923_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _require_no_rows(sql: str, message: str) -> None:
    if op.get_bind().execute(sa.text(sql)).scalar() is not None:
        raise RuntimeError(message)


def upgrade() -> None:
    _require_no_rows(
        """
        SELECT 1
        FROM orders AS orders
        LEFT JOIN payment_attempts AS payment_attempts
          ON payment_attempts.id = orders.accepted_payment_attempt_id
        WHERE orders.accepted_payment_attempt_id IS NOT NULL
          AND (payment_attempts.id IS NULL OR payment_attempts.order_id <> orders.id)
        LIMIT 1
        """,
        "无法添加订单支付归属约束：存在跨订单或缺失的已接受支付，请先人工核对并前向修复。",
    )
    _require_no_rows(
        """
        SELECT 1
        FROM order_items AS order_items
        LEFT JOIN product_skus AS product_skus
          ON product_skus.id = order_items.sku_id
        WHERE product_skus.id IS NULL OR product_skus.product_id <> order_items.product_id
        LIMIT 1
        """,
        "无法添加订单 SKU 归属约束：存在缺失 SKU 或跨商品订单明细，请先人工核对并前向修复。",
    )
    _require_no_rows(
        """
        SELECT 1
        FROM withdrawal_requests AS withdrawals
        LEFT JOIN wallet_accounts AS wallets ON wallets.id = withdrawals.wallet_id
        WHERE wallets.id IS NULL
           OR wallets.user_id <> withdrawals.user_id
           OR wallets.wallet_type <> 'commission'
        LIMIT 1
        """,
        "无法添加提现钱包归属约束：存在缺失、跨用户或非佣金钱包的提现记录，请先人工核对并前向修复。",
    )
    _require_no_rows(
        "SELECT 1 FROM audit_events WHERE actor_id IS NULL LIMIT 1",
        "无法补充审计主体类型：存在历史审计事件缺少主体，不能推测回填。",
    )
    _require_no_rows(
        """
        SELECT 1
        FROM reconciliation_records
        WHERE (resolution_status = 'open' AND (resolution_note IS NOT NULL OR resolved_by_id IS NOT NULL OR resolved_at IS NOT NULL))
           OR (resolution_status = 'resolved' AND (resolution_note IS NULL OR resolved_by_id IS NULL OR resolved_at IS NULL))
        LIMIT 1
        """,
        "无法添加对账处置事实约束：存在无法解释的历史处置字段，请先人工核对并前向修复。",
    )
    op.add_column(
        "audit_events",
        sa.Column("actor_type", sa.String(length=16), nullable=False, server_default="admin", comment="审计主体类型"),
    )
    op.add_column("audit_events", sa.Column("target_revision", sa.Integer(), nullable=True, comment="目标业务版本"))
    op.create_check_constraint(
        "ck_audit_events_actor",
        "audit_events",
        "actor_type IN ('admin', 'user', 'system', 'channel') AND "
        "((actor_type IN ('admin', 'user') AND actor_id IS NOT NULL) OR "
        "(actor_type IN ('system', 'channel') AND actor_id IS NULL))",
    )
    op.create_check_constraint(
        "ck_audit_events_target_revision",
        "audit_events",
        "target_revision IS NULL OR target_revision > 0",
    )
    _require_no_rows(
        """
        SELECT 1
        FROM audit_events
        WHERE action = 'withdrawal.state_changed'
          AND (target_type <> 'withdrawal_request' OR target_id IS NULL OR target_revision IS NULL)
        LIMIT 1
        """,
        "无法添加提现审计目标约束：存在缺少提现目标或版本的历史状态审计，请先人工核对并前向修复。",
    )
    op.create_check_constraint(
        "ck_audit_events_withdrawal_target",
        "audit_events",
        "action <> 'withdrawal.state_changed' OR "
        "(target_type = 'withdrawal_request' AND target_id IS NOT NULL AND target_revision IS NOT NULL)",
    )
    _require_no_rows(
        """
        SELECT 1
        FROM audit_events
        WHERE action = 'withdrawal.state_changed' AND result = 'succeeded'
        GROUP BY target_type, target_id, target_revision
        HAVING count(*) > 1
        LIMIT 1
        """,
        "无法添加提现审计唯一版本约束：存在重复成功的历史提现状态审计，请先人工核对并前向修复。",
    )
    op.create_index(
        "uq_audit_events_withdrawal_revision",
        "audit_events",
        ["target_type", "target_id", "target_revision"],
        unique=True,
        postgresql_where=sa.text("action = 'withdrawal.state_changed' AND result = 'succeeded'"),
    )
    op.alter_column("audit_events", "actor_type", server_default=None)

    op.create_unique_constraint("uq_payment_attempt_id_order", "payment_attempts", ["id", "order_id"])
    op.drop_constraint("fk_orders_payment_attempt", "orders", type_="foreignkey")
    op.create_foreign_key(
        "fk_orders_accepted_payment_same_order",
        "orders",
        "payment_attempts",
        ["accepted_payment_attempt_id", "id"],
        ["id", "order_id"],
        ondelete="RESTRICT",
    )

    op.create_unique_constraint("uq_order_item_id_order", "order_items", ["id", "order_id"])
    op.create_unique_constraint("uq_order_item_id_product", "order_items", ["id", "product_id"])
    op.create_foreign_key(
        "fk_order_items_sku_product",
        "order_items",
        "product_skus",
        ["sku_id", "product_id"],
        ["id", "product_id"],
        ondelete="RESTRICT",
    )

    op.drop_constraint("uq_withdrawal_channel_reference", "withdrawal_requests", type_="unique")
    op.create_unique_constraint(
        "uq_withdrawal_channel_reference",
        "withdrawal_requests",
        ["channel", "channel_reference"],
    )
    op.drop_constraint("withdrawal_requests_wallet_id_fkey", "withdrawal_requests", type_="foreignkey")
    op.create_foreign_key(
        "fk_withdrawal_wallet_owner",
        "withdrawal_requests",
        "wallet_accounts",
        ["wallet_id", "user_id"],
        ["id", "user_id"],
        ondelete="RESTRICT",
    )

    op.create_check_constraint(
        "ck_reconciliation_resolution_fact",
        "reconciliation_records",
        "(resolution_status = 'open' AND resolution_note IS NULL AND resolved_by_id IS NULL AND resolved_at IS NULL) OR "
        "(resolution_status = 'resolved' AND resolution_note IS NOT NULL AND resolved_by_id IS NOT NULL AND resolved_at IS NOT NULL)",
    )
    op.create_index(
        "ix_reconciliation_resolution",
        "reconciliation_records",
        ["resolution_status", "id"],
    )


def downgrade() -> None:
    raise RuntimeError("财务归属约束和审计版本已保护不可变资金事实，禁止自动破坏性降级；请前向修复或恢复备份。")
