"""商品领域拥有的品牌、公共属性及商品冻结采用关系。"""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Brand(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "brands"
    __table_args__ = (
        CheckConstraint("length(btrim(name)) > 0", name="ck_brands_name"),
        CheckConstraint("revision > 0", name="ck_brands_revision"),
        CheckConstraint("sort_order >= 0", name="ck_brands_sort"),
        Index("ix_brands_active_sort", "is_active", "sort_order", "id"),
        {"comment": "独立品牌资料，停用仅阻止新关联"},
    )
    name: Mapped[str] = mapped_column(String(100), comment="品牌名称")
    logo_asset_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("assets.id", ondelete="RESTRICT"), index=True, comment="品牌图片资产"
    )
    description: Mapped[str] = mapped_column(Text, default="", comment="品牌介绍")
    sort_order: Mapped[int | None] = mapped_column(
        Integer, default=None, comment="排序权重，值越小越靠前，NULL 表示未人工设置自动排最后"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否允许新关联")
    revision: Mapped[int] = mapped_column(Integer, default=1, comment="编辑版本")


class SpecAttribute(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "spec_attributes"
    __table_args__ = (
        CheckConstraint("value_type IN ('text','number','select','multi_select')", name="ck_spec_attribute_type"),
        CheckConstraint("unit IS NULL OR value_type = 'number'", name="ck_spec_attribute_unit"),
        CheckConstraint("jsonb_typeof(validation) = 'object'", name="ck_spec_attribute_validation"),
        CheckConstraint(
            "revision > 0 AND length(btrim(name)) > 0 AND length(btrim(code)) > 0", name="ck_spec_attribute_identity"
        ),
        CheckConstraint("sort_order >= 0", name="ck_spec_attribute_sort"),
        Index("ix_spec_attributes_active_sort", "is_active", "sort_order", "id"),
        {"comment": "公共销售及描述属性定义"},
    )
    code: Mapped[str] = mapped_column(String(64), unique=True, comment="公共属性唯一编码")
    name: Mapped[str] = mapped_column(String(100), comment="属性名称")
    value_type: Mapped[str] = mapped_column(String(16), comment="text/number/select/multi_select")
    unit: Mapped[str | None] = mapped_column(String(32), comment="数值单位")
    validation: Mapped[dict[str, object]] = mapped_column(JSONB, comment="版本化类型验证对象")
    revision: Mapped[int] = mapped_column(Integer, default=1, comment="公共属性版本")
    sort_order: Mapped[int | None] = mapped_column(
        Integer, default=None, comment="排序权重，值越小越靠前，NULL 表示未人工设置自动排最后"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, comment="启用状态")


class SpecAttributeValue(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "spec_attribute_values"
    __table_args__ = (
        UniqueConstraint("attribute_id", "code", name="uq_spec_value_code"),
        UniqueConstraint("id", "attribute_id", name="uq_spec_value_owner"),
        CheckConstraint(
            "revision > 0 AND length(btrim(name)) > 0 AND length(btrim(code)) > 0", name="ck_spec_value_identity"
        ),
        CheckConstraint("sort_order >= 0", name="ck_spec_value_sort"),
        Index("ix_spec_values_attribute_sort", "attribute_id", "sort_order", "id"),
        {"comment": "公共枚举属性候选值"},
    )
    attribute_id: Mapped[UUID] = mapped_column(
        ForeignKey("spec_attributes.id", ondelete="RESTRICT"), comment="所属公共属性"
    )
    code: Mapped[str] = mapped_column(String(64), comment="属性内唯一编码")
    name: Mapped[str] = mapped_column(String(100), comment="候选值名称")
    revision: Mapped[int] = mapped_column(Integer, default=1, comment="候选值版本，同时递增属性版本")
    sort_order: Mapped[int | None] = mapped_column(
        Integer, default=None, comment="排序权重，值越小越靠前，NULL 表示未人工设置自动排最后"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, comment="启用状态")


class CategorySpecAttribute(Base):
    __tablename__ = "category_spec_attributes"
    __table_args__ = (
        CheckConstraint("sort_order >= 0", name="ck_category_spec_sort"),
        {"comment": "分类直接绑定属性模板，不继承父模板"},
    )
    category_id: Mapped[UUID] = mapped_column(
        ForeignKey("product_categories.id", ondelete="RESTRICT"), primary_key=True, comment="分类"
    )
    attribute_id: Mapped[UUID] = mapped_column(
        ForeignKey("spec_attributes.id", ondelete="RESTRICT"), primary_key=True, index=True, comment="公共属性"
    )
    is_variant: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否销售规格")
    is_required: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否必填")
    sort_order: Mapped[int | None] = mapped_column(
        Integer, default=None, comment="排序权重，值越小越靠前，NULL 表示未人工设置自动排最后"
    )
    allow_custom_value: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否允许局部销售候选值")


class ProductSpecAttribute(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "product_spec_attributes"
    __table_args__ = (
        UniqueConstraint("id", "product_id", name="uq_product_adoption_owner"),
        Index(
            "uq_product_adoption_version",
            "product_id",
            "attribute_id",
            "adoption_version",
            unique=True,
            postgresql_where=text("attribute_id IS NOT NULL"),
        ),
        Index(
            "uq_product_adoption_current_attribute",
            "product_id",
            "attribute_id",
            unique=True,
            postgresql_where=text("is_current AND attribute_id IS NOT NULL"),
        ),
        Index(
            "uq_product_adoption_current_name",
            "product_id",
            "name_snapshot",
            unique=True,
            postgresql_where=text("is_current"),
        ),
        CheckConstraint(
            "adoption_version > 0 AND length(btrim(name_snapshot)) > 0", name="ck_product_adoption_version"
        ),
        CheckConstraint(
            "value_type_snapshot IN ('text','number','select','multi_select')", name="ck_product_adoption_type"
        ),
        CheckConstraint("NOT is_variant OR value_type_snapshot = 'select'", name="ck_product_adoption_variant"),
        CheckConstraint("unit_snapshot IS NULL OR value_type_snapshot = 'number'", name="ck_product_adoption_unit"),
        CheckConstraint("jsonb_typeof(validation_snapshot) = 'object'", name="ck_product_adoption_validation"),
        CheckConstraint(
            "(source_category_id IS NULL AND source_category_revision IS NULL) OR (source_category_id IS NOT NULL AND source_category_revision IS NOT NULL AND source_category_revision > 0)",
            name="ck_product_adoption_category_source",
        ),
        CheckConstraint(
            "(attribute_id IS NULL AND source_attribute_revision IS NULL AND source_category_id IS NULL) OR (attribute_id IS NOT NULL AND source_attribute_revision IS NOT NULL AND source_attribute_revision > 0)",
            name="ck_product_adoption_source",
        ),
        {"comment": "商品属性冻结采用版本，仅当前标记可退出"},
    )
    product_id: Mapped[UUID] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), index=True, comment="所属商品"
    )
    attribute_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("spec_attributes.id", ondelete="RESTRICT"), index=True, comment="公共属性，自建时为空"
    )
    adoption_version: Mapped[int] = mapped_column(Integer, comment="商品采用版本")
    name_snapshot: Mapped[str] = mapped_column(String(100), comment="采用名称快照")
    value_type_snapshot: Mapped[str] = mapped_column(String(16), comment="采用类型快照")
    unit_snapshot: Mapped[str | None] = mapped_column(String(32), comment="采用单位快照")
    validation_snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, comment="采用验证规则")
    source_category_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("product_categories.id", ondelete="RESTRICT"), comment="模板来源分类"
    )
    source_category_revision: Mapped[int | None] = mapped_column(Integer, comment="模板来源版本")
    source_attribute_revision: Mapped[int | None] = mapped_column(Integer, comment="公共属性来源版本")
    is_required: Mapped[bool] = mapped_column(Boolean, comment="冻结必填规则")
    allow_custom_value: Mapped[bool] = mapped_column(Boolean, comment="冻结局部候选授权")
    is_variant: Mapped[bool] = mapped_column(Boolean, comment="销售规格标记")
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否当前采用")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), comment="采用时间"
    )


