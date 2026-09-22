from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class MemberProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "member_profiles"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_member_profile_user"),
        UniqueConstraint("invitation_code", name="uq_member_profile_invitation_code"),
        CheckConstraint("revision > 0", name="ck_member_profile_revision"),
        Index("ix_member_profile_inviter", "inviter_id", "id"),
        {"comment": "会员档案与不可变首次推荐关系"},
    )

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), comment="会员用户")
    invitation_code: Mapped[str] = mapped_column(String(16), comment="本人唯一推荐码")
    level_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("member_levels.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
        comment="当前会员等级，空表示无等级",
    )
    level_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="最近等级变更时间"
    )
    inviter_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, comment="首次绑定的推荐人"
    )
    bound_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="推荐关系绑定时间"
    )
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False, comment="档案和等级版本")


class MemberLevel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "member_levels"
    __table_args__ = (
        UniqueConstraint("code", name="uq_member_level_code"),
        UniqueConstraint("level_rank", name="uq_member_level_rank"),
        CheckConstraint("discount_factor >= 0 AND discount_factor <= 1", name="ck_member_level_discount"),
        CheckConstraint("level_rank > 0", name="ck_member_level_rank"),
        CheckConstraint("revision > 0", name="ck_member_level_revision"),
        CheckConstraint("sort_order IS NULL OR sort_order >= 0", name="ck_member_level_sort"),
        Index("ix_member_level_active_sort", "is_active", "sort_order", "id"),
        {"comment": "会员等级与默认价格折扣"},
    )

    code: Mapped[str] = mapped_column(String(32), nullable=False, comment="稳定等级编码")
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="等级名称")
    discount_factor: Mapped[Decimal] = mapped_column(
        Numeric(7, 6), nullable=False, default=Decimal("1.000000"), comment="默认折扣因子"
    )
    level_rank: Mapped[int] = mapped_column(Integer, nullable=False, comment="等级高低权重")
    sort_order: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None, comment="展示排序权重")
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="编辑版本")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, comment="是否可应用价格权益")


class MemberLevelCondition(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "member_level_conditions"
    __table_args__ = (
        UniqueConstraint("level_id", "metric", "aggregation", name="uq_member_level_condition"),
        CheckConstraint("metric IN ('consumption', 'invite_count', 'points')", name="ck_member_level_condition_metric"),
        CheckConstraint("aggregation IN ('single', 'cumulative')", name="ck_member_level_condition_aggregation"),
        CheckConstraint(
            "(metric = 'consumption' AND amount_threshold IS NOT NULL AND amount_threshold >= 0 "
            "AND count_threshold IS NULL) OR "
            "(metric IN ('invite_count', 'points') AND count_threshold IS NOT NULL AND count_threshold >= 0 "
            "AND amount_threshold IS NULL)",
            name="ck_member_level_condition_threshold",
        ),
        CheckConstraint("revision > 0", name="ck_member_level_condition_revision"),
        Index("ix_member_level_condition_level", "level_id", "is_active", "id"),
        {"comment": "会员自动资格评估条件"},
    )

    level_id: Mapped[UUID] = mapped_column(ForeignKey("member_levels.id", ondelete="RESTRICT"), nullable=False)
    metric: Mapped[str] = mapped_column(String(24), nullable=False)
    aggregation: Mapped[str] = mapped_column(String(16), nullable=False)
    amount_threshold: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    count_threshold: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_by_id: Mapped[UUID | None] = mapped_column(
        "updated_by", ForeignKey("admins.id", ondelete="SET NULL"), nullable=True
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class MembershipQualificationEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "membership_qualification_events"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_membership_qualification_event_idempotency"),
        UniqueConstraint("user_id", "source_type", "source_id", "metric", name="uq_membership_qualification_source"),
        CheckConstraint(
            "metric IN ('consumption', 'invite_count', 'points')", name="ck_membership_qualification_metric"
        ),
        CheckConstraint(
            "source_type IN ('order_confirm', 'refund', 'invite_validated', 'points_grant', 'points_reverse', 'manual')",
            name="ck_membership_qualification_source_type",
        ),
        CheckConstraint(
            "(amount_delta IS NOT NULL AND amount_delta <> 0 AND count_delta IS NULL) OR "
            "(amount_delta IS NULL AND count_delta IS NOT NULL AND count_delta <> 0)",
            name="ck_membership_qualification_delta",
        ),
        Index("ix_membership_qualification_user_metric", "user_id", "metric", "id"),
        {"comment": "可冲销的会员资格贡献事实"},
    )

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    metric: Mapped[str] = mapped_column(String(24), nullable=False)
    source_type: Mapped[str] = mapped_column(String(24), nullable=False)
    source_id: Mapped[UUID] = mapped_column(nullable=False)
    order_id: Mapped[UUID | None] = mapped_column(ForeignKey("orders.id", ondelete="RESTRICT"), nullable=True)
    amount_delta: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    count_delta: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    reverses_event_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("membership_qualification_events.id", ondelete="RESTRICT"), nullable=True
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)


class MemberLevelEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "member_level_events"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_member_level_event_idempotency"),
        UniqueConstraint("user_id", "profile_revision", name="uq_member_level_event_profile_revision"),
        CheckConstraint(
            "trigger_type IN ('manual', 'order', 'refund', 'invite', 'policy_reassessment', 'points')",
            name="ck_member_level_event_trigger",
        ),
        CheckConstraint("profile_revision > 0", name="ck_member_level_event_profile_revision"),
        CheckConstraint("from_level_id IS DISTINCT FROM to_level_id", name="ck_member_level_event_change"),
        Index("ix_member_level_event_user", "user_id", "id"),
        {"comment": "会员等级变更的不可变历史"},
    )

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    from_level_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("member_levels.id", ondelete="RESTRICT"), nullable=True
    )
    to_level_id: Mapped[UUID | None] = mapped_column(ForeignKey("member_levels.id", ondelete="RESTRICT"), nullable=True)
    trigger_type: Mapped[str] = mapped_column(String(24), nullable=False)
    trigger_id: Mapped[UUID | None] = mapped_column(nullable=True)
    qualification_snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    profile_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    operator_id: Mapped[UUID | None] = mapped_column(ForeignKey("admins.id", ondelete="SET NULL"), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)


class PointsAccount(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "points_accounts"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_points_account_user"),
        CheckConstraint("available_points >= 0", name="ck_points_account_available"),
        CheckConstraint("frozen_points >= 0", name="ck_points_account_frozen"),
        CheckConstraint("debt_points >= 0", name="ck_points_account_debt"),
        CheckConstraint("revision > 0", name="ck_points_account_revision"),
        {"comment": "用户积分余额，不属于人民币钱包"},
    )

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    available_points: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    frozen_points: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    debt_points: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class PointsLedger(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "points_ledgers"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_points_ledger_idempotency"),
        CheckConstraint(
            "entry_type IN ('grant', 'spend', 'freeze', 'release', 'reverse', 'expire')", name="ck_points_ledger_type"
        ),
        CheckConstraint(
            "source_type IN ('invite', 'order', 'refund', 'redemption', 'manual')", name="ck_points_ledger_source"
        ),
        CheckConstraint("available_delta <> 0 OR frozen_delta <> 0 OR debt_delta <> 0", name="ck_points_ledger_delta"),
        Index("ix_points_ledger_account", "account_id", "id"),
        {"comment": "不可变积分收支与冲销流水"},
    )

    account_id: Mapped[UUID] = mapped_column(ForeignKey("points_accounts.id", ondelete="RESTRICT"), nullable=False)
    entry_type: Mapped[str] = mapped_column(String(24), nullable=False)
    available_delta: Mapped[int] = mapped_column(BigInteger, nullable=False)
    frozen_delta: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    debt_delta: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    source_type: Mapped[str] = mapped_column(String(24), nullable=False)
    source_id: Mapped[UUID] = mapped_column(nullable=False)
    reverses_ledger_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("points_ledgers.id", ondelete="RESTRICT"), nullable=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)


