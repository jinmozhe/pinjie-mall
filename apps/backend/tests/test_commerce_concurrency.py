"""真实 PostgreSQL 交易与推荐并发回归；只在专项授权后运行，不自动迁移。"""

import asyncio
import os
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.core.exceptions import AppException
from app.core.identifiers import new_uuid7
from app.db.models import (
    Category,
    InventoryAccount,
    InventoryReservation,
    InventoryReservationEvent,
    MemberProfile,
    Order,
    OrderEvent,
    OrderItem,
    Product,
    ProductPurchaseLimit,
    ProductPurchaseRecord,
    ProductSku,
    User,
    WalletAccount,
)
from app.db.transaction import transaction_scope
from app.domains.distribution import DistributionService, ReferralBindIn
from app.domains.orders import CheckoutLine, CheckoutRequest
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
                await session.execute(delete(MemberProfile).where(MemberProfile.user_id.in_(users)))
                await session.execute(delete(InventoryAccount).where(InventoryAccount.sku_id == sku_id))
                await session.execute(delete(ProductSku).where(ProductSku.id == sku_id))
                await session.execute(delete(Product).where(Product.id == product_id))
                await session.execute(delete(Category).where(Category.id == category_id))
                await session.execute(delete(User).where(User.id.in_(users)))
        finally:
            await engine.dispose()


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
