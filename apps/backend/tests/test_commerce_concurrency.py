"""真实 PostgreSQL 交易与推荐并发回归；只在专项授权后运行，不自动迁移。"""

import asyncio
import os
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.core.exceptions import AppException
from app.core.identifiers import new_uuid7
from app.db.models import (
    Category,
    InventoryAccount,
    InventoryReservation,
    InventoryReservationEvent,
    MemberLevelEvent,
    MemberProfile,
    MembershipQualificationEvent,
    Order,
    OrderEvent,
    OrderItem,
    PointsAccount,
    PointsLedger,
    Product,
    ProductPurchaseLimit,
    ProductPurchaseRecord,
    ProductSku,
    User,
    WalletAccount,
)
from app.db.transaction import transaction_scope
from app.domains.distribution import DistributionService, ReferralBindIn
from app.domains.membership import PointsManualAdjustment
from app.domains.orders import CheckoutLine, CheckoutRequest
from app.domains.points import PointsService
from app.domains.users import UserAccessService
from app.services.orders import OrderService


@pytest.fixture
async def commerce_database():
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.fail("TEST_DATABASE_URL is required for commerce concurrency tests")
    settings = Settings(_env_file=None, ENVIRONMENT="test", DATABASE_URL=database_url, TEST_DATABASE_URL=database_url)
    settings.validate_database_runtime()
    engine = create_async_engine(database_url, connect_args={"server_settings": {"lock_timeout": "5000ms"}})
    factory = async_sessionmaker(engine, expire_on_commit=False)
    users = [new_uuid7() for _ in range(3)]
    category_id, product_id, sku_id = (new_uuid7() for _ in range(3))
    try:
        async with factory() as session, transaction_scope(session):
            session.add_all(
                [
                    User(
                        id=user_id,
                        username=f"boundary-{user_id.hex}",
                        password_hash="test-only-unused-hash",
                        is_active=True,
                    )
                    for user_id in users
                ]
            )
            session.add(Category(id=category_id, name="边界回归", is_active=True))
            await session.flush()
            session.add(
                Product(
                    id=product_id,
                    category_id=category_id,
                    name="虚拟商品",
                    product_type="virtual",
                    status="on_sale",
                    revision=1,
                )
            )
            await session.flush()
            session.add(
                ProductSku(
                    id=sku_id,
                    product_id=product_id,
                    code=f"BOUNDARY-{sku_id.hex}",
                    sku_no=0,
                    specification_key="default",
                    specifications={},
                    price=Decimal("1.00"),
                    wholesale_prices=[],
                    weight_grams=0,
                    is_active=True,
                )
            )
            await session.flush()
            session.add(InventoryAccount(sku_id=sku_id, available=10, reserved=0, revision=1))
        yield SimpleNamespace(factory=factory, users=users, sku_id=sku_id)
    finally:
        try:
            async with factory() as session, transaction_scope(session):
                order_ids = select(Order.id).where(Order.user_id.in_(users))
                reservation_ids = select(InventoryReservation.id).where(InventoryReservation.order_id.in_(order_ids))
                await session.execute(
                    delete(InventoryReservationEvent).where(
                        InventoryReservationEvent.reservation_id.in_(reservation_ids)
                    )
                )
                await session.execute(delete(InventoryReservation).where(InventoryReservation.order_id.in_(order_ids)))
                await session.execute(delete(OrderEvent).where(OrderEvent.order_id.in_(order_ids)))
                await session.execute(delete(OrderItem).where(OrderItem.order_id.in_(order_ids)))
                await session.execute(
                    delete(ProductPurchaseRecord).where(ProductPurchaseRecord.order_id.in_(order_ids))
                )
                await session.execute(delete(ProductPurchaseLimit).where(ProductPurchaseLimit.product_id == product_id))
                await session.execute(delete(Order).where(Order.user_id.in_(users)))
                await session.execute(delete(WalletAccount).where(WalletAccount.user_id.in_(users)))
                await session.execute(delete(MemberLevelEvent).where(MemberLevelEvent.user_id.in_(users)))
                await session.execute(
                    delete(MembershipQualificationEvent).where(MembershipQualificationEvent.user_id.in_(users))
                )
                points_accounts = select(PointsAccount.id).where(PointsAccount.user_id.in_(users))
                await session.execute(delete(PointsLedger).where(PointsLedger.account_id.in_(points_accounts)))
                await session.execute(delete(PointsAccount).where(PointsAccount.user_id.in_(users)))
                await session.execute(delete(MemberProfile).where(MemberProfile.user_id.in_(users)))
                await session.execute(delete(InventoryAccount).where(InventoryAccount.sku_id == sku_id))
                await session.execute(delete(ProductSku).where(ProductSku.id == sku_id))
                await session.execute(delete(Product).where(Product.id == product_id))
                await session.execute(delete(Category).where(Category.id == category_id))
                await session.execute(delete(User).where(User.id.in_(users)))
        finally:
            await engine.dispose()


