from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class MemberProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "member_profiles"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_member_profile_user"),
        UniqueConstraint("invitation_code", name="uq_member_profile_invitation_code"),
        CheckConstraint("level_code = 'standard'", name="ck_member_profile_initial_level"),
        Index("ix_member_profile_inviter", "inviter_id", "id"),
        {"comment": "会员档案与不可变首次推荐关系"},
    )

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), comment="会员用户")
    invitation_code: Mapped[str] = mapped_column(String(16), comment="本人唯一推荐码")
    level_code: Mapped[str] = mapped_column(String(32), default="standard", comment="当前会员等级")
    inviter_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, comment="首次绑定的推荐人"
    )
    bound_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="推荐关系绑定时间"
    )


class WalletAccount(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "wallet_accounts"
    __table_args__ = (
        UniqueConstraint("user_id", "wallet_type", name="uq_wallet_account_user_type"),
        CheckConstraint("wallet_type IN ('commission', 'consumption')", name="ck_wallet_account_type"),
        CheckConstraint("available_amount >= 0", name="ck_wallet_account_available_nonnegative"),
        CheckConstraint("frozen_amount >= 0", name="ck_wallet_account_frozen_nonnegative"),
        CheckConstraint("debt_amount >= 0", name="ck_wallet_account_debt_nonnegative"),
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
        UniqueConstraint("order_id", "level", name="uq_commission_order_level"),
        CheckConstraint("level IN (1, 2)", name="ck_commission_level"),
        CheckConstraint("rate IN (0.1000, 0.0500)", name="ck_commission_rate"),
        CheckConstraint("base_amount > 0", name="ck_commission_base_positive"),
        CheckConstraint("amount > 0", name="ck_commission_amount_positive"),
        CheckConstraint("recovered_amount >= 0 AND recovered_amount <= amount", name="ck_commission_recovered_range"),
        CheckConstraint("status IN ('frozen', 'settled', 'recovered')", name="ck_commission_status"),
        Index("ix_commission_settle_due", "status", "settle_after", "id"),
        Index("ix_commission_beneficiary", "beneficiary_user_id", "created_at", "id"),
        {"comment": "两级分佣规则快照与生命周期"},
    )

    order_id: Mapped[UUID] = mapped_column(ForeignKey("orders.id", ondelete="RESTRICT"), comment="来源订单")
    source_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), comment="付款用户")
    beneficiary_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), comment="佣金受益人")
    level: Mapped[int] = mapped_column(Integer, comment="一级或二级")
    base_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), comment="不含运费的商品实付基数")
    rate: Mapped[Decimal] = mapped_column(Numeric(5, 4), comment="冻结时的佣金比例")
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


class CommissionRecovery(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "commission_recoveries"
    __table_args__ = (
        UniqueConstraint("commission_id", "refund_request_id", name="uq_commission_recovery_refund"),
        CheckConstraint("amount > 0", name="ck_commission_recovery_amount_positive"),
        {"comment": "退款与佣金追回的幂等关联"},
    )

    commission_id: Mapped[UUID] = mapped_column(
        ForeignKey("commission_records.id", ondelete="RESTRICT"), comment="佣金记录"
    )
    refund_request_id: Mapped[UUID] = mapped_column(
        ForeignKey("refund_requests.id", ondelete="RESTRICT"), comment="已成功退款申请"
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), comment="本次追回金额")


class WalletLedger(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "wallet_ledgers"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_wallet_ledger_idempotency"),
        CheckConstraint(
            "entry_type IN ('commission_settlement', 'commission_recovery', 'withdrawal_freeze', 'withdrawal_release')",
            name="ck_wallet_ledger_entry_type",
        ),
        CheckConstraint("amount <> 0 OR frozen_delta <> 0 OR debt_delta <> 0", name="ck_wallet_ledger_delta_nonzero"),
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
    revision: Mapped[int] = mapped_column(Integer, default=1, comment="状态版本")