class MemberPriceRule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "member_price_rules"
    __table_args__ = (
        CheckConstraint("scope_type IN ('sku', 'product', 'category')", name="ck_member_price_rule_scope"),
        CheckConstraint("price_mode IN ('fixed', 'discount', 'exclude')", name="ck_member_price_rule_mode"),
        CheckConstraint(
            "(scope_type = 'sku' AND sku_id IS NOT NULL AND product_id IS NULL AND category_id IS NULL) OR "
            "(scope_type = 'product' AND sku_id IS NULL AND product_id IS NOT NULL AND category_id IS NULL) OR "
            "(scope_type = 'category' AND sku_id IS NULL AND product_id IS NULL AND category_id IS NOT NULL)",
            name="ck_member_price_rule_scope_target",
        ),
        CheckConstraint(
            "(price_mode = 'fixed' AND fixed_price IS NOT NULL AND fixed_price >= 0 AND discount_factor IS NULL) OR "
            "(price_mode = 'discount' AND fixed_price IS NULL AND discount_factor IS NOT NULL AND discount_factor >= 0 AND discount_factor <= 1) OR "
            "(price_mode = 'exclude' AND fixed_price IS NULL AND discount_factor IS NULL)",
            name="ck_member_price_rule_value",
        ),
        CheckConstraint(
            "scope_type <> 'category' OR price_mode IN ('discount', 'exclude')",
            name="ck_member_price_rule_category_mode",
        ),
        CheckConstraint("revision > 0", name="ck_member_price_rule_revision"),
        Index(
            "uq_member_price_rule_sku",
            "member_level_id",
            "sku_id",
            unique=True,
            postgresql_where=text("sku_id IS NOT NULL"),
        ),
        Index(
            "uq_member_price_rule_product",
            "member_level_id",
            "product_id",
            unique=True,
            postgresql_where=text("product_id IS NOT NULL"),
        ),
        Index(
            "uq_member_price_rule_category",
            "member_level_id",
            "category_id",
            unique=True,
            postgresql_where=text("category_id IS NOT NULL"),
        ),
        Index("ix_member_price_rule_level", "member_level_id", "is_active", "id"),
        {"comment": "会员 SKU、商品和分类统一价格规则"},
    )

    member_level_id: Mapped[UUID] = mapped_column(ForeignKey("member_levels.id", ondelete="RESTRICT"), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False)
    sku_id: Mapped[UUID | None] = mapped_column(ForeignKey("product_skus.id", ondelete="RESTRICT"), nullable=True)
    product_id: Mapped[UUID | None] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"), nullable=True)
    category_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("product_categories.id", ondelete="RESTRICT"), nullable=True
    )
    price_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    fixed_price: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    discount_factor: Mapped[Decimal | None] = mapped_column(Numeric(7, 6), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_by_id: Mapped[UUID | None] = mapped_column(
        "updated_by", ForeignKey("admins.id", ondelete="SET NULL"), nullable=True, comment="最后编辑管理员"
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class CommissionPolicy(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "commission_policies"
    __table_args__ = (
        UniqueConstraint("content_version", name="uq_commission_policy_content_version"),
        CheckConstraint("status IN ('draft', 'active', 'retired')", name="ck_commission_policy_status"),
        CheckConstraint("max_depth BETWEEN 1 AND 3", name="ck_commission_policy_max_depth"),
        CheckConstraint("settle_delay_days >= 0", name="ck_commission_policy_settle_delay"),
        CheckConstraint("content_version > 0", name="ck_commission_policy_content_version"),
        CheckConstraint("revision > 0", name="ck_commission_policy_revision"),
        CheckConstraint(
            "(default_mode IS NULL AND default_amount_per_unit IS NULL AND default_percentage_rate IS NULL) OR "
            "(default_mode = 'fixed_amount' AND default_amount_per_unit IS NOT NULL "
            "AND default_amount_per_unit >= 0 AND default_percentage_rate IS NULL) OR "
            "(default_mode = 'percentage' AND default_percentage_rate IS NOT NULL "
            "AND default_percentage_rate >= 0 AND default_percentage_rate <= 1 AND default_amount_per_unit IS NULL) OR "
            "(default_mode = 'disabled' AND default_amount_per_unit IS NULL AND default_percentage_rate IS NULL)",
            name="ck_commission_policy_default_value",
        ),
        Index(
            "uq_commission_policy_active",
            "status",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
        Index("ix_commission_policy_status", "status", "id"),
        {"comment": "可发布且内容冻结的三级预算分佣政策"},
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    default_mode: Mapped[str | None] = mapped_column(String(16), nullable=True)
    default_amount_per_unit: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    default_percentage_rate: Mapped[Decimal | None] = mapped_column(Numeric(7, 6), nullable=True)
    max_depth: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    settle_delay_days: Mapped[int] = mapped_column(Integer, nullable=False, default=7)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    content_version: Mapped[int] = mapped_column(Integer, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_by_id: Mapped[UUID | None] = mapped_column(
        "updated_by", ForeignKey("admins.id", ondelete="SET NULL"), nullable=True
    )


class CommissionAmountRule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "commission_amount_rules"
    __table_args__ = (
        CheckConstraint("buyer_scope IN ('any', 'level')", name="ck_commission_amount_rule_buyer_scope"),
        CheckConstraint(
            "rule_mode IN ('fixed_amount', 'percentage', 'disabled')", name="ck_commission_amount_rule_mode"
        ),
        CheckConstraint(
            "(buyer_scope = 'any' AND buyer_level_id IS NULL) OR "
            "(buyer_scope = 'level' AND buyer_level_id IS NOT NULL)",
            name="ck_commission_amount_rule_buyer_level",
        ),
        CheckConstraint(
            "(product_id IS NOT NULL AND sku_id IS NULL) OR (product_id IS NULL AND sku_id IS NOT NULL)",
            name="ck_commission_amount_rule_target",
        ),
        CheckConstraint(
            "(rule_mode = 'fixed_amount' AND amount_per_unit IS NOT NULL AND amount_per_unit >= 0 "
            "AND percentage_rate IS NULL) OR "
            "(rule_mode = 'percentage' AND percentage_rate IS NOT NULL AND percentage_rate >= 0 "
            "AND percentage_rate <= 1 AND amount_per_unit IS NULL) OR "
            "(rule_mode = 'disabled' AND amount_per_unit IS NULL AND percentage_rate IS NULL)",
            name="ck_commission_amount_rule_value",
        ),
        Index(
            "uq_commission_amount_rule_product_any",
            "policy_id",
            "product_id",
            unique=True,
            postgresql_where=text("product_id IS NOT NULL AND buyer_scope = 'any'"),
        ),
        Index(
            "uq_commission_amount_rule_product_level",
            "policy_id",
            "product_id",
            "buyer_level_id",
            unique=True,
            postgresql_where=text("product_id IS NOT NULL AND buyer_scope = 'level'"),
        ),
        Index(
            "uq_commission_amount_rule_sku_any",
            "policy_id",
            "sku_id",
            unique=True,
            postgresql_where=text("sku_id IS NOT NULL AND buyer_scope = 'any'"),
        ),
        Index(
            "uq_commission_amount_rule_sku_level",
            "policy_id",
            "sku_id",
            "buyer_level_id",
            unique=True,
            postgresql_where=text("sku_id IS NOT NULL AND buyer_scope = 'level'"),
        ),
        Index("ix_commission_amount_rule_policy", "policy_id", "id"),
        {"comment": "商品或 SKU 的佣金来源预算规则"},
    )

    policy_id: Mapped[UUID] = mapped_column(ForeignKey("commission_policies.id", ondelete="RESTRICT"))
    buyer_scope: Mapped[str] = mapped_column(String(8), nullable=False, default="any")
    buyer_level_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("member_levels.id", ondelete="RESTRICT"), nullable=True
    )
    product_id: Mapped[UUID | None] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"), nullable=True)
    sku_id: Mapped[UUID | None] = mapped_column(ForeignKey("product_skus.id", ondelete="RESTRICT"), nullable=True)
    rule_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    amount_per_unit: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    percentage_rate: Mapped[Decimal | None] = mapped_column(Numeric(7, 6), nullable=True)


class CommissionDistributionRule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "commission_distribution_rules"
    __table_args__ = (
        UniqueConstraint(
            "policy_id",
            "buyer_level_id",
            "ancestor_depth",
            "beneficiary_level_id",
            name="uq_commission_distribution_rule",
        ),
        CheckConstraint("ancestor_depth BETWEEN 1 AND 3", name="ck_commission_distribution_rule_depth"),
        CheckConstraint(
            "allocation_mode IN ('percentage', 'fixed_amount')", name="ck_commission_distribution_rule_mode"
        ),
        CheckConstraint(
            "(allocation_mode = 'percentage' AND rate IS NOT NULL AND rate >= 0 AND rate <= 1 "
            "AND amount_per_unit IS NULL) OR "
            "(allocation_mode = 'fixed_amount' AND amount_per_unit IS NOT NULL AND amount_per_unit >= 0 "
            "AND rate IS NULL)",
            name="ck_commission_distribution_rule_value",
        ),
        Index("ix_commission_distribution_rule_policy", "policy_id", "ancestor_depth", "id"),
        {"comment": "按买家等级和真实推荐距离匹配的佣金矩阵"},
    )

    policy_id: Mapped[UUID] = mapped_column(ForeignKey("commission_policies.id", ondelete="RESTRICT"))
    buyer_level_id: Mapped[UUID] = mapped_column(ForeignKey("member_levels.id", ondelete="RESTRICT"))
    ancestor_depth: Mapped[int] = mapped_column(Integer, nullable=False)
    beneficiary_level_id: Mapped[UUID] = mapped_column(ForeignKey("member_levels.id", ondelete="RESTRICT"))
    allocation_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    rate: Mapped[Decimal | None] = mapped_column(Numeric(7, 6), nullable=True)
    amount_per_unit: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)


class WalletAccount(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "wallet_accounts"
    __table_args__ = (
        UniqueConstraint("user_id", "wallet_type", name="uq_wallet_account_user_type"),
        CheckConstraint("wallet_type IN ('commission', 'consumption')", name="ck_wallet_account_type"),
        CheckConstraint("available_amount >= 0", name="ck_wallet_account_available_nonnegative"),
        CheckConstraint("frozen_amount >= 0", name="ck_wallet_account_frozen_nonnegative"),
        CheckConstraint("debt_amount >= 0", name="ck_wallet_account_debt_nonnegative"),
        CheckConstraint("revision > 0", name="ck_wallet_account_revision"),
        UniqueConstraint("id", "user_id", name="uq_wallet_account_id_user"),
        {"comment": "双轨钱包账户余额与追回欠款"},
    )

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), comment="账户所属用户")
    wallet_type: Mapped[str] = mapped_column(String(16), comment="佣金或消费轨道")
    available_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=Decimal("0.00"), comment="可用余额")
    frozen_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=Decimal("0.00"), comment="提现冻结余额")
    debt_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=Decimal("0.00"), comment="退款追佣未清偿欠款")
    revision: Mapped[int] = mapped_column(Integer, default=1, comment="余额版本")


class CommissionRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "commission_records"
    __table_args__ = (
        UniqueConstraint("order_item_id", "level", name="uq_commission_order_item_level"),
        CheckConstraint("level BETWEEN 1 AND 3", name="ck_commission_level"),
        CheckConstraint("base_amount > 0", name="ck_commission_base_positive"),
        CheckConstraint("amount > 0", name="ck_commission_amount_positive"),
        CheckConstraint("recovered_amount >= 0 AND recovered_amount <= amount", name="ck_commission_recovered_range"),
        CheckConstraint("status IN ('frozen', 'settled', 'recovered')", name="ck_commission_status"),
        Index("ix_commission_settle_due", "status", "settle_after", "id"),
        CheckConstraint("revision > 0", name="ck_commission_revision"),
        Index("ix_commission_beneficiary", "beneficiary_user_id", "id"),
        {"comment": "订单明细三级分佣冻结、结算和追回事实"},
    )

    order_id: Mapped[UUID] = mapped_column(ForeignKey("orders.id", ondelete="RESTRICT"), comment="来源订单")
    order_item_id: Mapped[UUID] = mapped_column(
        ForeignKey("order_items.id", ondelete="RESTRICT"), comment="来源订单明细"
    )
    source_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), comment="付款用户")
    beneficiary_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), comment="佣金受益人")
    level: Mapped[int] = mapped_column(Integer, comment="一级或二级")
    base_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), comment="不含运费的商品实付基数")
    policy_id: Mapped[UUID] = mapped_column(ForeignKey("commission_policies.id", ondelete="RESTRICT"))
    rate: Mapped[Decimal | None] = mapped_column(Numeric(7, 6), nullable=True, comment="冻结时的比例候选参数")
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), comment="佣金总额")
    recovered_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=Decimal("0.00"), comment="累计退款追回额")
    status: Mapped[str] = mapped_column(String(16), default="frozen", comment="冻结、已结算或已追回")
    frozen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), comment="可信支付冻结时间")
    settle_after: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="交付后结算时间"
    )
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="钱包入账时间")
    recovered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="全部追回时间"
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    rule_snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, comment="不可变分佣决策快照")


