"""Add product detail image references and trusted image metadata.

Revision ID: 20260926_01
Revises: 20260923_02
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260926_01"
down_revision: str | None = "20260923_02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("assets", sa.Column("width", sa.Integer(), nullable=True, comment="按 EXIF 方向解释的图片宽度，像素"))
    op.add_column(
        "assets", sa.Column("height", sa.Integer(), nullable=True, comment="按 EXIF 方向解释的图片高度，像素")
    )
    op.add_column("assets", sa.Column("frame_count", sa.Integer(), nullable=True, comment="完整解码确认的图片帧数"))
    op.create_check_constraint(
        "ck_assets_image_metadata",
        "assets",
        "(width IS NULL AND height IS NULL AND frame_count IS NULL) OR "
        "(width IS NOT NULL AND height IS NOT NULL AND frame_count IS NOT NULL "
        "AND width > 0 AND height > 0 AND frame_count > 0)",
    )
    op.create_table(
        "product_detail_images",
        sa.Column("product_id", sa.Uuid(), nullable=False, comment="所属商品"),
        sa.Column("asset_id", sa.Uuid(), nullable=False, comment="引用图片资产"),
        sa.Column("position", sa.Integer(), nullable=False, comment="详情集合内连续展示序号"),
        sa.PrimaryKeyConstraint("product_id", "asset_id"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("product_id", "position", name="uq_product_detail_image_position"),
        sa.CheckConstraint("position >= 0", name="ck_product_detail_image_position"),
        comment="商品详情切片图片的独立有序资产引用",
    )
    op.create_index("ix_product_detail_images_asset", "product_detail_images", ["asset_id"])


def downgrade() -> None:
    if (
        op.get_bind().execute(sa.text("SELECT 1 FROM product_detail_images LIMIT 1")).scalar() is not None
        or op.get_bind().execute(sa.text("SELECT 1 FROM assets WHERE width IS NOT NULL LIMIT 1")).scalar() is not None
    ):
        raise RuntimeError("存在详情或图片元数据，禁止有损降级；请备份并采用前向修复。")
    op.drop_table("product_detail_images")
    op.drop_constraint("ck_assets_image_metadata", "assets", type_="check")
    op.drop_column("assets", "frame_count")
    op.drop_column("assets", "height")
    op.drop_column("assets", "width")
