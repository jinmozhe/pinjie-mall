"""Account security application use cases and explicit read-only closure observations."""

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.core.privacy import masked_ip
from app.core.request_metadata import RequestMetadata
from app.db.models import UserSession
from app.db.models.commerce_lifecycle import Fulfillment, PaymentAttempt, RefundAttempt, RefundRequest
from app.db.models.distribution import CommissionRecord, PointsAccount, WalletAccount, WithdrawalRequest
from app.db.models.order import Order
from app.db.repositories import SecurityRepository, SessionRepository, UserRepository
from app.db.repositories.miniapp_sessions import MiniappSessionRepository
from app.domains.users import UserAccessService
from app.services.miniapp_account_schemas import (
    ClosureCheckKey,
    MiniappClosureCheckRead,
    MiniappClosurePrecheckRead,
    MiniappLoginSessionRead,
    MiniappLoginSessionsRead,
    MiniappSessionRevocationRead,
    MiniappSessionStateRead,
    MiniappSessionTargets,
)
from app.services.miniapp_auth import bearer_error
from app.services.security_events import AuditCoordinator, login_event


def login_session_read(row: UserSession, current_id: UUID, now: datetime) -> MiniappLoginSessionRead:
    state: Literal["active", "expired", "revoked"] = (
        "revoked"
        if row.revoked_at is not None
        else "expired"
        if min(row.idle_expires_at, row.absolute_expires_at) <= now
        else "active"
    )
    return MiniappLoginSessionRead(
        id=row.id,
        device_name=row.device_name,
        ip_masked=masked_ip(row.ip_address),
        created_at=row.created_at,
        last_seen_at=row.last_seen_at,
        idle_expires_at=row.idle_expires_at,
        absolute_expires_at=row.absolute_expires_at,
        revoked_at=row.revoked_at,
        is_current=row.id == current_id,
        state=state,
    )


