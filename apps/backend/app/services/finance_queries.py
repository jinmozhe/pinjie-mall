"""Read-only, owner-filtered consumer projection over existing distribution facts."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.core.pagination import PageResult
from app.db.models.distribution import (
    CommissionRecord,
    MemberLevel,
    MemberProfile,
    WalletAccount,
    WalletLedger,
    WithdrawalRequest,
)
from app.domains.distribution import DistributionService
from app.domains.users import UserAccessService
from app.services.finance_query_schemas import (
    ConsumerCommissionRead,
    ConsumerMemberRead,
    ConsumerWalletLedgerRead,
    ConsumerWalletRead,
    ConsumerWithdrawalRead,
    WalletType,
)


def member_read(profile: MemberProfile | None, level: MemberLevel | None) -> ConsumerMemberRead:
    if profile is None:
        return ConsumerMemberRead(
            state="not_opened",
            level_name=None,
            level_changed_at=None,
            created_at=None,
            referral_bound=False,
            bound_at=None,
        )
    if profile.level_id is not None and (level is None or level.id != profile.level_id):
        raise AppException(status_code=409, code=ErrorCode.STATE_CONFLICT, message="会员等级事实不一致")
    return ConsumerMemberRead(
        state="no_level"
        if profile.level_id is None
        else "active"
        if level is not None and level.is_active
        else "inactive",
        level_name=level.name if level is not None else None,
        level_changed_at=profile.level_changed_at,
        created_at=profile.created_at,
        referral_bound=profile.inviter_id is not None,
        bound_at=profile.bound_at,
    )


def withdrawal_read(row: WithdrawalRequest) -> ConsumerWithdrawalRead:
    confirmed = row.status == "succeeded" and row.confirmed_at is not None
    return ConsumerWithdrawalRead.model_validate(
        {
            "id": row.id,
            "amount": row.amount,
            "currency": row.currency,
            "status": row.status,
            "reviewed_at": row.reviewed_at,
            "funds_status": ("manual_confirmed" if row.channel == "manual" else "channel_confirmed")
            if confirmed
            else "not_confirmed",
            "confirmed_at": row.confirmed_at if confirmed else None,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
    )


class ConsumerFinanceService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.access = UserAccessService(session)
        self.distribution = DistributionService(session)

    async def member(self, user_id: UUID) -> ConsumerMemberRead:
        await self.access.require_active_user(user_id)
        row = (
            await self.session.execute(
                select(MemberProfile, MemberLevel)
                .outerjoin(MemberLevel, MemberLevel.id == MemberProfile.level_id)
                .where(MemberProfile.user_id == user_id)
            )
        ).one_or_none()
        return member_read(row[0], row[1]) if row is not None else member_read(None, None)

    async def activate(self, user_id: UUID) -> ConsumerMemberRead:
        await self.distribution.activate_profile(user_id)
        return await self.member(user_id)

    async def wallets(self, user_id: UUID) -> list[ConsumerWalletRead]:
        await self.access.require_active_user(user_id)
        wallets = await self.distribution.wallets_for_user(user_id)
        if {wallet.wallet_type for wallet in wallets} != {"commission", "consumption"}:
            raise AppException(status_code=409, code=ErrorCode.STATE_CONFLICT, message="钱包轨道事实不一致")
        return [ConsumerWalletRead.model_validate(wallet) for wallet in wallets]

    async def ledgers(
        self, user_id: UUID, wallet_type: WalletType, page: int, page_size: int
    ) -> PageResult[ConsumerWalletLedgerRead]:
        await self.access.require_active_user(user_id)
        wallet = await self.session.scalar(
            select(WalletAccount).where(WalletAccount.user_id == user_id, WalletAccount.wallet_type == wallet_type)
        )
        if wallet is None:
            raise AppException(
                status_code=404, code=ErrorCode.DISTRIBUTION_PROFILE_NOT_FOUND, message="请先开通会员分销档案"
            )
        stmt = select(WalletLedger).where(WalletLedger.wallet_id == wallet.id)
        total = int(await self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        rows: Sequence[WalletLedger] = (
            await self.session.scalars(
                stmt.order_by(WalletLedger.id.desc()).offset((page - 1) * page_size).limit(page_size)
            )
        ).all()
        return PageResult[ConsumerWalletLedgerRead].create(
            items=[ConsumerWalletLedgerRead.model_validate(row) for row in rows],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def commissions(self, user_id: UUID, page: int, page_size: int) -> PageResult[ConsumerCommissionRead]:
        await self.access.require_active_user(user_id)
        stmt = select(CommissionRecord).where(CommissionRecord.beneficiary_user_id == user_id)
        total = int(await self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        rows = (
            await self.session.scalars(
                stmt.order_by(CommissionRecord.id.desc()).offset((page - 1) * page_size).limit(page_size)
            )
        ).all()
        return PageResult[ConsumerCommissionRead].create(
            items=[ConsumerCommissionRead.model_validate(row) for row in rows],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def withdrawals(self, user_id: UUID, page: int, page_size: int) -> PageResult[ConsumerWithdrawalRead]:
        await self.access.require_active_user(user_id)
        stmt = select(WithdrawalRequest).where(WithdrawalRequest.user_id == user_id)
        total = int(await self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        rows = (
            await self.session.scalars(
                stmt.order_by(WithdrawalRequest.id.desc()).offset((page - 1) * page_size).limit(page_size)
            )
        ).all()
        return PageResult[ConsumerWithdrawalRead].create(
            items=[withdrawal_read(row) for row in rows], total=total, page=page, page_size=page_size
        )
