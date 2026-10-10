"""Consumer read-model and HTTP boundary regressions; execution requires pytest authorization."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import httpx
import pytest
from pydantic import ValidationError

from app.api.dependencies import get_db_session
from app.core.config import Settings
from app.core.exceptions import AppException
from app.core.identifiers import new_uuid7
from app.core.resources import AppResources
from app.db.models.commerce_lifecycle import RefundAttempt, RefundRequest
from app.main import create_app
from app.services.trade_queries import display_status, refund_read


@pytest.mark.parametrize(
    ("status", "fulfillment", "expected"),
    [
        ("pending_payment", None, "pending_payment"),
        ("cancelled", None, "cancelled"),
        ("paid", None, "awaiting_fulfillment"),
        ("paid", "awaiting_delivery", "awaiting_delivery"),
        ("paid", "awaiting_shipment", "awaiting_shipment"),
        ("paid", "shipped", "shipped"),
        ("paid", "delivered", "delivered"),
        ("paid", "cancelled", "refund_completed"),
    ],
)
def test_display_requires_order_and_fulfillment_facts(status, fulfillment, expected) -> None:
    assert display_status(status, fulfillment) == expected


def test_unknown_order_and_fulfillment_fail_closed() -> None:
    with pytest.raises(AppException):
        display_status("completed", "delivered")
    with pytest.raises(AppException):
        display_status("paid", "unknown")


def refund_fixture(amount: str = "12.00", status: str = "approved") -> RefundRequest:
    return RefundRequest(
        id=new_uuid7(),
        order_id=new_uuid7(),
        user_id=new_uuid7(),
        request_id=new_uuid7(),
        status=status,
        review_mode="automatic",
        items_amount=Decimal(amount),
        freight_amount=Decimal("0.00"),
        amount=Decimal(amount),
        currency="CNY",
        reason="unit reason",
        review_note=None,
        created_at=datetime.now(UTC),
        reviewed_at=None,
        completed_at=None,
        revision=1,
    )


@pytest.mark.parametrize("state", ["created", "processing", "unknown", "abnormal", "closed"])
def test_approval_or_execution_without_verified_funds_never_claims_return(state) -> None:
    row = refund_fixture()
    attempt = RefundAttempt(
        id=new_uuid7(),
        refund_request_id=row.id,
        order_id=row.order_id,
        purpose="after_sale",
        amount=row.amount,
        currency=row.currency,
        status=state,
        confirmed_at=None,
    )
    read = refund_read(row, attempt)
    assert read.funds_status == "not_confirmed" and read.funds_confirmed_at is None
    assert "merchant_refund_reference" not in read.model_dump()


def test_verified_funds_and_zero_amount_are_distinct() -> None:
    row = refund_fixture()
    now = datetime.now(UTC)
    attempt = RefundAttempt(
        id=new_uuid7(),
        refund_request_id=row.id,
        order_id=row.order_id,
        purpose="after_sale",
        amount=row.amount,
        currency=row.currency,
        status="succeeded",
        confirmed_at=now,
    )
    assert refund_read(row, attempt).funds_status == "confirmed"
    attempt.confirmed_at = None
    assert refund_read(row, attempt).funds_status == "not_confirmed"
    assert refund_read(refund_fixture("0.00", "completed"), None).funds_status == "no_funds"
    assert refund_read(refund_fixture("0.00", "approved"), None).funds_status == "not_confirmed"
    attempt.amount = Decimal("1.00")
    with pytest.raises(AppException):
        refund_read(row, attempt)


def test_support_config_rejects_invalid_public_contacts() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, SUPPORT_PHONE="javascript:bad")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, SUPPORT_EMAIL="missing-domain")


@pytest.mark.asyncio
@pytest.mark.parametrize("login_enabled", [False, True])
@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("GET", "/orders", None),
        ("GET", f"/orders/{new_uuid7()}", None),
        ("GET", "/refunds/intent", None),
        ("GET", "/refunds", None),
        ("GET", f"/refunds/{new_uuid7()}", None),
        ("GET", f"/refunds/by-request/{new_uuid7()}", None),
        ("POST", f"/orders/{new_uuid7()}/fulfillment/confirm-receipt", {"revision": 1}),
        ("POST", f"/orders/{new_uuid7()}/refunds", {"request_id": str(new_uuid7()), "reason": "unit"}),
        ("POST", f"/order-items/{new_uuid7()}/review", {"rating": 5, "content": "unit"}),
    ],
)
async def test_private_trade_endpoints_refuse_missing_auth_and_browser_cookie(
    method, path, payload, login_enabled
) -> None:
    app = create_app(Settings.model_construct(miniapp_login_enabled=login_enabled))
    app.state.resources = MagicMock(spec=AppResources, redis=MagicMock())

    async def no_database():
        yield MagicMock()

    app.dependency_overrides[get_db_session] = no_database
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        disabled = await client.request(method, f"/api/v1{path}", json=payload)
        assert disabled.status_code == (401 if login_enabled else 503)
        cookie = await client.request(method, f"/api/v1{path}", json=payload, headers={"Cookie": "browser-only=unit"})
        assert cookie.status_code == 400


@pytest.mark.asyncio
async def test_help_is_public_and_absent_contacts_are_explicit() -> None:
    app = create_app(Settings.model_construct())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get("/api/v1/system/help")
        assert response.status_code == 200
        assert response.json()["data"] == {"phone": None, "email": None}
        assert response.headers["cache-control"] == "no-store"
