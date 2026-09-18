import uuid
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Category(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "product_categories"
    __table_args__ = (
        CheckConstraint("parent_id IS NULL OR parent_id <> id", name="ck_product_category_parent"),
        CheckConstraint("revision > 0", name="ck_product_category_revision"),
        {"comment": "商品三级分类"},
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="分类名称")
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("product_categories.id", ondelete="RESTRICT"), nullable=True, index=True, comment="父分类 ID"
    )
    sort_order: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=None, comment="排序权重，值越小越靠前，NULL 表示未人工设置自动排最后"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, comment="分类启用状态")
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="编辑版本")


class Product(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("product_type IN ('physical', 'virtual')", name="ck_products_type"),
        CheckConstraint("status IN ('draft', 'on_sale', 'off_sale')", name="ck_products_status"),
        CheckConstraint("revision > 0", name="ck_products_revision"),
        Index("ix_products_status_created", "status", "created_at"),
        {"comment": "商品 SPU 资料，不保存库存"},
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False, comment="商品名称")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", comment="商品纯文本说明")
    product_type: Mapped[str] = mapped_column(String(16), nullable=False, comment="实物或虚拟商品")
    category_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("product_categories.id", ondelete="RESTRICT"), nullable=False, index=True, comment="商品分类 ID"
    )
    shipping_template_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("shipping_templates.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
        comment="运费模板，虚拟商品为空",
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft", comment="草稿、上架或下架")
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="商品及变体的编辑版本")


class ProductSku(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "product_skus"
    __table_args__ = (
        CheckConstraint("price >= 0", name="ck_product_skus_price"),
        CheckConstraint("weight_grams >= 0", name="ck_product_skus_weight"),
        CheckConstraint("jsonb_typeof(specifications) = 'object'", name="ck_product_skus_specifications"),
        UniqueConstraint("product_id", "specifications", name="uq_product_sku_specifications"),
        {"comment": "稳定商品变体，不删除重建"},
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True, comment="所属商品 ID"
    )
    code: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, comment="全局唯一 SKU 编码")
    specifications: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False, comment="规格组合，无规格为空对象")
    price: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, comment="基础售价人民币元")
    weight_grams: Mapped[int] = mapped_column(Integer, nullable=False, comment="实物重量克数")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, comment="变体是否启用")


class ProductImage(Base):
    __tablename__ = "product_images"
    __table_args__ = (
        UniqueConstraint("product_id", "position", name="uq_product_image_position"),
        CheckConstraint("position >= 0", name="ck_product_image_position"),
        {"comment": "商品图片资产引用，首张为主图"},
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), primary_key=True, comment="所属商品"
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assets.id", ondelete="RESTRICT"), primary_key=True, comment="引用图片资产"
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, comment="图片排序")
