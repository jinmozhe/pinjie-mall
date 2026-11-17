"""基础账户事务、历史补齐与资产保护；仅显式授权后执行真实隔离 PostgreSQL。"""

import os
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import Settings
from app.core.exceptions import AppException
from app.core.identifiers import new_uuid7
from app.db.models import User
from app.db.models.distribution import MemberProfile, PointsAccount, WalletAccount
from app.db.transaction import transaction_scope
from app.services.customer_accounts import CustomerAccountsService


@pytest.mark.integration
@pytest.mark.asyncio
async def test_initialization_preserves_existing_assets_and_rolls_back_incomplete_accounts() -> None:
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.fail("Explicit isolated TEST_DATABASE_URL is required")
    settings = Settings(ENVIRONMENT="test", DATABASE_URL=database_url, TEST_DATABASE_URL=database_url)
    settings.validate_database_runtime()
    engine = create_async_engine(database_url, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            outer = await connection.begin()
            try:
                async with AsyncSession(
                    bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
                ) as session:
                    owner, referrer, broken, rolled_back = (new_uuid7() for _ in range(4))
                    async with transaction_scope(session):
                        session.add_all(
                            [User(id=value, username=f"accounts-{value}") for value in (owner, referrer, broken)]
                        )
                        await session.flush()
                        accounts = CustomerAccountsService(session)
                        await accounts.initialize_in_open_transaction(owner)
                        await accounts.initialize_in_open_transaction(referrer)
                        profile = (
                            await session.scalars(select(MemberProfile).where(MemberProfile.user_id == owner))
                        ).one()
                        profile.inviter_id, profile.bound_at = referrer, datetime.now(UTC)
                        wallet = (
                            await session.scalars(
                                select(WalletAccount).where(
                                    WalletAccount.user_id == owner, WalletAccount.wallet_type == "commission"
                                )
                            )
                        ).one()
                        wallet.available_amount, wallet.frozen_amount, wallet.debt_amount, wallet.revision = (
                            Decimal("12.34"),
                            Decimal("5.00"),
                            Decimal("2.00"),
                            4,
                        )
                        points = (
                            await session.scalars(select(PointsAccount).where(PointsAccount.user_id == owner))
                        ).one()
                        points.available_points, points.frozen_points, points.debt_points, points.revision = 23, 4, 2, 7
                        original = profile.id, profile.invitation_code, profile.bound_at, wallet.id, points.id
                        session.add(
                            MemberProfile(
                                id=new_uuid7(),
                                user_id=broken,
                                invitation_code=new_uuid7().hex[-16:].upper(),
                                level_changed_at=datetime.now(UTC),
                                revision=1,
                            )
                        )
                        # 旧账户已有档案与钱包，尚未发生积分业务。
                        await session.execute(delete(PointsAccount).where(PointsAccount.user_id == referrer))
                    async with transaction_scope(session):
                        await CustomerAccountsService(session).initialize_in_open_transaction(referrer)
                        legacy_points = (
                            await session.scalars(select(PointsAccount).where(PointsAccount.user_id == referrer))
                        ).one()
                        assert (
                            legacy_points.available_points
                            == legacy_points.frozen_points
                            == legacy_points.debt_points
                            == 0
                        )
                        await CustomerAccountsService(session).initialize_in_open_transaction(owner)
                        await session.refresh(wallet)
                        await session.refresh(points)
                        assert (profile.id, profile.invitation_code, profile.bound_at, wallet.id, points.id) == original
                        assert profile.inviter_id == referrer
                        assert (wallet.available_amount, wallet.frozen_amount, wallet.debt_amount, wallet.revision) == (
                            Decimal("12.34"),
                            Decimal("5.00"),
                            Decimal("2.00"),
                            4,
                        )
                        assert (points.available_points, points.frozen_points, points.debt_points, points.revision) == (
                            23,
                            4,
                            2,
                            7,
                        )
                    with pytest.raises(AppException, match="会员与钱包账户不完整"):
                        async with transaction_scope(session):
                            await CustomerAccountsService(session).initialize_in_open_transaction(broken)
                    assert (
                        await session.scalar(
                            select(func.count()).select_from(PointsAccount).where(PointsAccount.user_id == broken)
                        )
                        == 0
                    )
                    with pytest.raises(RuntimeError, match="abort registration"):
                        async with transaction_scope(session):
                            session.add(User(id=rolled_back, username=f"accounts-{rolled_back}"))
                            await session.flush()
                            await CustomerAccountsService(session).initialize_in_open_transaction(rolled_back)
                            raise RuntimeError("abort registration")
                    for model in (MemberProfile, WalletAccount, PointsAccount):
                        assert (
                            await session.scalar(
                                select(func.count()).select_from(model).where(model.user_id == rolled_back)
                            )
                            == 0
                        )
                    assert await session.get(User, rolled_back) is None
            finally:
                await outer.rollback()
    finally:
        await engine.dispose()
