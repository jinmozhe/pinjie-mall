"""Explicit consumer read model; referral writes delegate to their owning domain."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.core.pagination import PageResult
from app.db.models.distribution import MemberProfile, PointsAccount, PointsLedger
from app.domains.distribution import DistributionService, ReferralBindIn
from app.domains.users import UserAccessService
from app.services.engagement_schemas import (
    ConsumerPointsAccountRead,
    ConsumerPointsLedgerRead,
    ConsumerPointsRead,
    ConsumerReferralRead,
)


def referral_read(
    profile: MemberProfile | None, inviter_code: str | None, invitation_code: str | None
) -> ConsumerReferralRead:
    if profile is None:
        return ConsumerReferralRead(
            state="not_opened",
            invitation_code=None,
            bound_at=None,
            matches_invitation=False if invitation_code is not None else None,
        )
    bound = profile.inviter_id is not None
    if bound and (inviter_code is None or profile.bound_at is None):
        raise AppException(status_code=409, code=ErrorCode.STATE_CONFLICT, message="推荐关系事实不一致")
    return ConsumerReferralRead(
        state="bound" if bound else "unbound",
        invitation_code=profile.invitation_code,
        bound_at=profile.bound_at,
        matches_invitation=(bound and inviter_code == invitation_code) if invitation_code is not None else None,
    )


class ConsumerEngagementService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.access = UserAccessService(session)
        self.distribution = DistributionService(session)

    async def referral(self, user_id: UUID, invitation_code: str | None = None) -> ConsumerReferralRead:
        await self.access.require_active_user(user_id)
        inviter = aliased(MemberProfile)
        row = (
            await self.session.execute(
                select(MemberProfile, inviter.invitation_code)
                .outerjoin(inviter, inviter.user_id == MemberProfile.inviter_id)
                .where(MemberProfile.user_id == user_id)
            )
        ).one_or_none()
        return (
            referral_read(row[0], row[1], invitation_code)
            if row is not None
            else referral_read(None, None, invitation_code)
        )

    async def bind(self, user_id: UUID, payload: ReferralBindIn) -> ConsumerReferralRead:
        await self.distribution.bind_referrer(user_id, payload)
        return await self.referral(user_id, payload.invitation_code)

    async def points(self, user_id: UUID) -> ConsumerPointsRead:
        await self.access.require_active_user(user_id)
        account = await self.session.scalar(select(PointsAccount).where(PointsAccount.user_id == user_id))
        return ConsumerPointsRead(
            state="not_opened" if account is None else "opened",
            account=ConsumerPointsAccountRead.model_validate(account) if account is not None else None,
        )

    async def points_ledgers(self, user_id: UUID, page: int, page_size: int) -> PageResult[ConsumerPointsLedgerRead]:
        await self.access.require_active_user(user_id)
        account_id = await self.session.scalar(select(PointsAccount.id).where(PointsAccount.user_id == user_id))
        if account_id is None:
            raise AppException(status_code=404, code=ErrorCode.NOT_FOUND, message="本人积分账户尚未建立")
        stmt = select(PointsLedger).where(PointsLedger.account_id == account_id)
        total = int(await self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        rows = (
            await self.session.scalars(
                stmt.order_by(PointsLedger.id.desc()).offset((page - 1) * page_size).limit(page_size)
            )
        ).all()
        return PageResult[ConsumerPointsLedgerRead].create(
            items=[ConsumerPointsLedgerRead.model_validate(row) for row in rows],
            total=total,
            page=page,
            page_size=page_size,
        )
