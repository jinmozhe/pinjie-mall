"""Create membership pricing, platform shipping settings, and external identity mapping.

Revision ID: 20260922_02
Revises: 20260922_01
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260922_02"
down_revision: str | None = "20260922_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_MINIAPP_REGISTRATION_ID = "0198f8a0-0000-7000-8000-000000000003"
_ORDER_SHIPPING_ID = "0198f8a0-0000-7000-8000-000000000004"


def upgrade() -> None:
    op.create_table(
        "member_levels",
        sa.Column("code", sa.String(32), nullable=False, comment="稳定等级编码"),
        sa.Column("name", sa.String(100), nullable=False, comment="等级名称"),
        sa.Column("discount_factor", sa.Numeric(7, 6), nullable=False, comment="默认折扣因子"),
        sa.Column("level_rank", sa.Integer(), nullable=False, comment="等级高低权重"),
        sa.Column("sort_order", sa.Integer(), nullable=True, comment="展示排序权重"),
        sa.Column("revision", sa.Integer(), nullable=False, comment="编辑版本"),
        sa.Column("is_active", sa.Boolean(), nullable=False, comment="是否可应用价格权益"),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_member_level_code"),
        sa.UniqueConstraint("level_rank", name="uq_member_level_rank"),
        sa.CheckConstraint("discount_factor >= 0 AND discount_factor <= 1", name="ck_member_level_discount"),
        sa.CheckConstraint("level_rank > 0", name="ck_member_level_rank"),
        sa.CheckConstraint("revision > 0", name="ck_member_level_revision"),
        sa.CheckConstraint("sort_order IS NULL OR sort_order >= 0", name="ck_member_level_sort"),
        comment="会员等级与默认价格折扣",
    )
    op.create_index("ix_member_level_active_sort", "member_levels", ["is_active", "sort_order", "id"])
    op.create_table(
        "member_price_rules",
        sa.Column("member_level_id", sa.Uuid(), nullable=False),
        sa.Column("scope_type", sa.String(16), nullable=False),
        sa.Column("sku_id", sa.Uuid(), nullable=True),
        sa.Column("product_id", sa.Uuid(), nullable=True),
        sa.Column("category_id", sa.Uuid(), nullable=True),
        sa.Column("price_mode", sa.String(16), nullable=False),
        sa.Column("fixed_price", sa.Numeric(15, 2), nullable=True),
        sa.Column("discount_factor", sa.Numeric(7, 6), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["member_level_id"], ["member_levels.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["sku_id"], ["product_skus.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["category_id"], ["product_categories.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["updated_by"], ["admins.id"], ondelete="SET NULL"),
        sa.CheckConstraint("scope_type IN ('sku', 'product', 'category')", name="ck_member_price_rule_scope"),
        sa.CheckConstraint("price_mode IN ('fixed', 'discount', 'exclude')", name="ck_member_price_rule_mode"),
        sa.CheckConstraint(
            "(scope_type = 'sku' AND sku_id IS NOT NULL AND product_id IS NULL AND category_id IS NULL) OR "
            "(scope_type = 'product' AND sku_id IS NULL AND product_id IS NOT NULL AND category_id IS NULL) OR "
            "(scope_type = 'category' AND sku_id IS NULL AND product_id IS NULL AND category_id IS NOT NULL)",
            name="ck_member_price_rule_scope_target",
        ),
        sa.CheckConstraint(
            "(price_mode = 'fixed' AND fixed_price IS NOT NULL AND fixed_price >= 0 AND discount_factor IS NULL) OR "
            "(price_mode = 'discount' AND fixed_price IS NULL AND discount_factor IS NOT NULL AND discount_factor >= 0 AND discount_factor <= 1) OR "
            "(price_mode = 'exclude' AND fixed_price IS NULL AND discount_factor IS NULL)",
            name="ck_member_price_rule_value",
        ),
        sa.CheckConstraint(
            "scope_type <> 'category' OR price_mode IN ('discount', 'exclude')",
            name="ck_member_price_rule_category_mode",
        ),
        sa.CheckConstraint("revision > 0", name="ck_member_price_rule_revision"),
        comment="会员 SKU、商品和分类统一价格规则",
    )
    op.create_index(
        "uq_member_price_rule_sku",
        "member_price_rules",
        ["member_level_id", "sku_id"],
        unique=True,
        postgresql_where=sa.text("sku_id IS NOT NULL"),
    )
    op.create_index(
        "uq_member_price_rule_product",
        "member_price_rules",
        ["member_level_id", "product_id"],
        unique=True,
        postgresql_where=sa.text("product_id IS NOT NULL"),
    )
    op.create_index(
        "uq_member_price_rule_category",
        "member_price_rules",
        ["member_level_id", "category_id"],
        unique=True,
        postgresql_where=sa.text("category_id IS NOT NULL"),
    )
    op.create_index("ix_member_price_rule_level", "member_price_rules", ["member_level_id", "is_active", "id"])
    op.create_table(
        "user_external_identities",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(16), nullable=False),
        sa.Column("app_id", sa.String(64), nullable=False),
        sa.Column("subject_id", sa.String(128), nullable=False),
        sa.Column("union_id", sa.String(128), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("provider", "app_id", "subject_id", name="uq_user_external_identity_subject"),
        sa.UniqueConstraint("user_id", "provider", "app_id", name="uq_user_external_identity_user_provider"),
        sa.CheckConstraint("provider = 'wechat'", name="ck_user_external_identity_provider"),
        comment="可信外部身份与商城用户的不可变绑定",
    )
    op.create_index("ix_user_external_identity_user", "user_external_identities", ["user_id"])
    op.alter_column(
        "users", "password_hash", existing_type=sa.String(255), nullable=True, existing_comment="Argon2id 密码摘要"
    )
    op.drop_constraint("ck_member_profile_initial_level", "member_profiles", type_="check")
    op.drop_column("member_profiles", "level_code")
    op.add_column(
        "member_profiles", sa.Column("level_id", sa.Uuid(), nullable=True, comment="当前会员等级，空表示无等级")
    )
    op.add_column(
        "member_profiles",
        sa.Column("level_changed_at", sa.DateTime(timezone=True), nullable=True, comment="最近等级变更时间"),
    )
    op.add_column(
        "member_profiles",
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1", comment="档案和等级版本"),
    )
    op.execute("UPDATE member_profiles SET level_changed_at = updated_at WHERE level_changed_at IS NULL")
    op.alter_column("member_profiles", "level_changed_at", nullable=False)
    op.alter_column("member_profiles", "revision", server_default=None)
    op.create_foreign_key(
        "fk_member_profiles_level", "member_profiles", "member_levels", ["level_id"], ["id"], ondelete="RESTRICT"
    )
    op.create_index("ix_member_profiles_level", "member_profiles", ["level_id"])
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
                "id": uuid.UUID(_MINIAPP_REGISTRATION_ID),
                "setting_group": "miniapp_registration",
                "setting_value": {"enabled": False},
                "revision": 1,
                "updated_by": None,
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": uuid.UUID(_ORDER_SHIPPING_ID),
                "setting_group": "order_shipping",
                "setting_value": {
                    "schema_version": 1,
                    "region_level": "province",
                    "default_rule": {"free_shipping_threshold": "0.00", "fixed_fee": "0.00"},
                    "region_rules": [],
                },
                "revision": 1,
                "updated_by": None,
                "created_at": now,
                "updated_at": now,
            },
        ],
    )


def downgrade() -> None:
    raise RuntimeError("会员身份和价格规则可能已被交易快照引用，禁止自动破坏性降级；请前向修复或恢复备份。")