class ProductSpecValue(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "product_spec_values"
    __table_args__ = (
        UniqueConstraint("id", "adoption_id", "product_id", name="uq_product_spec_value_owner"),
        ForeignKeyConstraint(
            ["adoption_id", "product_id"],
            ["product_spec_attributes.id", "product_spec_attributes.product_id"],
            ondelete="RESTRICT",
            name="fk_product_spec_value_adoption",
        ),
        ForeignKeyConstraint(
            ["value_id", "attribute_id"],
            ["spec_attribute_values.id", "spec_attribute_values.attribute_id"],
            ondelete="RESTRICT",
            name="fk_product_spec_value_standard",
        ),
        CheckConstraint("value_id IS NULL OR attribute_id IS NOT NULL", name="ck_product_spec_value_standard"),
        CheckConstraint(
            "length(btrim(display_value)) > 0 AND length(btrim(normalized_value)) > 0",
            name="ck_product_spec_value_text",
        ),
        Index(
            "uq_product_spec_value_standard_current",
            "adoption_id",
            "value_id",
            unique=True,
            postgresql_where=text("is_current AND value_id IS NOT NULL"),
        ),
        Index(
            "uq_product_spec_value_custom_current",
            "adoption_id",
            "normalized_value",
            unique=True,
            postgresql_where=text("is_current AND value_id IS NULL"),
        ),
        {"comment": "商品采用下的公共或局部候选值，历史保留"},
    )
    adoption_id: Mapped[UUID] = mapped_column(index=True, comment="商品采用记录")
    product_id: Mapped[UUID] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"), comment="所属商品")
    attribute_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("spec_attributes.id", ondelete="RESTRICT"), comment="冗余公共属性身份"
    )
    value_id: Mapped[UUID | None] = mapped_column(comment="公共标准值，局部候选为空")
    display_value: Mapped[str] = mapped_column(String(100), comment="候选值文本快照")
    normalized_value: Mapped[str] = mapped_column(String(100), comment="NFC 去首尾空白的去重文本")
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否当前候选")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), comment="创建时间"
    )