@pytest.mark.integration
async def test_detail_binding_lock_precedes_asset_deletion_check(commerce_database):
    """Independent PostgreSQL connections verify the common asset lock protocol."""
    from app.db.models import Asset, ProductDetailImage
    from app.db.repositories.asset import AssetRepository
    from app.db.repositories.commerce_access import CommerceAccessRepository

    fixture = commerce_database
    asset_id = new_uuid7()
    reader_started = asyncio.Event()

    async def deletion_guard():
        async with fixture.factory() as session, transaction_scope(session):
            reader_started.set()
            asset = await AssetRepository(session).get(asset_id, for_update=True)
            assert asset is not None
            return await CommerceAccessRepository(session).asset_is_product_image(asset_id)

    task = None
    try:
        async with fixture.factory() as session, transaction_scope(session):
            product_id = await session.scalar(select(ProductSku.product_id).where(ProductSku.id == fixture.sku_id))
            session.add(
                Asset(
                    id=asset_id,
                    uploader_type="system",
                    uploader_id=None,
                    storage_driver="local",
                    file_key=f"product/{asset_id}.png",
                    original_name="detail.png",
                    mime_type="image/png",
                    file_size=100,
                    file_hash=asset_id.hex * 2,
                    url=f"/static/uploads/product/{asset_id}.png",
                    scene="product",
                    width=750,
                    height=1000,
                    frame_count=1,
                )
            )
        async with fixture.factory() as writer, transaction_scope(writer):
            await CommerceAccessRepository(writer).get_images_for_update([asset_id])
            writer.add(ProductDetailImage(product_id=product_id, asset_id=asset_id, position=0))
            await writer.flush()
            task = asyncio.create_task(deletion_guard())
            await asyncio.wait_for(reader_started.wait(), timeout=5)
            # It must not observe "unreferenced" while the binding transaction is uncommitted.
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(asyncio.shield(task), timeout=0.1)
        assert await asyncio.wait_for(task, timeout=5) is True
    finally:
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        async with fixture.factory() as session, transaction_scope(session):
            await session.execute(delete(ProductDetailImage).where(ProductDetailImage.asset_id == asset_id))
            await session.execute(delete(Asset).where(Asset.id == asset_id))


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize("shared_key", [True, False])
async def test_concurrent_first_points_adjustments_preserve_idempotency_and_account(commerce_database, shared_key):
    fixture = commerce_database
    user_id, actor_id = fixture.users[:2]
    async with fixture.factory() as session, transaction_scope(session):
        session.add(
            MemberProfile(
                user_id=user_id,
                invitation_code=new_uuid7().hex[-16:],
                level_changed_at=datetime.now(UTC),
                revision=1,
            )
        )

    class TransactionAudit:
        """权限不属于本用例目标；保留真实事务、仓储和会员贡献链。"""

        def __init__(self, session):
            self.session = session

        async def execute(self, *, operation, **metadata):
            async with transaction_scope(self.session):
                return await operation()

    gate = asyncio.Event()
    first_key = f"concurrent-points:{new_uuid7()}"
    second_key = first_key if shared_key else f"concurrent-points:{new_uuid7()}"

    async def adjust(key):
        async with fixture.factory() as session:
            service = PointsService(session=session, actor_id=actor_id, audit=TransactionAudit(session))
            await gate.wait()
            return await service.adjust(
                PointsManualAdjustment(user_id=user_id, points=7, operation="grant", idempotency_key=key)
            )

    tasks = [asyncio.create_task(adjust(key)) for key in (first_key, second_key)]
    gate.set()
    results = await asyncio.wait_for(asyncio.gather(*tasks), timeout=20)
    assert results[0].id == results[1].id
    expected_entries = 1 if shared_key else 2
    async with fixture.factory() as session:
        account = (await session.scalars(select(PointsAccount).where(PointsAccount.user_id == user_id))).one()
        assert account.available_points == 7 * expected_entries
        assert account.revision == 1 + expected_entries
        assert (
            await session.scalar(
                select(func.count()).select_from(PointsLedger).where(PointsLedger.account_id == account.id)
            )
            == expected_entries
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(MembershipQualificationEvent)
                .where(MembershipQualificationEvent.user_id == user_id, MembershipQualificationEvent.metric == "points")
            )
            == expected_entries
        )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_concurrent_checkout_cannot_oversell_and_cancel_releases_once(commerce_database):
    fixture = commerce_database
    request = CheckoutRequest(request_id=new_uuid7(), items=[CheckoutLine(sku_id=fixture.sku_id, quantity=7)])
    async with fixture.factory() as session:
        quote = await OrderService(session).preview(fixture.users[0], request)
    gate = asyncio.Event()

    async def create(user_id):
        async with fixture.factory() as session:
            await gate.wait()
            return user_id, await OrderService(session).create(
                user_id, request.model_copy(update={"quote_fingerprint": quote.fingerprint})
            )

    tasks = [asyncio.create_task(create(user_id)) for user_id in fixture.users[:2]]
    gate.set()
    results = await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=20)
    successes = [result for result in results if isinstance(result, tuple)]
    failures = [result for result in results if isinstance(result, AppException)]
    assert len(successes) == 1 and len(failures) == 1
    assert failures[0].code == "ORDER_STOCK_REJECTED"
    user_id, order = successes[0]
    async with fixture.factory() as session:
        service = OrderService(session)
        await service.cancel(user_id, order.id)
        await service.cancel(user_id, order.id)
        account = await session.scalar(select(InventoryAccount).where(InventoryAccount.sku_id == fixture.sku_id))
        assert (account.available, account.reserved, account.revision) == (10, 0, 3)
        events = list(
            await session.scalars(
                select(InventoryReservationEvent)
                .join(InventoryReservation, InventoryReservationEvent.reservation_id == InventoryReservation.id)
                .where(InventoryReservation.order_id == order.id)
                .order_by(InventoryReservationEvent.revision)
            )
        )
        assert [event.to_status for event in events] == ["reserved", "released"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_user_status_lock_allows_unrelated_foreign_key_writes(commerce_database):
    fixture = commerce_database

    async def write_wallet():
        async with fixture.factory() as session, transaction_scope(session):
            session.add(
                WalletAccount(
                    id=new_uuid7(),
                    user_id=fixture.users[0],
                    wallet_type="commission",
                    available_amount=Decimal("0"),
                    frozen_amount=Decimal("0"),
                    debt_amount=Decimal("0"),
                    revision=1,
                )
            )
            await session.flush()

    async with fixture.factory() as session, transaction_scope(session):
        await UserAccessService(session).require_active_user(fixture.users[0])
        await asyncio.wait_for(write_wallet(), timeout=10)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_concurrent_profile_activation_is_idempotent(commerce_database):
    fixture = commerce_database

    async def activate():
        async with fixture.factory() as session:
            return await DistributionService(session).activate_profile(fixture.users[0])

    first, second = await asyncio.wait_for(asyncio.gather(activate(), activate()), timeout=20)
    assert first.invitation_code == second.invitation_code
    async with fixture.factory() as session:
        wallets = list(await session.scalars(select(WalletAccount).where(WalletAccount.user_id == fixture.users[0])))
        assert sorted(wallet.wallet_type for wallet in wallets) == ["commission", "consumption"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_three_concurrent_referrals_cannot_form_a_cycle(commerce_database):
    fixture = commerce_database
    profiles = []
    for user_id in fixture.users:
        async with fixture.factory() as session:
            profiles.append(await DistributionService(session).activate_profile(user_id))

    async def bind(index):
        async with fixture.factory() as session:
            return await DistributionService(session).bind_referrer(
                fixture.users[index], ReferralBindIn(invitation_code=profiles[(index + 1) % 3].invitation_code)
            )

    results = await asyncio.wait_for(
        asyncio.gather(*(bind(index) for index in range(3)), return_exceptions=True), timeout=20
    )
    failures = [result for result in results if isinstance(result, AppException)]
    assert len(failures) == 1 and failures[0].code == "DISTRIBUTION_REFERRAL_REJECTED"
    assert sum(not isinstance(result, BaseException) for result in results) == 2
    async with fixture.factory() as session:
        rows = list(await session.scalars(select(MemberProfile).where(MemberProfile.user_id.in_(fixture.users))))
        parents = {row.user_id: row.inviter_id for row in rows}
        for user_id in fixture.users:
            visited = set()
            while user_id is not None:
                assert user_id not in visited
                visited.add(user_id)
                user_id = parents[user_id]
