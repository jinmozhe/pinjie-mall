"""Independent verified phone and scoped external identities; no account reassignment."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261013_01"
down_revision: str | None = "20261009_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("phone_e164", sa.String(16), nullable=True, comment="独立已验证手机号，E.164"))
    op.add_column(
        "users", sa.Column("phone_verified_at", sa.DateTime(timezone=True), nullable=True, comment="手机号平台验证时间")
    )
    op.add_column(
        "users", sa.Column("phone_verification_source", sa.String(32), nullable=True, comment="手机号可信验证来源")
    )
    op.create_unique_constraint("uq_users_phone_e164", "users", ["phone_e164"])
    op.create_check_constraint(
        "ck_users_verified_phone",
        "users",
        "(phone_e164 IS NULL AND phone_verified_at IS NULL AND phone_verification_source IS NULL) OR "
        "(phone_e164 IS NOT NULL AND phone_verified_at IS NOT NULL AND "
        "phone_verification_source IS NOT NULL AND phone_verification_source = 'wechat_phone_quick' "
        "AND phone_e164 ~ '^\\+[1-9][0-9]{1,14}$')",
    )
    op.add_column(
        "user_external_identities",
        sa.Column("union_scope_id", sa.String(64), nullable=True, comment="服务端登记的微信开放平台账号命名空间"),
    )
    op.create_index(
        "ix_user_external_identity_union", "user_external_identities", ["provider", "union_scope_id", "union_id"]
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.scalar(sa.text("SELECT EXISTS (SELECT 1 FROM users WHERE phone_e164 IS NOT NULL)")):
        raise RuntimeError("Verified phones require an explicit preservation plan; use a forward fix")
    if bind.scalar(sa.text("SELECT EXISTS (SELECT 1 FROM user_external_identities WHERE union_scope_id IS NOT NULL)")):
        raise RuntimeError("External identity scopes require an explicit preservation plan")
    op.drop_index("ix_user_external_identity_union", table_name="user_external_identities")
    op.drop_column("user_external_identities", "union_scope_id")
    op.drop_constraint("ck_users_verified_phone", "users", type_="check")
    op.drop_constraint("uq_users_phone_e164", "users", type_="unique")
    op.drop_column("users", "phone_verification_source")
    op.drop_column("users", "phone_verified_at")
    op.drop_column("users", "phone_e164")