class CommissionRecovery(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "commission_recoveries"
    __table_args__ = (
        UniqueConstraint("commission_id", "refund_request_id", name="uq_commission_recovery_refund"),
        CheckConstraint("amount > 0", name="ck_commission_recovery_amount_positive"),
        CheckConstraint(
            "cancelled_frozen_amount >= 0 AND wallet_deducted_amount >= 0 AND debt_created_amount >= 0 "
            "AND amount = cancelled_frozen_amount + wallet_deducted_amount + debt_created_amount",
            name="ck_commission_recovery_components",
        ),
        {"comment": "退款与佣金追回的幂等关联"},
    )

    commission_id: Mapped[UUID] = mapped_column(
        ForeignKey("commission_records.id", ondelete="RESTRICT"), comment="佣金记录"
    )
    refund_request_id: Mapped[UUID] = mapped_column(
        ForeignKey("refund_requests.id", ondelete="RESTRICT"), comment="已成功退款申请"
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), comment="本次追回金额")
    cancelled_frozen_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, default=Decimal("0.00"))
    wallet_deducted_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, default=Decimal("0.00"))
    debt_created_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, default=Decimal("0.00"))


class WalletLedger(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "wallet_ledgers"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_wallet_ledger_idempotency"),
        CheckConstraint(
            "entry_type IN ('commission_settlement', 'commission_recovery', 'withdrawal_freeze', "
            "'withdrawal_release', 'withdrawal_paid')",
            name="ck_wallet_ledger_entry_type",
        ),
        CheckConstraint("amount <> 0 OR frozen_delta <> 0 OR debt_delta <> 0", name="ck_wallet_ledger_delta_nonzero"),
        UniqueConstraint("wallet_id", "wallet_revision", name="uq_wallet_ledger_wallet_revision"),
        Index("ix_wallet_ledger_wallet_created", "wallet_id", "created_at", "id"),
        {"comment": "钱包不可变业务流水"},
    )

    wallet_id: Mapped[UUID] = mapped_column(ForeignKey("wallet_accounts.id", ondelete="RESTRICT"), comment="钱包账户")
    entry_type: Mapped[str] = mapped_column(String(32), comment="资金变动类型")
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), comment="可用余额变化，正数入账负数扣减")
    frozen_delta: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=Decimal("0.00"), comment="冻结余额变化")
    debt_delta: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=Decimal("0.00"), comment="欠款变化")
    idempotency_key: Mapped[str] = mapped_column(String(160), comment="业务幂等键")
    reference_type: Mapped[str] = mapped_column(String(32), comment="关联业务类型")
    reference_id: Mapped[UUID] = mapped_column(comment="关联业务标识")
    wallet_revision: Mapped[int] = mapped_column(Integer, nullable=False, comment="变动后账户版本")
    balance_after: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, comment="变动后余额快照")


