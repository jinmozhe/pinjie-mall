"""将 product_categories.sort_order 改为可空列并更新列注释。

Revision ID: 20260918_02
Revises: 20260918_01
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260918_02"
down_revision: str | None = "20260918_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 移除 NOT NULL 约束并去除默认值：已有的 0 值保持不变，仅新增记录默认为 NULL
    op.execute("ALTER TABLE product_categories ALTER COLUMN sort_order DROP NOT NULL")
    op.execute("ALTER TABLE product_categories ALTER COLUMN sort_order DROP DEFAULT")
    op.execute(
        "COMMENT ON COLUMN product_categories.sort_order IS '排序权重，值越小越靠前，NULL 表示未人工设置自动排最后'"
    )


def downgrade() -> None:
    # 回滚：将现有 NULL 值填充为 0，再恢复 NOT NULL + DEFAULT 0
    op.execute("UPDATE product_categories SET sort_order = 0 WHERE sort_order IS NULL")
    op.execute("ALTER TABLE product_categories ALTER COLUMN sort_order SET DEFAULT 0")
    op.execute("ALTER TABLE product_categories ALTER COLUMN sort_order SET NOT NULL")
    op.execute("COMMENT ON COLUMN product_categories.sort_order IS '排序值'")
