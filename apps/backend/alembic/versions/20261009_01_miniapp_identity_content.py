"""Add independent Miniapp Bearer sessions and explicit description migration marker."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261009_01"
down_revision: str | None = "20260929_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_user_sessions_profile", "user_sessions", type_="check")
    op.alter_column("user_sessions", "csrf_digest", nullable=True, comment="Cookie CSRF HMAC；Bearer 为空")
    op.create_check_constraint(
        "ck_user_sessions_profile",
        "user_sessions",
        "(credential_profile = 'browser_cookie' AND client_id = 'pinjie-web' AND csrf_digest IS NOT NULL) OR "
        "(credential_profile = 'miniapp_bearer' AND client_id = 'pinjie-miniapp' AND csrf_digest IS NULL)",
    )
    op.add_column(
        "products",
        sa.Column(
            "description_version",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="0 未审计 legacy；1 受限 HTML v1",
        ),
    )
    op.alter_column("products", "description_version", server_default=None)
    op.alter_column("products", "description", comment="商品受限 HTML，旧数据须显式迁移")
    op.create_check_constraint("ck_products_description_version", "products", "description_version IN (0, 1)")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.scalar(sa.text("SELECT EXISTS (SELECT 1 FROM user_sessions WHERE credential_profile = 'miniapp_bearer')")):
        raise RuntimeError("Bearer sessions must be explicitly retired before downgrade; no automatic deletion")
    if bind.scalar(sa.text("SELECT EXISTS (SELECT 1 FROM products WHERE description_version = 1)")):
        raise RuntimeError("Description v1 data requires an explicit rollback plan before downgrade")
    op.drop_constraint("ck_products_description_version", "products", type_="check")
    op.drop_column("products", "description_version")
    op.alter_column("products", "description", comment="商品纯文本说明")
    op.drop_constraint("ck_user_sessions_profile", "user_sessions", type_="check")
    op.alter_column("user_sessions", "csrf_digest", nullable=False, comment="CSRF Token HMAC")
    op.create_check_constraint("ck_user_sessions_profile", "user_sessions", "credential_profile = 'browser_cookie'")
