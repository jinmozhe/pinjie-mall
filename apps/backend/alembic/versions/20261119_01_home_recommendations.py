"""商品首页人工推荐配置。

Revision ID: 20261119_01
Revises: 20261118_01
"""

import sqlalchemy as sa

from alembic import op

revision = "20261119_01"
down_revision = "20261118_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column(
            "is_home_recommended",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
            comment="是否由管理员指定为首页推荐",
        ),
    )
    op.alter_column("products", "is_home_recommended", server_default=None)
    op.add_column(
        "products",
        sa.Column(
            "home_recommend_sort",
            sa.Integer(),
            nullable=True,
            comment="首页推荐排序权重，值越小越靠前，NULL 表示未人工设置自动排最后",
        ),
    )
    op.create_check_constraint("ck_products_home_recommend_sort", "products", "home_recommend_sort >= 0")
    op.create_index(
        "ix_products_home_recommend",
        "products",
        [sa.text("home_recommend_sort ASC NULLS LAST"), sa.text("id DESC")],
        postgresql_where=sa.text("is_home_recommended IS TRUE"),
    )


def downgrade() -> None:
    # 降级会丢失人工推荐配置，执行前须单独备份该配置。
    op.drop_index("ix_products_home_recommend", table_name="products")
    op.drop_constraint("ck_products_home_recommend_sort", "products", type_="check")
    op.drop_column("products", "home_recommend_sort")
    op.drop_column("products", "is_home_recommended")
