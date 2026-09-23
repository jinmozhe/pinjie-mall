import hashlib
import json
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.core.identifiers import new_uuid7
from app.db.models.commerce_lifecycle import Fulfillment, RefundRequest
from app.db.models.distribution import (
    CommissionRecord,
    CommissionRecovery,
    MemberProfile,
    WalletAccount,
    WalletLedger,
    WithdrawalRequest,
)
from app.db.models.order import Order
from app.db.transaction import transaction_scope
from app.domains.durable_tasks import DurableTaskService
from app.domains.users import UserAccessService

from .commission_freeze import freeze_paid_commissions
from .repository import DistributionRepository
from .schemas import (
    CommissionPage,
    CommissionRead,
    MemberProfileRead,
    ReferralBindIn,
    WalletAccountRead,
    WithdrawalCreate,
    WithdrawalManualCompletion,
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
    def _wallet_balance_after(wallet: WalletAccount) -> dict[str, str]:
        return {
            "available_amount": str(wallet.available_amount),
            "frozen_amount": str(wallet.frozen_amount),
            "debt_amount": str(wallet.debt_amount),
        }

    async def _write_wallet_ledger(
        self,
        *,
        wallet: WalletAccount,
        entry_type: str,
        amount: Decimal,
        frozen_delta: Decimal,
        debt_delta: Decimal,
        idempotency_key: str,
        reference_type: str,
        reference_id: UUID,
    ) -> None:
        await self.repository.save(
            WalletLedger(
                id=new_uuid7(),
                wallet_id=wallet.id,
                entry_type=entry_type,
                amount=amount,
                frozen_delta=frozen_delta,
                debt_delta=debt_delta,
                idempotency_key=idempotency_key,
                reference_type=reference_type,
                reference_id=reference_id,
                wallet_revision=wallet.revision,
                balance_after=self._wallet_balance_after(wallet),
            )
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
            level_id=None,
            level_changed_at=datetime.now(UTC),
            inviter_id=None,
            bound_at=None,
            revision=1,
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

    async def matched_withdrawal_id_in_open_transaction(
        self, *, channel: str, channel_reference: str, amount: Decimal, currency: str
    ) -> UUID | None:
        withdrawal = await self.repository.withdrawal_by_channel_reference(channel, channel_reference, lock=True)
        if (
            withdrawal is None
            or withdrawal.status != "succeeded"
            or withdrawal.amount != amount
            or withdrawal.currency != currency
        ):
            return None
        return withdrawal.id

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
                merchant_reference=f"W3-{new_uuid7()}",
                channel="manual",
                channel_context={"schema_version": 1, "merchant_id": None, "app_id": None, "config_version": None},
                amount=amount,
                currency="CNY",
                destination_reference=data.destination_reference,
                status="requested",
                revision=1,
            )
            self._check_wallet(wallet)
            await self.repository.save(wallet)
            await self.repository.save(withdrawal)
            await self._write_wallet_ledger(
                wallet=wallet,
                entry_type="withdrawal_freeze",
                amount=-amount,
                frozen_delta=amount,
                debt_delta=Decimal("0.00"),
                idempotency_key=f"withdrawal-freeze:{withdrawal.id}",
                reference_type="withdrawal",
                reference_id=withdrawal.id,
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
        await self._write_wallet_ledger(
            wallet=wallet,
            entry_type="withdrawal_release",
            amount=withdrawal.amount - debt_offset,
            frozen_delta=-withdrawal.amount,
            debt_delta=-debt_offset,
            idempotency_key=f"withdrawal-release:{withdrawal.id}",
            reference_type="withdrawal",
            reference_id=withdrawal.id,
        )
        return self._withdrawal_read(withdrawal)

    async def complete_withdrawal_manually_in_open_transaction(
        self, withdrawal_id: UUID, data: WithdrawalManualCompletion, actor_id: UUID
    ) -> WithdrawalRead:
        withdrawal = await self.repository.withdrawal(withdrawal_id, lock=True)
        if withdrawal is None:
            raise AppException(status_code=404, code=ErrorCode.WITHDRAWAL_NOT_FOUND, message="提现申请不存在")
        if withdrawal.status != "approved" or withdrawal.revision != data.revision:
            raise AppException(
                status_code=409, code=ErrorCode.WITHDRAWAL_STATE_CONFLICT, message="提现状态已变化，请重新读取"
            )
        wallet = await self._commission_wallet(withdrawal.user_id, lock=True)
        if wallet.frozen_amount < withdrawal.amount:
            raise AppException(status_code=409, code=ErrorCode.WITHDRAWAL_STATE_CONFLICT, message="提现冻结余额异常")
        paid_at = datetime.now(UTC)
        wallet.frozen_amount -= withdrawal.amount
        wallet.revision += 1
        withdrawal.status = "succeeded"
        withdrawal.channel_reference = data.payment_reference
        withdrawal.confirmed_at = paid_at
        withdrawal.channel_paid_at = paid_at
        withdrawal.payload_hash = self._request_hash(
            {"merchant_reference": withdrawal.merchant_reference, "payment_reference": data.payment_reference}
        )
        withdrawal.review_note = f"{withdrawal.review_note}\n线下转账确认：{data.note}"[:300]
        withdrawal.reviewed_by_id = actor_id
        withdrawal.reviewed_at = paid_at
        withdrawal.revision += 1
        self._check_wallet(wallet)
        await self.repository.save(wallet)
        await self.repository.save(withdrawal)
        await self._write_wallet_ledger(
            wallet=wallet,
            entry_type="withdrawal_paid",
            amount=Decimal("0.00"),
            frozen_delta=-withdrawal.amount,
            debt_delta=Decimal("0.00"),
            idempotency_key=f"withdrawal-paid:{withdrawal.id}",
            reference_type="withdrawal",
            reference_id=withdrawal.id,
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
        await freeze_paid_commissions(self.session, order_id=order_id, source_user_id=source_user_id, paid_at=paid_at)

    async def schedule_settlement_for_delivery_in_open_transaction(
        self, order_id: UUID, delivered_at: datetime
    ) -> None:
        commissions = await self.repository.commissions_for_order(order_id, lock=True)
        scheduled_at: datetime | None = None
        changed = False
        for commission in commissions:
            if commission.status == "frozen" and commission.settle_after is None:
                delay_days = commission.rule_snapshot.get("settle_delay_days")
                if not isinstance(delay_days, int) or isinstance(delay_days, bool) or delay_days < 0:
                    raise AppException(
                        status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="佣金冻结政策缺少有效结算等待期"
                    )
                commission.settle_after = delivered_at + timedelta(days=delay_days)
                scheduled_at = (
                    commission.settle_after if scheduled_at is None else min(scheduled_at, commission.settle_after)
                )
                commission.revision += 1
                await self.repository.save(commission)
                changed = True
        if changed and scheduled_at is not None:
            await DurableTaskService(self.session).enqueue_in_open_transaction(
                task_type="commission_settlement",
                business_key=f"commission-settlement:{order_id}",
                payload={"schema_version": 1, "order_id": str(order_id)},
                available_at=scheduled_at,
            )

    async def settle_due(self, limit: int = 100) -> int:
        async with transaction_scope(self.session):
            return await self.settle_due_in_open_transaction(limit)

    async def settle_due_in_open_transaction(self, limit: int = 100) -> int:
        if not 1 <= limit <= 100:
            raise AppException(status_code=422, code=ErrorCode.VALIDATION_ERROR, message="佣金结算数量无效")
        now = datetime.now(UTC)
        commissions = await self.repository.due_commissions(now, limit)
        return await self._settle_commissions_in_open_transaction(commissions, now)

    async def settle_order_scheduled(self, order_id: UUID) -> int:
        async with transaction_scope(self.session):
            commissions = await self.repository.commissions_for_order(order_id, lock=True)
            due = [
                item
                for item in commissions
                if item.status == "frozen" and item.settle_after is not None and item.settle_after <= datetime.now(UTC)
            ]
            return await self._settle_commissions_in_open_transaction(due, datetime.now(UTC))

    async def _settlement_ready_in_open_transaction(self, commission: CommissionRecord) -> bool:
        order = await self.session.get(Order, commission.order_id, with_for_update=True)
        if order is None:
            raise AppException(status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="佣金来源订单不存在")
        fulfillment = (
            await self.session.scalars(
                select(Fulfillment)
                .where(Fulfillment.order_id == order.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).one_or_none()
        if fulfillment is None or fulfillment.status != "delivered":
            return False
        refunds = list(
            await self.session.scalars(
                select(RefundRequest)
                .where(RefundRequest.order_id == order.id)
                .order_by(RefundRequest.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        )
        return not any(refund.status in {"requested", "approved"} for refund in refunds)

    async def _settle_commissions_in_open_transaction(self, commissions: list[CommissionRecord], now: datetime) -> int:
        ready = [item for item in commissions if await self._settlement_ready_in_open_transaction(item)]
        settled = 0
        await self.repository.lock_wallets(sorted({item.beneficiary_user_id for item in ready}))
        for commission in ready:
            remaining = self._money(commission.amount - commission.recovered_amount)
            if remaining <= 0:
                commission.status = "recovered"
                commission.recovered_at = now
                commission.revision += 1
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
            await self._write_wallet_ledger(
                wallet=wallet,
                entry_type="commission_settlement",
                amount=credited,
                frozen_delta=Decimal("0.00"),
                debt_delta=-debt_offset,
                idempotency_key=f"commission-settlement:{commission.id}",
                reference_type="commission",
                reference_id=commission.id,
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
        if cumulative_refunded_amount < 0:
            raise AppException(status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="退款佣金基数异常")
        commissions = await self.repository.commissions_for_order(order_id, lock=True)
        await self.repository.lock_wallets(sorted({item.beneficiary_user_id for item in commissions}))
        for commission in commissions:
            if (
                commission.status == "recovered"
                or await self.repository.recovery(commission.id, refund_request_id) is not None
            ):
                continue
            amount = self._money(commission.amount - commission.recovered_amount)
            if amount <= 0:
                continue
            commission.recovered_amount += amount
            cancelled_frozen_amount = amount if commission.status == "frozen" else Decimal("0.00")
            wallet_deducted_amount = Decimal("0.00")
            debt_created_amount = Decimal("0.00")
            if commission.status == "settled":
                wallet = await self._commission_wallet(commission.beneficiary_user_id, lock=True)
                available_debit = min(wallet.available_amount, amount)
                debt_increase = amount - available_debit
                wallet.available_amount -= available_debit
                wallet.debt_amount += debt_increase
                wallet.revision += 1
                self._check_wallet(wallet)
                await self.repository.save(wallet)
                wallet_deducted_amount = available_debit
                debt_created_amount = debt_increase
                await self._write_wallet_ledger(
                    wallet=wallet,
                    entry_type="commission_recovery",
                    amount=-available_debit,
                    frozen_delta=Decimal("0.00"),
                    debt_delta=debt_increase,
                    idempotency_key=f"commission-recovery:{commission.id}:{refund_request_id}",
                    reference_type="recovery",
                    reference_id=refund_request_id,
                )
            await self.repository.save(
                CommissionRecovery(
                    id=new_uuid7(),
                    commission_id=commission.id,
                    refund_request_id=refund_request_id,
                    amount=amount,
                    cancelled_frozen_amount=cancelled_frozen_amount,
                    wallet_deducted_amount=wallet_deducted_amount,
                    debt_created_amount=debt_created_amount,
                )
            )
            if commission.recovered_amount == commission.amount:
                commission.status = "recovered"
                commission.recovered_at = refunded_at
            commission.revision += 1
            await self.repository.save(commission)
