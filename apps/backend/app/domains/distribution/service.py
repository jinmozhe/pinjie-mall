import hashlib
import json
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.core.identifiers import new_uuid7
from app.db.models.distribution import (
    CommissionRecord,
    CommissionRecovery,
    MemberProfile,
    WalletAccount,
    WalletLedger,
    WithdrawalRequest,
)
from app.db.transaction import transaction_scope
from app.domains.users import UserAccessService

from .repository import DistributionRepository
from .schemas import (
    CommissionPage,
    CommissionRead,
    MemberProfileRead,
    ReferralBindIn,
    WalletAccountRead,
    WithdrawalCreate,
    WithdrawalPage,
    WithdrawalRead,
    WithdrawalReview,
)

MONEY = Decimal("0.01")
COMMISSION_RATES: tuple[Decimal, Decimal] = (Decimal("0.1000"), Decimal("0.0500"))


class DistributionService:
    def __init__(
        self,
        session: AsyncSession,
        repository: DistributionRepository | None = None,
        *,
        access: UserAccessService | None = None,
    ) -> None:
        self.session = session
        self.repository = repository or DistributionRepository(session)
        self.access = access or UserAccessService(session)

    @staticmethod
    def _money(value: Decimal) -> Decimal:
        return value.quantize(MONEY, rounding=ROUND_HALF_UP)

    @staticmethod
    def _check_wallet(wallet: WalletAccount) -> None:
        maximum = Decimal("9999999999999.99")
        if (
            any(
                value < 0 or value > maximum
                for value in (wallet.available_amount, wallet.frozen_amount, wallet.debt_amount)
            )
            or wallet.available_amount + wallet.frozen_amount > maximum
        ):
            raise AppException(
                status_code=409, code=ErrorCode.WITHDRAWAL_STATE_CONFLICT, message="钱包余额超过允许范围"
            )

    @staticmethod
    def _request_hash(payload: object) -> str:
        return hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    @staticmethod
    def _profile_read(profile: MemberProfile) -> MemberProfileRead:
        return MemberProfileRead.model_validate(profile)

    @staticmethod
    def _wallet_read(wallet: WalletAccount) -> WalletAccountRead:
        return WalletAccountRead.model_validate(wallet)

    @staticmethod
    def _commission_read(commission: CommissionRecord) -> CommissionRead:
        return CommissionRead.model_validate(commission)

    @staticmethod
    def _withdrawal_read(withdrawal: WithdrawalRequest) -> WithdrawalRead:
        return WithdrawalRead.model_validate(withdrawal)

    @staticmethod
    def _new_invitation_code() -> str:
        return new_uuid7().hex[-16:].upper()

    async def _ensure_profile(self, user_id: UUID) -> MemberProfile:
        profile = await self.repository.profile(user_id, lock=True)
        if profile is not None:
            return profile
        profile = MemberProfile(
            id=new_uuid7(),
            user_id=user_id,
            invitation_code=self._new_invitation_code(),
            level_code="standard",
            inviter_id=None,
            bound_at=None,
        )
        await self.repository.save(profile)
        for wallet_type in ("commission", "consumption"):
            await self.repository.save(
                WalletAccount(
                    id=new_uuid7(),
                    user_id=user_id,
                    wallet_type=wallet_type,
                    available_amount=Decimal("0.00"),
                    frozen_amount=Decimal("0.00"),
                    debt_amount=Decimal("0.00"),
                    revision=1,
                )
            )
        return profile

    async def _commission_wallet(self, user_id: UUID, *, lock: bool) -> WalletAccount:
        wallet = await self.repository.wallet(user_id, "commission", lock=lock)
        if wallet is not None:
            return wallet
        await self._ensure_profile(user_id)
        wallet = await self.repository.wallet(user_id, "commission", lock=lock)
        if wallet is None:
            raise AppException(status_code=503, code=ErrorCode.SERVICE_UNAVAILABLE, message="佣金钱包初始化失败")
        return wallet

    async def activate_profile(self, user_id: UUID) -> MemberProfileRead:
        async with transaction_scope(self.session):
            await self.access.require_active_user(user_id)
            return self._profile_read(await self._ensure_profile(user_id))

    async def lock_referral_changes(self) -> None:
        """支付编排须在订单与库存锁之前取得关系图锁。"""
        await self.repository.lock_referral_graph()

    async def profile_for_user(self, user_id: UUID) -> MemberProfileRead:
        profile = await self.repository.profile(user_id)
        if profile is None:
            raise AppException(
                status_code=404, code=ErrorCode.DISTRIBUTION_PROFILE_NOT_FOUND, message="请先开通会员分销档案"
            )
        return self._profile_read(profile)

    async def bind_referrer(self, user_id: UUID, data: ReferralBindIn) -> MemberProfileRead:
        async with transaction_scope(self.session):
            await self.repository.lock_referral_graph()
            await self.access.require_active_user(user_id)
            profile = await self._ensure_profile(user_id)
            inviter = await self.repository.profile_by_code(data.invitation_code)
            if inviter is None:
                raise AppException(
                    status_code=404, code=ErrorCode.DISTRIBUTION_REFERRAL_REJECTED, message="邀请码不存在"
                )
            locked = await self.repository.lock_profiles(
                sorted([profile.user_id, inviter.user_id], key=lambda item: item.hex)
            )
            locked_by_user = {item.user_id: item for item in locked}
            locked_profile = locked_by_user.get(user_id)
            locked_inviter = locked_by_user.get(inviter.user_id)
            if locked_profile is None or locked_inviter is None:
                raise AppException(
                    status_code=409, code=ErrorCode.DISTRIBUTION_REFERRAL_REJECTED, message="推荐关系状态已变化"
                )
            profile = locked_profile
            inviter = locked_inviter
            if profile.user_id == inviter.user_id:
                raise AppException(
                    status_code=409, code=ErrorCode.DISTRIBUTION_REFERRAL_REJECTED, message="不能绑定自己的邀请码"
                )
            if profile.inviter_id is not None:
                if profile.inviter_id == inviter.user_id:
                    return self._profile_read(profile)
                raise AppException(
                    status_code=409, code=ErrorCode.DISTRIBUTION_REFERRAL_REJECTED, message="推荐关系只能首次绑定"
                )
            cursor: UUID | None = inviter.user_id
            visited: set[UUID] = set()
            while cursor is not None:
                if cursor == profile.user_id or cursor in visited:
                    raise AppException(
                        status_code=409, code=ErrorCode.DISTRIBUTION_REFERRAL_REJECTED, message="推荐关系不能形成循环"
                    )
                visited.add(cursor)
                ancestor = await self.repository.profile(cursor)
                cursor = ancestor.inviter_id if ancestor is not None else None
            profile.inviter_id = inviter.user_id
            profile.bound_at = datetime.now(UTC)
            await self.repository.save(profile)
            return self._profile_read(profile)

    async def wallets_for_user(self, user_id: UUID) -> list[WalletAccountRead]:
        wallets = await self.repository.wallets(user_id)
        if len(wallets) != 2:
            raise AppException(
                status_code=404, code=ErrorCode.DISTRIBUTION_PROFILE_NOT_FOUND, message="请先开通会员分销档案"
            )
        return [self._wallet_read(wallet) for wallet in wallets]

    async def commissions_for_user(self, user_id: UUID, page: int, page_size: int) -> CommissionPage:
        rows, total = await self.repository.commissions_for_user(user_id, page, page_size)
        return CommissionPage.create(
            items=[self._commission_read(item) for item in rows], total=total, page=page, page_size=page_size
        )

    async def withdrawals_for_user(self, user_id: UUID, page: int, page_size: int) -> WithdrawalPage:
        rows, total = await self.repository.withdrawals_for_user(user_id, page, page_size)
        return WithdrawalPage.create(
            items=[self._withdrawal_read(item) for item in rows], total=total, page=page, page_size=page_size
        )

    async def create_withdrawal(self, user_id: UUID, data: WithdrawalCreate) -> WithdrawalRead:
        request_hash = self._request_hash(
            {"amount": str(data.amount), "destination_reference": data.destination_reference}
        )
        async with transaction_scope(self.session):
            await self.access.require_active_user(user_id)
            existing = await self.repository.withdrawal_by_request(user_id, data.request_id, lock=True)
            if existing is not None:
                if existing.amount != data.amount or existing.destination_reference != data.destination_reference:
                    raise AppException(
                        status_code=409, code=ErrorCode.WITHDRAWAL_REQUEST_CONFLICT, message="提现请求号已用于其他内容"
                    )
                return self._withdrawal_read(existing)
            wallet = await self._commission_wallet(user_id, lock=True)
            amount = self._money(data.amount)
            if wallet.debt_amount > 0 or wallet.available_amount < amount:
                raise AppException(
                    status_code=409, code=ErrorCode.WALLET_INSUFFICIENT_BALANCE, message="佣金钱包可提现余额不足"
                )
            wallet.available_amount -= amount
            wallet.frozen_amount += amount
            wallet.revision += 1
            withdrawal = WithdrawalRequest(
                id=new_uuid7(),
                user_id=user_id,
                wallet_id=wallet.id,
                request_id=data.request_id,
                request_hash=request_hash,
                amount=amount,
                currency="CNY",
                destination_reference=data.destination_reference,
                status="requested",
                revision=1,
            )
            self._check_wallet(wallet)
            await self.repository.save(wallet)
            await self.repository.save(withdrawal)
            await self.repository.save(
                WalletLedger(
                    id=new_uuid7(),
                    wallet_id=wallet.id,
                    entry_type="withdrawal_freeze",
                    amount=-amount,
                    frozen_delta=amount,
                    debt_delta=Decimal("0.00"),
                    idempotency_key=f"withdrawal-freeze:{withdrawal.id}",
                    reference_type="withdrawal",
                    reference_id=withdrawal.id,
                )
            )
            return self._withdrawal_read(withdrawal)

    async def approve_withdrawal_in_open_transaction(
        self, withdrawal_id: UUID, data: WithdrawalReview, actor_id: UUID
    ) -> WithdrawalRead:
        withdrawal = await self.repository.withdrawal(withdrawal_id, lock=True)
        if withdrawal is None:
            raise AppException(status_code=404, code=ErrorCode.WITHDRAWAL_NOT_FOUND, message="提现申请不存在")
        if withdrawal.status != "requested" or withdrawal.revision != data.revision:
            raise AppException(
                status_code=409, code=ErrorCode.WITHDRAWAL_STATE_CONFLICT, message="提现状态已变化，请重新读取"
            )
        wallet = await self._commission_wallet(withdrawal.user_id, lock=True)
        if wallet.debt_amount > 0 or wallet.frozen_amount < withdrawal.amount:
            raise AppException(
                status_code=409,
                code=ErrorCode.WITHDRAWAL_STATE_CONFLICT,
                message="存在追佣欠款或冻结余额异常，不能批准提现",
            )
        withdrawal.status = "approved"
        withdrawal.review_note = data.note
        withdrawal.reviewed_by_id = actor_id
        withdrawal.reviewed_at = datetime.now(UTC)
        withdrawal.revision += 1
        await self.repository.save(withdrawal)
        return self._withdrawal_read(withdrawal)

    async def reject_withdrawal_in_open_transaction(
        self, withdrawal_id: UUID, data: WithdrawalReview, actor_id: UUID
    ) -> WithdrawalRead:
        withdrawal = await self.repository.withdrawal(withdrawal_id, lock=True)
        if withdrawal is None:
            raise AppException(status_code=404, code=ErrorCode.WITHDRAWAL_NOT_FOUND, message="提现申请不存在")
        if withdrawal.status != "requested" or withdrawal.revision != data.revision:
            raise AppException(
                status_code=409, code=ErrorCode.WITHDRAWAL_STATE_CONFLICT, message="提现状态已变化，请重新读取"
            )
        wallet = await self._commission_wallet(withdrawal.user_id, lock=True)
        if wallet.frozen_amount < withdrawal.amount:
            raise AppException(status_code=409, code=ErrorCode.WITHDRAWAL_STATE_CONFLICT, message="提现冻结余额异常")
        wallet.frozen_amount -= withdrawal.amount
        debt_offset = min(wallet.debt_amount, withdrawal.amount)
        wallet.debt_amount -= debt_offset
        wallet.available_amount += withdrawal.amount - debt_offset
        wallet.revision += 1
        withdrawal.status = "rejected"
        withdrawal.review_note = data.note
        withdrawal.reviewed_by_id = actor_id
        withdrawal.reviewed_at = datetime.now(UTC)
        withdrawal.revision += 1
        self._check_wallet(wallet)
        await self.repository.save(wallet)
        await self.repository.save(withdrawal)
        await self.repository.save(
            WalletLedger(
                id=new_uuid7(),
                wallet_id=wallet.id,
                entry_type="withdrawal_release",
                amount=withdrawal.amount - debt_offset,
                frozen_delta=-withdrawal.amount,
                debt_delta=-debt_offset,
                idempotency_key=f"withdrawal-release:{withdrawal.id}",
                reference_type="withdrawal",
                reference_id=withdrawal.id,
            )
        )
        return self._withdrawal_read(withdrawal)

    async def pending_withdrawals(self, page: int, page_size: int) -> WithdrawalPage:
        rows, total = await self.repository.pending_withdrawals(page, page_size)
        return WithdrawalPage.create(
            items=[self._withdrawal_read(item) for item in rows], total=total, page=page, page_size=page_size
        )

    async def freeze_commissions_for_payment_in_open_transaction(
        self, *, order_id: UUID, source_user_id: UUID, base_amount: Decimal, paid_at: datetime
    ) -> None:
        if base_amount <= 0:
            return
        await self.repository.lock_referral_graph()
        existing = await self.repository.commissions_for_order(order_id, lock=True)
        if existing:
            return
        profile = await self.repository.profile(source_user_id)
        if profile is None or profile.inviter_id is None or profile.bound_at is None or profile.bound_at > paid_at:
            return
        inviter_id: UUID | None = profile.inviter_id
        visited = {source_user_id}
        for level, rate in enumerate(COMMISSION_RATES, start=1):
            if inviter_id is None:
                break
            if inviter_id in visited:
                raise AppException(
                    status_code=409, code=ErrorCode.DISTRIBUTION_REFERRAL_REJECTED, message="推荐关系异常，不能冻结佣金"
                )
            visited.add(inviter_id)
            inviter = await self.repository.profile(inviter_id)
            if inviter is None:
                raise AppException(
                    status_code=409,
                    code=ErrorCode.DISTRIBUTION_REFERRAL_REJECTED,
                    message="推荐人档案缺失，不能冻结佣金",
                )
            amount = self._money(base_amount * rate)
            if amount > 0:
                await self.repository.save(
                    CommissionRecord(
                        id=new_uuid7(),
                        order_id=order_id,
                        source_user_id=source_user_id,
                        beneficiary_user_id=inviter.user_id,
                        level=level,
                        base_amount=base_amount,
                        rate=rate,
                        amount=amount,
                        recovered_amount=Decimal("0.00"),
                        status="frozen",
                        frozen_at=paid_at,
                        settle_after=None,
                        settled_at=None,
                        recovered_at=None,
                    )
                )
            inviter_id = inviter.inviter_id if inviter.bound_at is not None and inviter.bound_at <= paid_at else None

    async def schedule_settlement_for_delivery_in_open_transaction(
        self, order_id: UUID, delivered_at: datetime
    ) -> None:
        commissions = await self.repository.commissions_for_order(order_id, lock=True)
        settle_after = delivered_at + timedelta(days=7)
        for commission in commissions:
            if commission.status == "frozen" and commission.settle_after is None:
                commission.settle_after = settle_after
                await self.repository.save(commission)

    async def settle_due(self, limit: int = 100) -> int:
        async with transaction_scope(self.session):
            return await self.settle_due_in_open_transaction(limit)

    async def settle_due_in_open_transaction(self, limit: int = 100) -> int:
        now = datetime.now(UTC)
        settled = 0
        commissions = await self.repository.due_commissions(now, limit)
        await self.repository.lock_wallets(sorted({item.beneficiary_user_id for item in commissions}))
        for commission in commissions:
            remaining = self._money(commission.amount - commission.recovered_amount)
            if remaining <= 0:
                commission.status = "recovered"
                commission.recovered_at = now
                await self.repository.save(commission)
                continue
            wallet = await self._commission_wallet(commission.beneficiary_user_id, lock=True)
            debt_offset = min(wallet.debt_amount, remaining)
            credited = remaining - debt_offset
            wallet.debt_amount -= debt_offset
            wallet.available_amount += credited
            wallet.revision += 1
            commission.status = "settled"
            commission.settled_at = now
            self._check_wallet(wallet)
            await self.repository.save(wallet)
            await self.repository.save(commission)
            await self.repository.save(
                WalletLedger(
                    id=new_uuid7(),
                    wallet_id=wallet.id,
                    entry_type="commission_settlement",
                    amount=credited,
                    frozen_delta=Decimal("0.00"),
                    debt_delta=-debt_offset,
                    idempotency_key=f"commission-settlement:{commission.id}",
                    reference_type="commission",
                    reference_id=commission.id,
                )
            )
            settled += 1
        return settled

    async def recover_for_refund_in_open_transaction(
        self,
        *,
        refund_request_id: UUID,
        order_id: UUID,
        cumulative_refunded_amount: Decimal,
        refunded_at: datetime,
    ) -> None:
        if cumulative_refunded_amount <= 0:
            return
        commissions = await self.repository.commissions_for_order(order_id, lock=True)
        await self.repository.lock_wallets(sorted({item.beneficiary_user_id for item in commissions}))
        for commission in commissions:
            if (
                commission.status == "recovered"
                or await self.repository.recovery(commission.id, refund_request_id) is not None
            ):
                continue
            if cumulative_refunded_amount > commission.base_amount:
                raise AppException(
                    status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="累计退款金额超过佣金基数"
                )
            target = self._money(commission.amount * cumulative_refunded_amount / commission.base_amount)
            amount = max(Decimal("0.00"), target - commission.recovered_amount)
            if amount <= 0:
                continue
            commission.recovered_amount += amount
            await self.repository.save(
                CommissionRecovery(
                    id=new_uuid7(), commission_id=commission.id, refund_request_id=refund_request_id, amount=amount
                )
            )
            if commission.status == "settled":
                wallet = await self._commission_wallet(commission.beneficiary_user_id, lock=True)
                available_debit = min(wallet.available_amount, amount)
                debt_increase = amount - available_debit
                wallet.available_amount -= available_debit
                wallet.debt_amount += debt_increase
                wallet.revision += 1
                self._check_wallet(wallet)
                await self.repository.save(wallet)
                await self.repository.save(
                    WalletLedger(
                        id=new_uuid7(),
                        wallet_id=wallet.id,
                        entry_type="commission_recovery",
                        amount=-available_debit,
                        frozen_delta=Decimal("0.00"),
                        debt_delta=debt_increase,
                        idempotency_key=f"commission-recovery:{commission.id}:{refund_request_id}",
                        reference_type="refund",
                        reference_id=refund_request_id,
                    )
                )
            if commission.recovered_amount == commission.amount:
                commission.status = "recovered"
                commission.recovered_at = refunded_at
            await self.repository.save(commission)