class WithdrawalRequest(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "withdrawal_requests"
    __table_args__ = (
        UniqueConstraint("user_id", "request_id", name="uq_withdrawal_user_request"),
        UniqueConstraint("channel_reference", name="uq_withdrawal_channel_reference"),
        CheckConstraint(
            "status IN ('requested', 'approved', 'rejected', 'processing', 'succeeded', 'unknown')",
            name="ck_withdrawal_status",
        ),
        CheckConstraint("amount > 0", name="ck_withdrawal_amount_positive"),
        CheckConstraint("currency = 'CNY'", name="ck_withdrawal_currency"),
        Index("ix_withdrawal_status_created", "status", "created_at", "id"),
        {"comment": "佣金钱包提现申请与渠道执行状态"},
    )

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), comment="申请用户")
    wallet_id: Mapped[UUID] = mapped_column(ForeignKey("wallet_accounts.id", ondelete="RESTRICT"), comment="佣金钱包")
    request_id: Mapped[UUID] = mapped_column(comment="用户范围幂等请求号")
    request_hash: Mapped[str] = mapped_column(String(64), comment="规范化请求摘要")
    merchant_reference: Mapped[str] = mapped_column(String(80), unique=True, comment="服务端提现业务号")
    channel: Mapped[str] = mapped_column(String(16), comment="提现渠道适配器")
    channel_context: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, comment="非秘密渠道配置快照")
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), comment="申请金额")
    currency: Mapped[str] = mapped_column(String(3), default="CNY", comment="币种")
    destination_reference: Mapped[str] = mapped_column(String(180), comment="脱敏收款目标引用")
    status: Mapped[str] = mapped_column(String(16), default="requested", comment="申请与渠道执行状态")
    review_note: Mapped[str | None] = mapped_column(String(300), nullable=True, comment="审核说明")
    reviewed_by_id: Mapped[UUID | None] = mapped_column(nullable=True, comment="审核管理员")
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="审核时间")
    channel_reference: Mapped[str | None] = mapped_column(String(160), nullable=True, comment="未来渠道打款流水")
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="渠道确认时间"
    )
    channel_paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payload_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    revision: Mapped[int] = mapped_column(Integer, default=1, comment="状态版本")


