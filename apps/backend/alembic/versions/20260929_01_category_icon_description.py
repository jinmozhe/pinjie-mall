"""分类表新增图标资产与简述字段

Revision ID: 20260929_01
Revises: 20260926_01

新增字段：
- product_categories.icon_asset_id（可空，关联 assets.id，RESTRICT 删除保护）
- product_categories.description（TEXT，NOT NULL，默认空字符串）
"""

import sqlalchemy as sa

from alembic import op

revision = "20260929_01"
down_revision = "20260926_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 新增图标资产外键字段（可空）
    op.add_column(
        "product_categories",
        sa.Column("icon_asset_id", sa.UUID(), nullable=True, comment="分类图标资产 ID"),
    )
    op.create_foreign_key(
        "fk_product_categories_icon_asset",
        "product_categories",
        "assets",
        ["icon_asset_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_product_categories_icon",
        "product_categories",
        ["icon_asset_id"],
        postgresql_where=sa.text("icon_asset_id IS NOT NULL"),
    )

    # 新增简述字段（NOT NULL，默认空字符串）
    op.add_column(
        "product_categories",
        sa.Column(
            "description",
            sa.Text(),
            nullable=False,
            server_default="",
            comment="分类简述，HTML 字符串",
        ),
    )
    # 落地后去除 server_default，由应用层控制
    op.alter_column("product_categories", "description", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_product_categories_icon", table_name="product_categories")
    op.drop_constraint("fk_product_categories_icon_asset", "product_categories", type_="foreignkey")
    op.drop_column("product_categories", "icon_asset_id")
    op.drop_column("product_categories", "description")
