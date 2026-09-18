from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.distribution import (
    CommissionRecord,
    CommissionRecovery,
    MemberProfile,
    WalletAccount,
    WalletLedger,
    WithdrawalRequest,
)


class DistributionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def lock_referral_graph(self) -> None:
        await self.session.execute(text("SELECT pg_advisory_xact_lock(722341902)"))

    async def lock_wallets(self, user_ids: list[UUID]) -> None:
        if user_ids:
            await self.session.scalars(
                select(WalletAccount)
                .where(WalletAccount.user_id.in_(user_ids), WalletAccount.wallet_type == "commission")
                .order_by(WalletAccount.user_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )

    async def profile(self, user_id: UUID, *, lock: bool = False) -> MemberProfile | None:
        statement = select(MemberProfile).where(MemberProfile.user_id == user_id)
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return (await self.session.scalars(statement)).one_or_none()

    async def profile_by_code(self, invitation_code: str, *, lock: bool = False) -> MemberProfile | None:
        statement = select(MemberProfile).where(MemberProfile.invitation_code == invitation_code)
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return (await self.session.scalars(statement)).one_or_none()

    async def lock_profiles(self, user_ids: list[UUID]) -> list[MemberProfile]:
        if not user_ids:
            return []
        statement = (
            select(MemberProfile)
            .where(MemberProfile.user_id.in_(user_ids))
            .order_by(MemberProfile.user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return list(await self.session.scalars(statement))

    async def wallet(self, user_id: UUID, wallet_type: str, *, lock: bool = False) -> WalletAccount | None:
        statement = select(WalletAccount).where(
            WalletAccount.user_id == user_id,
            WalletAccount.wallet_type == wallet_type,
        )
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return (await self.session.scalars(statement)).one_or_none()

    async def wallets(self, user_id: UUID) -> list[WalletAccount]:
        return list(
            await self.session.scalars(
                select(WalletAccount).where(WalletAccount.user_id == user_id).order_by(WalletAccount.wallet_type)
            )
        )

    async def commission(self, commission_id: UUID, *, lock: bool = False) -> CommissionRecord | None:
        statement = select(CommissionRecord).where(CommissionRecord.id == commission_id)
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return (await self.session.scalars(statement)).one_or_none()

    async def commissions_for_order(self, order_id: UUID, *, lock: bool = False) -> list[CommissionRecord]:
        statement = select(CommissionRecord).where(CommissionRecord.order_id == order_id).order_by(CommissionRecord.id)
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return list(await self.session.scalars(statement))

    async def commissions_for_user(
        self, user_id: UUID, page: int, page_size: int
    ) -> tuple[list[CommissionRecord], int]:
        filter_clause = CommissionRecord.beneficiary_user_id == user_id
        total = await self.session.scalar(select(func.count()).select_from(CommissionRecord).where(filter_clause))
        rows = await self.session.scalars(
            select(CommissionRecord)
            .where(filter_clause)
            .order_by(CommissionRecord.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(rows), int(total or 0)

    async def count_due_commissions(self, now: datetime) -> int:
        value = await self.session.scalar(
            select(func.count())
            .select_from(CommissionRecord)
            .where(
                CommissionRecord.status == "frozen",
                CommissionRecord.settle_after.is_not(None),
                CommissionRecord.settle_after <= now,
            )
        )
        return int(value or 0)

    async def due_commissions(self, now: datetime, limit: int) -> list[CommissionRecord]:
        statement = (
            select(CommissionRecord)
            .where(
                CommissionRecord.status == "frozen",
                CommissionRecord.settle_after.is_not(None),
                CommissionRecord.settle_after <= now,
            )
            .order_by(CommissionRecord.settle_after, CommissionRecord.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
            .execution_options(populate_existing=True)
        )
        return list(await self.session.scalars(statement))

    async def recovery(self, commission_id: UUID, refund_request_id: UUID) -> CommissionRecovery | None:
        return (
            await self.session.scalars(
                select(CommissionRecovery).where(
                    CommissionRecovery.commission_id == commission_id,
                    CommissionRecovery.refund_request_id == refund_request_id,
                )
            )
        ).one_or_none()

    async def withdrawal_by_request(
        self, user_id: UUID, request_id: UUID, *, lock: bool = False
    ) -> WithdrawalRequest | None:
        statement = select(WithdrawalRequest).where(
            WithdrawalRequest.user_id == user_id,
            WithdrawalRequest.request_id == request_id,
        )
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return (await self.session.scalars(statement)).one_or_none()

    async def withdrawal(self, withdrawal_id: UUID, *, lock: bool = False) -> WithdrawalRequest | None:
        statement = select(WithdrawalRequest).where(WithdrawalRequest.id == withdrawal_id)
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return (await self.session.scalars(statement)).one_or_none()

    async def withdrawals_for_user(
        self, user_id: UUID, page: int, page_size: int
    ) -> tuple[list[WithdrawalRequest], int]:
        filter_clause = WithdrawalRequest.user_id == user_id
        total = await self.session.scalar(select(func.count()).select_from(WithdrawalRequest).where(filter_clause))
        rows = await self.session.scalars(
            select(WithdrawalRequest)
            .where(filter_clause)
            .order_by(WithdrawalRequest.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(rows), int(total or 0)

    async def pending_withdrawals(self, page: int, page_size: int) -> tuple[list[WithdrawalRequest], int]:
        total = await self.session.scalar(
            select(func.count()).select_from(WithdrawalRequest).where(WithdrawalRequest.status == "requested")
        )
        rows = await self.session.scalars(
            select(WithdrawalRequest)
            .where(WithdrawalRequest.status == "requested")
            .order_by(WithdrawalRequest.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(rows), int(total or 0)

    async def save(
        self,
        value: MemberProfile | WalletAccount | CommissionRecord | CommissionRecovery | WalletLedger | WithdrawalRequest,
    ) -> None:
        self.session.add(value)
        await self.session.flush()
