"""Persist WeChat prepay state and verified callback inbox. No credential data."""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261118_01"
down_revision: str | None = "20261013_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "payment_attempts",
        sa.Column("prepay_id", sa.String(128), nullable=True, comment="微信预支付会话，仅本人调起使用"),
    )
    op.add_column(
        "payment_attempts",
        sa.Column("channel_expires_at", sa.DateTime(timezone=True), nullable=True, comment="渠道支付截止"),
    )
    op.add_column(
        "payment_attempts",
        sa.Column("submission_started_at", sa.DateTime(timezone=True), nullable=True, comment="最近提交领取时间"),
    )
    op.add_column(
        "payment_attempts",
        sa.Column(
            "close_requested",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="已要求关闭渠道订单",
        ),
    )
    op.create_index(
        "uq_payment_wechat_active_order",
        "payment_attempts",
        ["order_id"],
        unique=True,
        postgresql_where=sa.text("channel = 'wechat' AND status IN ('created', 'pending', 'unknown')"),
    )
    op.create_table(
        "wechat_pay_notifications",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("merchant_id", sa.String(32), nullable=False),
        sa.Column("notification_id", sa.String(128), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("config_version", sa.String(64), nullable=False),
        sa.Column("verified_payload", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.UniqueConstraint("merchant_id", "notification_id", name="uq_wechat_pay_notification"),
        sa.CheckConstraint("status IN ('pending', 'processed')", name="ck_wechat_pay_notification_status"),
        comment="微信支付已验签通知的最小持久接收记录",
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM wechat_pay_notifications) OR EXISTS "
            "(SELECT 1 FROM payment_attempts WHERE channel_expires_at IS NOT NULL)"
        )
    ):
        raise RuntimeError("Payment evidence must be retained; use a forward fix")
    op.drop_table("wechat_pay_notifications")
    op.drop_index("uq_payment_wechat_active_order", table_name="payment_attempts")
    for name in ("close_requested", "submission_started_at", "channel_expires_at", "prepay_id"):
        op.drop_column("payment_attempts", name)
