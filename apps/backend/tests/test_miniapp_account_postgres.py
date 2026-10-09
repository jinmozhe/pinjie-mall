"""Account isolation and explicit-target revocation on isolated PostgreSQL; never migrate."""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.core.exceptions import AppException
from app.core.identifiers import new_uuid7
from app.core.request_metadata import RequestMetadata
from app.db.models import User, UserSession
from app.db.models.distribution import PointsAccount, WalletAccount
from app.services.miniapp_account import MiniappAccountService
from app.services.miniapp_account_schemas import MiniappSessionTargets

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
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
                yield async_sessionmaker(
                    bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
                )
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()


@asynccontextmanager
async def account(factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[MiniappAccountService]:
    async with factory() as session:
        yield MiniappAccountService(
            session=session,
            session_factory=factory,
            metadata=RequestMetadata("account-test", "account-test", None, None, None),
        )


def login(user_id: UUID, *, browser: bool = False, expired: bool = False) -> UserSession:
    now = datetime.now(UTC)
    return UserSession(
        id=new_uuid7(),
        user_id=user_id,
        family_id=new_uuid7(),
        credential_profile="browser_cookie" if browser else "miniapp_bearer",
        client_id="pinjie-web" if browser else "pinjie-miniapp",
        csrf_digest="a" * 64 if browser else None,
        last_seen_at=now,
        idle_expires_at=now + timedelta(hours=-1 if expired else 1),
        absolute_expires_at=now + timedelta(days=1),
        ip_address="192.0.2.123",
    )


async def test_original_targets_owner_profile_and_current_rechecks(factory: async_sessionmaker[AsyncSession]) -> None:
    owner, other = new_uuid7(), new_uuid7()
    current, target, expired = login(owner), login(owner), login(owner, expired=True)
    browser, foreign = login(owner, browser=True), login(other)
    async with factory() as session:
        session.add_all([User(id=owner, username=f"account-{owner}"), User(id=other, username=f"account-{other}")])
        await session.flush()
        session.add_all([current, target, expired, browser, foreign])
        await session.commit()
    async with account(factory) as service:
        page = await service.list_sessions(owner, current.id, 1, 100)
        assert {item.id for item in page.items} == {current.id, target.id, expired.id}
        assert page.other_active_ids == [target.id] and page.other_active_total == 1
        assert next(item for item in page.items if item.id == current.id).is_current
    for forbidden in [current.id, browser.id, foreign.id, new_uuid7()]:
        async with account(factory) as service:
            with pytest.raises(AppException):
                await service.revoke(owner, current.id, 1, MiniappSessionTargets(session_ids=[target.id, forbidden]))
        async with factory() as session:
            unchanged = await session.get(UserSession, target.id)
            assert unchanged is not None and unchanged.revoked_at is None
    original = MiniappSessionTargets(session_ids=[target.id, expired.id])
    async with account(factory) as service:
        result = await service.revoke(owner, current.id, 1, original)
        assert [item.state for item in result.sessions] == ["revoked", "revoked"]
    async with factory() as session:
        revoked = await session.get(UserSession, target.id)
        assert revoked is not None
        first_revoked_at = revoked.revoked_at
        new_login = login(owner)
        session.add(new_login)
        await session.commit()
    async with account(factory) as service:
        await service.revoke(owner, current.id, 1, original)
    async with factory() as session:
        revoked = await session.get(UserSession, target.id)
        untouched = await session.get(UserSession, new_login.id)
        active = await session.get(UserSession, current.id)
        assert revoked is not None and revoked.revoked_at == first_revoked_at
        assert untouched is not None and untouched.revoked_at is None
        assert active is not None and active.revoked_at is None
        active.revoked_at = datetime.now(UTC)
        await session.commit()
    async with account(factory) as service:
        with pytest.raises(AppException):
            await service.revoke(owner, current.id, 1, MiniappSessionTargets(session_ids=[new_login.id]))
    async with account(factory) as service:
        status = await service.revocation_status(
            owner, MiniappSessionTargets(session_ids=[target.id, foreign.id, browser.id])
        )
        assert [item.state for item in status.sessions] == ["revoked", "not_found", "not_found"]
    async with factory() as session:
        untouched = await session.get(UserSession, new_login.id)
        assert untouched is not None and untouched.revoked_at is None


async def test_closure_is_read_only_and_foreign_rights_are_excluded(factory: async_sessionmaker[AsyncSession]) -> None:
    owner, other = new_uuid7(), new_uuid7()
    async with factory() as session:
        session.add_all([User(id=owner, username=f"closure-{owner}"), User(id=other, username=f"closure-{other}")])
        await session.flush()
        session.add_all(
            [
                WalletAccount(user_id=other, wallet_type="commission", available_amount=Decimal("1.00")),
                PointsAccount(user_id=other, available_points=1),
            ]
        )
        await session.commit()
    async with account(factory) as service:
        read = await service.closure_precheck(owner)
        assert read.self_service_enabled is False
        assert read.wallet_state == read.points_state == "not_opened"
        assert len(read.checks) == 8 and not any(item.needs_review for item in read.checks)
    async with factory() as session:
        wallet = WalletAccount(user_id=owner, wallet_type="consumption", debt_amount=Decimal("2.00"))
        points = PointsAccount(user_id=owner, frozen_points=3)
        session.add_all([wallet, points])
        await session.commit()
    async with account(factory) as service:
        read = await service.closure_precheck(owner)
        assert read.self_service_enabled is False
        assert read.wallet_state == read.points_state == "opened"
        flags = {item.key: item.needs_review for item in read.checks}
        assert flags["wallets"] and flags["points"]
        assert not any(value for key, value in flags.items() if key not in ("wallets", "points"))
    async with factory() as session:
        persisted_wallet = await session.get(WalletAccount, wallet.id)
        persisted_points = await session.get(PointsAccount, points.id)
        assert persisted_wallet is not None and persisted_wallet.debt_amount == Decimal("2.00")
        assert persisted_points is not None and persisted_points.frozen_points == 3