class MiniappAccountService:
    def __init__(
        self, *, session: AsyncSession, session_factory: async_sessionmaker[AsyncSession], metadata: RequestMetadata
    ) -> None:
        self.session = session
        self.session_factory = session_factory
        self.metadata = metadata
        self.sessions = MiniappSessionRepository(session)
        self.access = UserAccessService(session)

    async def list_sessions(
        self, user_id: UUID, current_id: UUID, page: int, page_size: int
    ) -> MiniappLoginSessionsRead:
        await self.access.require_active_user(user_id)
        now = datetime.now(UTC)
        rows, total = await self.sessions.page(user_id, page, page_size)
        ids, other_total = await self.sessions.active_others(user_id, current_id, now)
        return MiniappLoginSessionsRead(
            items=[login_session_read(row, current_id, now) for row in rows],
            page=page,
            page_size=page_size,
            total=total,
            total_pages=(total + page_size - 1) // page_size,
            other_active_total=other_total,
            other_active_ids=ids,
        )

    async def revocation_status(self, user_id: UUID, payload: MiniappSessionTargets) -> MiniappSessionRevocationRead:
        await self.access.require_active_user(user_id)
        rows = {row.id: row for row in await self.sessions.targets(user_id, payload.session_ids)}
        now = datetime.now(UTC)
        return MiniappSessionRevocationRead(
            sessions=[
                MiniappSessionStateRead(
                    id=target,
                    state=login_session_read(rows[target], target, now).state if target in rows else "not_found",
                )
                for target in payload.session_ids
            ]
        )

    async def revoke(
        self, user_id: UUID, current_id: UUID, credential_version: int, payload: MiniappSessionTargets
    ) -> MiniappSessionRevocationRead:
        if current_id in payload.session_ids:
            raise AppException(
                status_code=409, code=ErrorCode.STATE_CONFLICT, message="当前会话请使用退出登录，不可在此撤销"
            )

        async def operation() -> MiniappSessionRevocationRead:
            # Login and other account writes use the same user lock. No refresh-token locks are taken:
            # Refresh locks token -> session, and already rejects a revoked parent session.
            user = await UserRepository(self.session).get(user_id, for_update=True)
            if user is None or not user.is_active or user.deleted_at is not None:
                raise AppException(status_code=403, code=ErrorCode.AUTH_ACCOUNT_DISABLED, message="账户已停用")
            current = await SessionRepository(self.session).get_web(current_id, for_update=True)
            now = datetime.now(UTC)
            if (
                current is None
                or current.user_id != user_id
                or current.credential_profile != "miniapp_bearer"
                or current.client_id != "pinjie-miniapp"
                or current.csrf_digest is not None
                or current.revoked_at is not None
                or user.credential_version != credential_version
                or min(current.idle_expires_at, current.absolute_expires_at) <= now
            ):
                raise bearer_error(ErrorCode.AUTH_SESSION_REVOKED)
            rows = await self.sessions.targets(user_id, payload.session_ids, for_update=True)
            if {row.id for row in rows} != set(payload.session_ids):
                raise AppException(
                    status_code=404, code=ErrorCode.NOT_FOUND, message="目标会话不存在或不属于本人小程序"
                )
            for row in rows:
                if row.revoked_at is None:
                    row.revoked_at, row.revoke_reason = now, "miniapp_user_revoked"
            SecurityRepository(self.session).add_login_event(
                login_event(
                    principal_type="user",
                    principal_id=user_id,
                    identifier_digest=None,
                    event_type="miniapp_sessions_revoke",
                    succeeded=True,
                    reason_code="SESSIONS_REVOKED",
                    metadata=self.metadata,
                    now=now,
                )
            )
            return MiniappSessionRevocationRead(
                sessions=[MiniappSessionStateRead(id=target, state="revoked") for target in payload.session_ids]
            )

        return await AuditCoordinator(
            session=self.session, session_factory=self.session_factory, actor_id=user_id, metadata=self.metadata
        ).execute(
            action="miniapp.sessions.revoke",
            target_type="user_session",
            target_id=payload.session_ids[0] if len(payload.session_ids) == 1 else None,
            actor_type="user",
            changed_fields={"session_ids": [str(target) for target in payload.session_ids]},
            operation=operation,
        )

    async def closure_precheck(self, user_id: UUID) -> MiniappClosurePrecheckRead:
        await self.access.require_active_user(user_id)
        # A single SELECT observes all source tables in one PostgreSQL statement snapshot.
        # These are consultation flags, never an authorization to delete or waive rights.
        observations = {
            "orders": select(Order.id)
            .outerjoin(Fulfillment, Fulfillment.order_id == Order.id)
            .where(
                Order.user_id == user_id,
                or_(
                    Order.status == "pending_payment",
                    (Order.status == "paid")
                    & or_(Fulfillment.id.is_(None), Fulfillment.status.not_in(("delivered", "cancelled"))),
                ),
            )
            .exists(),
            "payments": select(PaymentAttempt.id)
            .where(PaymentAttempt.user_id == user_id, PaymentAttempt.status.in_(("created", "pending", "unknown")))
            .exists(),
            "refunds": select(RefundRequest.id)
            .where(RefundRequest.user_id == user_id, RefundRequest.status.in_(("requested", "approved")))
            .exists(),
            "refund_execution": select(RefundAttempt.id)
            .join(Order, Order.id == RefundAttempt.order_id)
            .where(
                Order.user_id == user_id,
                or_(
                    RefundAttempt.status.not_in(("succeeded", "closed")),
                    (RefundAttempt.status == "succeeded") & RefundAttempt.confirmed_at.is_(None),
                ),
            )
            .exists(),
            "withdrawals": select(WithdrawalRequest.id)
            .where(
                WithdrawalRequest.user_id == user_id,
                or_(
                    WithdrawalRequest.status.not_in(("succeeded", "rejected")),
                    (WithdrawalRequest.status == "succeeded") & WithdrawalRequest.confirmed_at.is_(None),
                ),
            )
            .exists(),
            "commissions": select(CommissionRecord.id)
            .where(CommissionRecord.beneficiary_user_id == user_id, CommissionRecord.status == "frozen")
            .exists(),
            "wallets": select(WalletAccount.id)
            .where(
                WalletAccount.user_id == user_id,
                or_(
                    WalletAccount.available_amount != 0,
                    WalletAccount.frozen_amount != 0,
                    WalletAccount.debt_amount != 0,
                ),
            )
            .exists(),
            "points": select(PointsAccount.id)
            .where(
                PointsAccount.user_id == user_id,
                or_(
                    PointsAccount.available_points != 0,
                    PointsAccount.frozen_points != 0,
                    PointsAccount.debt_points != 0,
                ),
            )
            .exists(),
            "wallet_opened": select(WalletAccount.id).where(WalletAccount.user_id == user_id).exists(),
            "points_opened": select(PointsAccount.id).where(PointsAccount.user_id == user_id).exists(),
        }
        facts = (
            (await self.session.execute(select(*(value.label(key) for key, value in observations.items()))))
            .one()
            ._mapping
        )
        keys: tuple[ClosureCheckKey, ...] = (
            "orders",
            "payments",
            "refunds",
            "refund_execution",
            "withdrawals",
            "commissions",
            "wallets",
            "points",
        )
        return MiniappClosurePrecheckRead(
            checked_at=datetime.now(UTC),
            wallet_state="opened" if facts["wallet_opened"] else "not_opened",
            points_state="opened" if facts["points_opened"] else "not_opened",
            checks=[MiniappClosureCheckRead(key=key, needs_review=facts[key]) for key in keys],
        )
