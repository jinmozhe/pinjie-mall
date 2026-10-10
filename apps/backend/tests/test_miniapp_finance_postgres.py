"""Real PostgreSQL ownership and profile writes; isolated URL required, no auto-migration."""

import os
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import Settings
from app.core.exceptions import AppException
from app.core.identifiers import new_uuid7
from app.db.models import Asset, User
from app.db.models.distribution import WalletAccount, WalletLedger, WithdrawalRequest
from app.domains.users.schemas import UserAvatarUpdateIn, UserUpdateIn
from app.services.accounts import UserProfileService
from app.services.finance_queries import ConsumerFinanceService


@pytest.mark.integration
@pytest.mark.asyncio
async def test_personal_wallet_history_and_avatar_ownership() -> None:
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
                # Write services commit savepoints; the external transaction always rolls back fixtures.
                async with AsyncSession(
                    bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
                ) as session:
                    owner, other = new_uuid7(), new_uuid7()
                    session.add_all(
                        [User(id=owner, username=f"finance-{owner}"), User(id=other, username=f"finance-{other}")]
                    )
                    await session.commit()
                    query = ConsumerFinanceService(session)
                    assert (await query.member(owner)).state == "not_opened"
                    assert (await query.activate(owner)).state == "no_level"
                    assert (await query.activate(owner)).state == "no_level"
                    await query.activate(other)
                    wallets = await query.wallets(owner)
                    assert {row.wallet_type for row in wallets} == {"commission", "consumption"}
                    wallet_rows = (
                        await session.scalars(select(WalletAccount).where(WalletAccount.user_id.in_([owner, other])))
                    ).all()
                    ledgers, withdrawals = [], []
                    for wallet in wallet_rows:
                        count = 2 if wallet.user_id == owner and wallet.wallet_type == "commission" else 1
                        for index in range(count):
                            ledger = WalletLedger(
                                id=new_uuid7(),
                                wallet_id=wallet.id,
                                entry_type="commission_settlement",
                                amount=Decimal("1.00"),
                                frozen_delta=Decimal("0"),
                                debt_delta=Decimal("0"),
                                idempotency_key=f"unit-{new_uuid7()}",
                                reference_type="unit",
                                reference_id=new_uuid7(),
                                wallet_revision=index + 2,
                                balance_after={"available_amount": "1.00", "frozen_amount": "0", "debt_amount": "0"},
                            )
                            session.add(ledger)
                            if wallet.user_id == owner and wallet.wallet_type == "commission":
                                ledgers.append(ledger.id)
                        if wallet.wallet_type == "commission":
                            row = WithdrawalRequest(
                                id=new_uuid7(),
                                user_id=wallet.user_id,
                                wallet_id=wallet.id,
                                request_id=new_uuid7(),
                                request_hash="a" * 64,
                                merchant_reference=f"unit-{new_uuid7()}",
                                channel="manual",
                                channel_context={},
                                amount=Decimal("1.00"),
                                currency="CNY",
                                destination_reference="private",
                                status="approved",
                                revision=1,
                            )
                            session.add(row)
                            withdrawals.append(row)
                    foreign_avatar = Asset(
                        id=new_uuid7(),
                        uploader_type="user",
                        uploader_id=other,
                        storage_driver="local",
                        file_key=f"avatar/{new_uuid7()}.png",
                        original_name="avatar.png",
                        mime_type="image/png",
                        file_size=32,
                        file_hash="a" * 64,
                        url=settings.upload_base_url + "/avatar.png",
                        scene="avatar",
                    )
                    session.add(foreign_avatar)
                    own_assets = []
                    for scene in ["avatar", "product"]:
                        asset = Asset(
                            id=new_uuid7(),
                            uploader_type="user",
                            uploader_id=owner,
                            storage_driver="local",
                            file_key=f"{scene}/{new_uuid7()}.png",
                            original_name="image.png",
                            mime_type="image/png",
                            file_size=32,
                            file_hash="b" * 64,
                            url=settings.upload_base_url + f"/{scene}.png",
                            scene=scene,
                        )
                        session.add(asset)
                        own_assets.append(asset.id)
                    await session.commit()
                    first = await query.ledgers(owner, "commission", 1, 1)
                    second = await query.ledgers(owner, "commission", 2, 1)
                    assert first.total == 2 and first.total_pages == 2
                    assert {first.items[0].id, second.items[0].id} == set(ledgers)
                    assert (await query.ledgers(owner, "consumption", 1, 10)).total == 1
                    history = await query.withdrawals(owner, 1, 10)
                    assert history.total == 1 and history.items[0].id == next(
                        row.id for row in withdrawals if row.user_id == owner
                    )
                    assert history.items[0].funds_status == "not_confirmed"
                    profile = UserProfileService(session=session, settings=settings)
                    with pytest.raises(AppException) as forbidden:
                        await profile.update_avatar(owner, UserAvatarUpdateIn(asset_id=foreign_avatar.id))
                    assert forbidden.value.status_code == 403
                    with pytest.raises(AppException) as wrong_scene:
                        await profile.update_avatar(owner, UserAvatarUpdateIn(asset_id=own_assets[1]))
                    assert wrong_scene.value.status_code == 403
                    user = await profile.update_avatar(owner, UserAvatarUpdateIn(asset_id=own_assets[0]))
                    assert user.avatar == settings.upload_base_url + "/avatar.png"
                    assert (await profile.update_avatar(owner, UserAvatarUpdateIn(asset_id=None))).avatar is None
                    user = await profile.update_profile(owner, UserUpdateIn(display_name=" new name "))
                    assert user.display_name == "new name"
                    user.is_active = False
                    await session.commit()
                    with pytest.raises(AppException) as disabled:
                        await profile.update_profile(owner, UserUpdateIn(display_name="blocked"))
                    assert disabled.value.status_code == 403
                    with pytest.raises(AppException):
                        await query.wallets(owner)
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()
