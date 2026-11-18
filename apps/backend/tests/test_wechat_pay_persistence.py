"""Real PostgreSQL channel invariants; execution requires explicit authorization."""

import asyncio
import base64
import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.core.identifiers import new_uuid7
from app.db.models import DurableTask, Order, PaymentAttempt, PaymentEvent, RefundAttempt, RefundEvent, User
from app.db.models.commerce_lifecycle import WechatPayNotification
from app.db.transaction import transaction_scope
from app.services.wechat_pay import WechatPaymentService
from app.services.wechat_pay_client import PayProtocolError, PayRefund, PayTransaction, WechatPayClient
from tests import test_wechat_pay_protocol as protocol

pay_material = protocol.pay_material
signed_headers = protocol.signed_headers


@pytest.fixture
async def payment_database(pay_material):
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.fail("TEST_DATABASE_URL is required")
    Settings(_env_file=None, ENVIRONMENT="test", DATABASE_URL=url, TEST_DATABASE_URL=url).validate_database_runtime()
    engine = create_async_engine(url)
    async with engine.connect() as connection:
        outer = await connection.begin()
        try:
            async with AsyncSession(
                bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
            ) as session:
                yield session
        finally:
            await outer.rollback()
    await engine.dispose()


async def seed_payment(session, settings):
    now = datetime.now(UTC)
    user = User(id=new_uuid7(), username=new_uuid7().hex, password_hash="unused-test-hash", is_active=True)
    session.add(user)
    await session.flush()
    order = Order(
        id=new_uuid7(),
        user_id=user.id,
        request_id=new_uuid7(),
        request_hash="a" * 64,
        quote_fingerprint="b" * 64,
        product_type="virtual",
        status="pending_payment",
        items_amount=Decimal("10.00"),
        freight_amount=Decimal("0.00"),
        total_amount=Decimal("10.00"),
        shipping_snapshot={},
        buyer_level_snapshot={},
        pricing_version="test",
        expires_at=now + timedelta(minutes=15),
        revision=1,
    )
    session.add(order)
    await session.flush()
    attempt = PaymentAttempt(
        id=new_uuid7(),
        order_id=order.id,
        user_id=user.id,
        request_id=new_uuid7(),
        request_hash="c" * 64,
        channel="wechat",
        merchant_reference=new_uuid7().hex,
        status="unknown",
        amount=order.total_amount,
        currency="CNY",
        revision=1,
        channel_context=WechatPaymentService(session, settings, None).snapshot("payer-unit"),
        channel_expires_at=order.expires_at,
        created_at=now - timedelta(seconds=5),
    )
    session.add(attempt)
    await session.commit()
    return attempt


def payment_fact(attempt, settings):
    return PayTransaction(
        appid=settings.wechat_app_id,
        mchid=settings.wechat_pay_mch_id,
        out_trade_no=attempt.merchant_reference,
        transaction_id=new_uuid7().hex,
        trade_state="SUCCESS",
        success_time=datetime.now(UTC).replace(microsecond=0),
        amount={"total": 1000, "currency": "CNY"},
        payer={"openid": "payer-unit"},
    )


@pytest.mark.integration
async def test_verified_payment_is_idempotent_and_wrong_amount_does_not_change_funds(payment_database, pay_material):
    session = payment_database
    settings, _, _ = pay_material
    attempt = await seed_payment(session, settings)
    attempt_id = attempt.id
    service = WechatPaymentService(session, settings, None)
    fact = payment_fact(attempt, settings)
    wrong = fact.model_copy(update={"amount": fact.amount.model_copy(update={"total": 999})})
    with pytest.raises(PayProtocolError):
        await service.confirm_payment(wrong)
    await service.confirm_payment(fact)
    await service.confirm_payment(fact)
    assert (
        await session.scalar(
            select(func.count()).select_from(PaymentEvent).where(PaymentEvent.payment_attempt_id == attempt_id)
        )
        == 1
    )
    assert (
        await session.scalar(
            select(func.count())
            .select_from(DurableTask)
            .where(DurableTask.business_key == f"confirm-order:{attempt_id}")
        )
        == 1
    )
    assert (await session.get(PaymentAttempt, attempt_id)).status == "succeeded"


@pytest.mark.integration
async def test_duplicate_encrypted_notification_has_one_inbox_and_task(payment_database, pay_material):
    settings, _, platform = pay_material
    session = payment_database
    attempt = await seed_payment(session, settings)
    fact = payment_fact(attempt, settings)
    event_id = new_uuid7().hex

    def envelope(data):
        cipher = AESGCM(settings.wechat_pay_api_v3_key.encode()).encrypt(
            b"unit-nonce12", json.dumps(data).encode(), b"transaction"
        )
        return json.dumps(
            {
                "id": event_id,
                "event_type": "TRANSACTION.SUCCESS",
                "resource": {
                    "algorithm": "AEAD_AES_256_GCM",
                    "nonce": "unit-nonce12",
                    "associated_data": "transaction",
                    "ciphertext": base64.b64encode(cipher).decode(),
                },
            }
        ).encode()

    async with httpx.AsyncClient() as http:
        service = WechatPaymentService(session, settings, WechatPayClient(settings, http))
        body = envelope(fact.model_dump(mode="json"))
        await service.receive(signed_headers(platform, body), body, refund=False)
        await service.receive(signed_headers(platform, body), body, refund=False)
        rows = list(
            await session.scalars(
                select(WechatPayNotification).where(WechatPayNotification.notification_id == event_id)
            )
        )
        assert len(rows) == 1 and "payer" not in rows[0].verified_payload
        assert rows[0].verified_payload["payer_hash"] == hashlib.sha256(b"payer-unit").hexdigest()
        assert (
            await session.scalar(
                select(func.count())
                .select_from(DurableTask)
                .where(DurableTask.business_key == f"wechat-notification:{rows[0].id}")
            )
            == 1
        )
        await service.process_notification(rows[0].id)
        await service.process_notification(rows[0].id)
        conflicting = envelope({**fact.model_dump(mode="json"), "transaction_id": "conflicting"})
        with pytest.raises(PayProtocolError):
            await service.receive(signed_headers(platform, conflicting), conflicting, refund=False)


