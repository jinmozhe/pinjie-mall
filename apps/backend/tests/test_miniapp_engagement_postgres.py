"""Owner isolation and immutable binding on real PostgreSQL; never auto-migrate."""

import os

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import Settings
from app.core.exceptions import AppException
from app.core.identifiers import new_uuid7
from app.db.models import User
from app.db.models.distribution import PointsAccount, PointsLedger
from app.domains.distribution import DistributionService, ReferralBindIn
from app.services.engagement import ConsumerEngagementService


@pytest.mark.integration
@pytest.mark.asyncio
async def test_referral_idempotence_and_personal_points_pagination() -> None:
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.fail("Explicit isolated TEST_DATABASE_URL is required")
    settings = Settings(ENVIRONMENT="test", DATABASE_URL=database_url, TEST_DATABASE_URL=database_url)
    settings.validate_database_runtime()
    engine = create_async_engine(database_url, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                async with AsyncSession(
                    bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
                ) as session:
                    owner, inviter, other = new_uuid7(), new_uuid7(), new_uuid7()
                    users = [User(id=uid, username=f"engagement-{uid}") for uid in [owner, inviter, other]]
                    session.add_all(users)
                    await session.commit()
                    query = ConsumerEngagementService(session)
                    distribution = DistributionService(session)
                    assert (await query.referral(owner)).state == "not_opened"
                    assert (await query.points(owner)).account is None
                    with pytest.raises(AppException) as missing:
                        await query.points_ledgers(owner, 1, 10)
                    assert missing.value.status_code == 404
                    inviter_profile = await distribution.activate_profile(inviter)
                    other_profile = await distribution.activate_profile(other)
                    payload = ReferralBindIn(invitation_code=inviter_profile.invitation_code.lower())
                    bound = await query.bind(owner, payload)
                    assert bound.state == "bound" and bound.matches_invitation is True
                    assert (await query.bind(owner, payload)).bound_at == bound.bound_at
                    assert (await query.referral(owner, other_profile.invitation_code)).matches_invitation is False
                    for user_id, code in [
                        (owner, other_profile.invitation_code),
                        (owner, bound.invitation_code),
                        (inviter, bound.invitation_code),
                        (other, "INVALIDCODE"),
                    ]:
                        assert code is not None
                        with pytest.raises(AppException):
                            await query.bind(user_id, ReferralBindIn(invitation_code=code))
                    own_account, foreign_account = new_uuid7(), new_uuid7()
                    session.add_all(
                        [
                            PointsAccount(id=own_account, user_id=owner, available_points=9_007_199_254_740_993),
                            PointsAccount(id=foreign_account, user_id=other, available_points=1),
                        ]
                    )
                    await session.flush()
                    own_ids = []
                    for account_id in [own_account, own_account, foreign_account]:
                        identifier = new_uuid7()
                        session.add(
                            PointsLedger(
                                id=identifier,
                                account_id=account_id,
                                entry_type="grant",
                                available_delta=1,
                                frozen_delta=0,
                                debt_delta=0,
                                source_type="manual",
                                source_id=new_uuid7(),
                                idempotency_key=f"engagement-{identifier}",
                                note="private",
                            )
                        )
                        if account_id == own_account:
                            own_ids.append(identifier)
                    await session.commit()
                    read = await query.points(owner)
                    assert read.account is not None
                    assert read.account.model_dump(mode="json")["available_points"] == "9007199254740993"
                    first, second = await query.points_ledgers(owner, 1, 1), await query.points_ledgers(owner, 2, 1)
                    assert first.total == 2 and first.total_pages == 2
                    assert [first.items[0].id, second.items[0].id] == list(reversed(own_ids))
                    assert (await query.points_ledgers(owner, 3, 1)).items == []
                    users[0].is_active = False
                    await session.commit()
                    with pytest.raises(AppException):
                        await query.points(owner)
                    with pytest.raises(AppException):
                        await query.referral(owner)
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()
