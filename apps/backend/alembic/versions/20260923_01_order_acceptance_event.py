"""allow audited administrator order acceptance events

Revision ID: 20260923_01
Revises: 20260922_07
Create Date: 2026-09-23 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260923_01"
down_revision: str | None = "20260922_07"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_order_event_actor", "order_events", type_="check")
    op.create_check_constraint(
        "ck_order_event_actor",
        "order_events",
        "actor_type IN ('user', 'system', 'payment', 'admin')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_order_event_actor", "order_events", type_="check")
    op.create_check_constraint("ck_order_event_actor", "order_events", "actor_type IN ('user', 'system', 'payment')")