@pytest.mark.integration
async def test_refund_success_survives_stale_processing_and_repeated_confirmation(payment_database, pay_material):
    session = payment_database
    settings, _, _ = pay_material
    attempt = await seed_payment(session, settings)
    service = WechatPaymentService(session, settings, None)
    payment = payment_fact(attempt, settings)
    await service.confirm_payment(payment)
    refund = RefundAttempt(
        id=new_uuid7(),
        order_id=attempt.order_id,
        payment_attempt_id=attempt.id,
        purpose="late_payment",
        attempt_no=1,
        channel="wechat",
        merchant_refund_reference=new_uuid7().hex,
        amount=attempt.amount,
        currency="CNY",
        status="unknown",
        revision=1,
        created_at=datetime.now(UTC) - timedelta(seconds=5),
    )
    session.add(refund)
    await session.commit()
    fact = PayRefund(
        mchid=settings.wechat_pay_mch_id,
        out_trade_no=attempt.merchant_reference,
        transaction_id=payment.transaction_id,
        out_refund_no=refund.merchant_refund_reference,
        refund_id=new_uuid7().hex,
        status="SUCCESS",
        success_time=datetime.now(UTC).replace(microsecond=0),
        amount={"total": 1000, "refund": 1000, "currency": "CNY"},
    )
    await service.confirm_refund(fact)
    await service.confirm_refund(fact.model_copy(update={"status": "PROCESSING", "success_time": None}))
    await service.confirm_refund(fact)
    assert (await session.get(RefundAttempt, refund.id)).status == "succeeded"
    assert (
        await session.scalar(
            select(func.count()).select_from(RefundEvent).where(RefundEvent.refund_attempt_id == refund.id)
        )
        == 1
    )


@pytest.mark.integration
async def test_concurrent_notification_delivery_commits_one_recoverable_task(pay_material):
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.fail("TEST_DATABASE_URL is required")
    Settings(_env_file=None, ENVIRONMENT="test", DATABASE_URL=url, TEST_DATABASE_URL=url).validate_database_runtime()
    settings, _, platform = pay_material
    event_id = new_uuid7().hex
    plain = {
        "appid": settings.wechat_app_id,
        "mchid": settings.wechat_pay_mch_id,
        "out_trade_no": new_uuid7().hex,
        "transaction_id": new_uuid7().hex,
        "trade_state": "SUCCESS",
        "success_time": datetime.now(UTC).isoformat(),
        "amount": {"total": 1000, "currency": "CNY"},
        "payer": {"openid": "concurrent-test-payer"},
    }
    cipher = AESGCM(settings.wechat_pay_api_v3_key.encode()).encrypt(
        b"unit-nonce12", json.dumps(plain).encode(), b"transaction"
    )
    body = json.dumps(
        {
            "id": event_id,
            "event_type": "TRANSACTION.SUCCESS",
            "resource": {
                "algorithm": "AEAD_AES_256_GCM",
                "nonce": "unit-nonce12",
                "associated_data": "transaction",
                "ciphertext": base64.b64encode(cipher).decode(),
            },
        }
    ).encode()
    engine = create_async_engine(url, connect_args={"server_settings": {"lock_timeout": "5000ms"}})
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with httpx.AsyncClient() as http:
            client = WechatPayClient(settings, http)
            ready = asyncio.Event()

            async def deliver():
                async with factory() as session:
                    await ready.wait()
                    await WechatPaymentService(session, settings, client).receive(
                        signed_headers(platform, body), body, refund=False
                    )

            async with asyncio.TaskGroup() as group:
                group.create_task(deliver())
                group.create_task(deliver())
                ready.set()
        async with factory() as session:
            notice = (
                await session.scalars(
                    select(WechatPayNotification).where(WechatPayNotification.notification_id == event_id)
                )
            ).one()
            tasks = list(
                await session.scalars(
                    select(DurableTask).where(DurableTask.business_key == f"wechat-notification:{notice.id}")
                )
            )
            assert len(tasks) == 1 and tasks[0].status == "pending" and notice.status == "pending"
    finally:
        async with factory() as session, transaction_scope(session):
            notices = list(
                await session.scalars(
                    select(WechatPayNotification).where(WechatPayNotification.notification_id == event_id)
                )
            )
            for notice in notices:
                await session.execute(
                    delete(DurableTask).where(DurableTask.business_key == f"wechat-notification:{notice.id}")
                )
                await session.delete(notice)
        await engine.dispose()
