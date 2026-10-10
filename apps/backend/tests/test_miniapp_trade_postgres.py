"""Real PostgreSQL consumer ownership and pagination regression; never auto-migrates."""

import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.core.exceptions import AppException
from app.core.identifiers import new_uuid7
from app.db.models import User
from app.db.models.commerce_lifecycle import Fulfillment, RefundRequest
from app.db.models.order import Order
from app.services.trade_queries import ConsumerTradeQueryService


@pytest.mark.integration
@pytest.mark.asyncio
async def test_owner_pagination_fulfillment_and_refund_lookup_are_isolated() -> None:
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.fail("Explicit isolated TEST_DATABASE_URL is required")
    settings = Settings(ENVIRONMENT="test", DATABASE_URL=database_url, TEST_DATABASE_URL=database_url)
    settings.validate_database_runtime()
    engine = create_async_engine(database_url, pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as session:
            try:
                # All fixtures remain in this uncommitted transaction and roll back even on failure.
                owner, other = new_uuid7(), new_uuid7()
                session.add_all([User(id=owner, username=f"trade-{owner}"), User(id=other, username=f"trade-{other}")])
                await session.flush()
                now = datetime.now(UTC)
                orders = []
                for user_id, status in [
                    (owner, "awaiting_delivery"),
                    (owner, "delivered"),
                    (other, "awaiting_delivery"),
                ]:
                    order = Order(
                        id=new_uuid7(),
                        user_id=user_id,
                        request_id=new_uuid7(),
                        request_hash="a" * 64,
                        quote_fingerprint="b" * 64,
                        status="paid",
                        product_type="virtual",
                        currency="CNY",
                        items_amount=Decimal("0.00"),
                        freight_amount=Decimal("0.00"),
                        total_amount=Decimal("0.00"),
                        address_snapshot=None,
                        shipping_snapshot={},
                        buyer_level_snapshot={},
                        pricing_version="test",
                        expires_at=now + timedelta(minutes=10),
                        paid_at=now,
                        settlement_kind="zero_amount",
                        zero_confirmation_id=new_uuid7(),
                        revision=1,
                    )
                    session.add(order)
                    await session.flush()
                    session.add(
                        Fulfillment(
                            id=new_uuid7(),
                            order_id=order.id,
                            product_type="virtual",
                            status=status,
                            revision=1,
                            delivered_at=now if status == "delivered" else None,
                        )
                    )
                    orders.append(order)
                await session.flush()
                foreign_refund = RefundRequest(
                    id=new_uuid7(),
                    order_id=orders[2].id,
                    user_id=other,
                    request_id=new_uuid7(),
                    request_hash="c" * 64,
                    status="requested",
                    review_mode="manual",
                    items_amount=Decimal("0.00"),
                    freight_amount=Decimal("0.00"),
                    amount=Decimal("0.00"),
                    currency="CNY",
                    reason="unit",
                    fulfillment_status_snapshot="awaiting_delivery",
                    revision=1,
                )
                session.add(foreign_refund)
                await session.flush()
                query = ConsumerTradeQueryService(session)
                first = await query.orders(owner, 1, 1, None)
                second = await query.orders(owner, 2, 1, None)
                assert first.total == 2 and first.total_pages == 2
                assert {first.items[0].id, second.items[0].id} == {orders[0].id, orders[1].id}
                waiting = await query.orders(owner, 1, 1, "awaiting_delivery")
                assert waiting.total == 1 and waiting.items[0].id == orders[0].id
                assert waiting.items[0].can_refund and not waiting.items[0].can_confirm_receipt
                with pytest.raises(AppException) as inaccessible:
                    await query.order(owner, orders[2].id)
                assert inaccessible.value.status_code == 404
                with pytest.raises(AppException):
                    await query.refund(owner, foreign_refund.id)
                assert (await query.refund_by_request(owner, foreign_refund.request_id)).state == "not_found"
                assert (await query.refunds(owner, 1, 10, None)).total == 0
                with pytest.raises(AppException):
                    await query.refunds(owner, 1, 10, orders[2].id)
            finally:
                await session.rollback()
    finally:
        await engine.dispose()