class ProductSkuSpecValue(Base):
    __tablename__ = "product_sku_spec_values"
    __table_args__ = (
        ForeignKeyConstraint(
            ["sku_id", "product_id"],
            ["product_skus.id", "product_skus.product_id"],
            ondelete="RESTRICT",
            name="fk_sku_spec_sku_owner",
        ),
        ForeignKeyConstraint(
            ["spec_value_id", "adoption_id", "product_id"],
            ["product_spec_values.id", "product_spec_values.adoption_id", "product_spec_values.product_id"],
            ondelete="RESTRICT",
            name="fk_sku_spec_value_owner",
        ),
        {"comment": "SKU 每个采用维度恰一值的稳定组合身份"},
    )
    product_id: Mapped[UUID] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"), comment="所属商品")
    sku_id: Mapped[UUID] = mapped_column(primary_key=True, comment="稳定 SKU")
    adoption_id: Mapped[UUID] = mapped_column(
        ForeignKey("product_spec_attributes.id", ondelete="RESTRICT"), primary_key=True, index=True, comment="采用维度"
    )
    attribute_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("spec_attributes.id", ondelete="RESTRICT"), comment="公共属性或空"
    )
    spec_value_id: Mapped[UUID] = mapped_column(index=True, comment="商品候选值")


class ProductAttributeValue(Base, TimestampMixin):
    __tablename__ = "product_attribute_values"
    __table_args__ = (
        ForeignKeyConstraint(
            ["adoption_id", "product_id"],
            ["product_spec_attributes.id", "product_spec_attributes.product_id"],
            ondelete="RESTRICT",
            name="fk_description_adoption_owner",
        ),
        CheckConstraint(
            "schema_version = 1 AND jsonb_typeof(display_snapshot) = 'object'", name="ck_description_schema"
        ),
        Index("ix_description_product_attribute", "product_id", "attribute_id"),
        {"comment": "非销售属性描述值，按采用版本保留"},
    )
    adoption_id: Mapped[UUID] = mapped_column(primary_key=True, comment="采用版本")
    product_id: Mapped[UUID] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"), comment="所属商品")
    attribute_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("spec_attributes.id", ondelete="RESTRICT"), comment="公共属性或空"
    )
    value: Mapped[object] = mapped_column(JSONB, nullable=False, comment="类型化描述值，数值为十进制字符串")
    schema_version: Mapped[int] = mapped_column(Integer, default=1, comment="描述编码版本")
    display_snapshot: Mapped[dict[str, str]] = mapped_column(JSONB, comment="枚举显示文本快照")
