"""Consumer profile/finance boundary regressions; execution requires explicit authorization."""

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
from app.db.models.distribution import CommissionRecord, MemberLevel, MemberProfile, WalletLedger, WithdrawalRequest
from app.domains.users.schemas import ConsumerAvatarUpdate, ConsumerProfileUpdate
from app.main import create_app
from app.services.finance_queries import member_read, withdrawal_read
from app.services.finance_query_schemas import (
    ConsumerCommissionRead,
    ConsumerWalletLedgerRead,
)


def test_profile_inputs_require_explicit_valid_changes() -> None:
    assert ConsumerProfileUpdate(display_name="  大仙  ").display_name == "大仙"
    for value in [" ", "x" * 101]:
        with pytest.raises(ValidationError):
            ConsumerProfileUpdate(display_name=value)
    with pytest.raises(ValidationError):
        ConsumerProfileUpdate.model_validate({"display_name": "name", "email": "private@example.test"})
    with pytest.raises(ValidationError):
        ConsumerAvatarUpdate.model_validate({})
    assert ConsumerAvatarUpdate(asset_id=None).asset_id is None


def test_membership_state_and_private_relationship_projection() -> None:
    assert member_read(None, None).state == "not_opened"
    profile = MemberProfile(
        id=new_uuid7(),
        user_id=new_uuid7(),
        level_id=None,
        inviter_id=new_uuid7(),
        invitation_code="private",
        created_at=datetime.now(UTC),
        bound_at=None,
        level_changed_at=None,
    )
    read = member_read(profile, None)
    assert read.state == "no_level" and read.referral_bound
    assert "inviter_id" not in read.model_dump() and "invitation_code" not in read.model_dump()
    level = MemberLevel(id=new_uuid7(), name="普通会员", is_active=True)
    profile.level_id = level.id
    assert member_read(profile, level).state == "active"
    level.is_active = False
    assert member_read(profile, level).state == "inactive"
    with pytest.raises(AppException):
        member_read(profile, None)
    level.id = new_uuid7()
    with pytest.raises(AppException):
        member_read(profile, level)


@pytest.mark.parametrize("status", ["requested", "approved", "rejected", "processing", "unknown", "succeeded"])
def test_review_and_unconfirmed_execution_never_claim_paid(status) -> None:
    now = datetime.now(UTC)
    row = WithdrawalRequest(
        id=new_uuid7(),
        amount=Decimal("10.00"),
        currency="CNY",
        status=status,
        reviewed_at=now,
        confirmed_at=None,
        channel="manual",
        created_at=now,
        updated_at=now,
        destination_reference="private",
        reviewed_by_id=new_uuid7(),
        review_note="private",
        channel_reference="private",
        channel_context={"private": "value"},
        payload_hash="a" * 64,
    )
    read = withdrawal_read(row)
    assert read.funds_status == "not_confirmed" and read.confirmed_at is None
    assert not set(read.model_dump()) & {
        "destination_reference",
        "reviewed_by_id",
        "review_note",
        "channel_reference",
        "channel_context",
        "payload_hash",
    }
    row.confirmed_at = now
    assert withdrawal_read(row).funds_status == ("manual_confirmed" if status == "succeeded" else "not_confirmed")


def test_commission_and_ledger_exclude_operational_identifiers_and_raw_snapshots() -> None:
    row = CommissionRecord(
        id=new_uuid7(),
        level=1,
        base_amount=Decimal("100.00"),
        rate=Decimal("0.1"),
        amount=Decimal("10.00"),
        recovered_amount=Decimal("0.00"),
        status="frozen",
        frozen_at=datetime.now(UTC),
        settle_after=None,
        settled_at=None,
        recovered_at=None,
        source_user_id=new_uuid7(),
        beneficiary_user_id=new_uuid7(),
        policy_id=new_uuid7(),
        rule_snapshot={"private": "value"},
        order_id=new_uuid7(),
        order_item_id=new_uuid7(),
    )
    assert not set(ConsumerCommissionRead.model_validate(row).model_dump()) & {
        "source_user_id",
        "beneficiary_user_id",
        "policy_id",
        "rule_snapshot",
        "order_id",
        "order_item_id",
    }
    ledger = WalletLedger(
        id=new_uuid7(),
        entry_type="commission_settlement",
        amount=Decimal("10.00"),
        frozen_delta=Decimal("0"),
        debt_delta=Decimal("0"),
        wallet_revision=2,
        created_at=datetime.now(UTC),
        idempotency_key="private",
        reference_id=new_uuid7(),
        reference_type="commission",
        balance_after={
            "available_amount": "10.00",
            "frozen_amount": "0.00",
            "debt_amount": "0.00",
            "private": "value",
        },
    )
    read = ConsumerWalletLedgerRead.model_validate(ledger).model_dump()
    assert not set(read) & {"idempotency_key", "reference_id", "reference_type"}
    assert "private" not in read["balance_after"]


@pytest.mark.asyncio
@pytest.mark.parametrize("login_enabled", [False, True])
@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("PATCH", "/users/me", {"display_name": "name"}),
        ("PUT", "/users/me/avatar", {"asset_id": None}),
        ("GET", "/distribution/me/profile", None),
        ("POST", "/distribution/me/profile", None),
        ("GET", "/distribution/me/referrer", None),
        ("POST", "/distribution/me/referrer", {"invitation_code": "ABC12345"}),
        ("GET", "/users/me/points", None),
        ("GET", "/users/me/points/ledgers", None),
        ("GET", "/distribution/me/wallets", None),
        ("GET", "/distribution/me/wallets/commission/ledgers", None),
        ("GET", "/distribution/me/commissions", None),
        ("GET", "/distribution/me/withdrawals", None),
        ("GET", "/users/me/sessions", None),
        ("POST", "/users/me/sessions/revoke", {"session_ids": [str(new_uuid7())]}),
        ("POST", "/users/me/sessions/revocation-status", {"session_ids": [str(new_uuid7())]}),
        ("GET", "/users/me/closure-precheck", None),
        ("POST", "/users/me/avatar-assets", None),
    ],
)
async def test_new_private_routes_reject_missing_auth_and_browser_cookies(method, path, payload, login_enabled) -> None:
    app = create_app(Settings.model_construct(miniapp_login_enabled=login_enabled))
    app.state.resources = MagicMock(spec=AppResources, redis=MagicMock())

    async def no_database():
        yield MagicMock()

    app.dependency_overrides[get_db_session] = no_database
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.request(method, f"/api/v1{path}", json=payload)
        assert response.status_code == (401 if login_enabled else 503)
        response = await client.request(method, f"/api/v1{path}", json=payload, headers={"Cookie": "browser=unit"})
        assert response.status_code == 400