class DurableTask(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "durable_tasks"
    __table_args__ = (
        UniqueConstraint("task_type", "business_key", name="uq_durable_task_type_business_key"),
        CheckConstraint("status IN ('pending', 'running', 'succeeded', 'attention')", name="ck_durable_task_status"),
        CheckConstraint("attempt_count >= 0", name="ck_durable_task_attempt_count"),
        CheckConstraint("failure_count >= 0", name="ck_durable_task_failure_count"),
        CheckConstraint("max_failures > 0", name="ck_durable_task_max_failures"),
        CheckConstraint("revision > 0", name="ck_durable_task_revision"),
        CheckConstraint("jsonb_typeof(payload) = 'object'", name="ck_durable_task_payload_object"),
        CheckConstraint(
            "(status = 'running' AND lease_token IS NOT NULL AND lease_until IS NOT NULL AND completed_at IS NULL) OR "
            "(status = 'succeeded' AND lease_token IS NULL AND lease_until IS NULL AND completed_at IS NOT NULL) OR "
            "(status IN ('pending', 'attention') AND lease_token IS NULL AND lease_until IS NULL AND completed_at IS NULL)",
            name="ck_durable_task_state_columns",
        ),
        Index("ix_durable_task_pending", "available_at", "id", postgresql_where=text("status = 'pending'")),
        Index("ix_durable_task_running", "lease_until", "id", postgresql_where=text("status = 'running'")),
        {"comment": "可恢复且带租约的数据库持久任务"},
    )

    task_type: Mapped[str] = mapped_column(String(64), nullable=False)
    business_key: Mapped[str] = mapped_column(String(160), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    lease_token: Mapped[UUID | None] = mapped_column(nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_error_summary: Mapped[str | None] = mapped_column(String(500), nullable=True)
