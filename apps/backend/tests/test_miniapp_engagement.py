"""Projection safety regressions. Running pytest requires separate authorization."""

from datetime import UTC, datetime

import pytest

from app.core.exceptions import AppException
from app.core.identifiers import new_uuid7
from app.db.models.distribution import MemberProfile, PointsAccount, PointsLedger
from app.services.miniapp_engagement import referral_read
from app.services.miniapp_engagement_schemas import MiniappPointsAccountRead, MiniappPointsLedgerRead


def test_bound_referral_requires_exact_original_code_without_exposing_inviter() -> None:
    now = datetime.now(UTC)
    profile = MemberProfile(user_id=new_uuid7(), invitation_code="ABC12345", inviter_id=new_uuid7(), bound_at=now)
    correct = referral_read(profile, "DEF12345", "DEF12345")
    assert correct.state == "bound" and correct.matches_invitation is True
    assert correct.invitation_code == "ABC12345"
    assert "inviter_id" not in correct.model_dump() and "DEF12345" not in correct.model_dump_json()
    assert referral_read(profile, "DEF12345", "OTHER123").matches_invitation is False
    assert referral_read(profile, "DEF12345", None).matches_invitation is None
    with pytest.raises(AppException):
        referral_read(profile, None, "DEF12345")
    profile.bound_at = None
    with pytest.raises(AppException):
        referral_read(profile, "DEF12345", "DEF12345")
    profile.inviter_id = None
    assert referral_read(profile, None, "DEF12345").state == "unbound"
    assert referral_read(None, None, "DEF12345").state == "not_opened"


def test_points_json_preserves_bigint_precision_and_excludes_private_source_data() -> None:
    now = datetime.now(UTC)
    exact = 9_007_199_254_740_993
    account = PointsAccount(
        id=new_uuid7(),
        user_id=new_uuid7(),
        available_points=exact,
        frozen_points=0,
        debt_points=2,
        revision=1,
        updated_at=now,
    )
    data = MiniappPointsAccountRead.model_validate(account).model_dump(mode="json")
    assert data["available_points"] == str(exact) and data["frozen_points"] == "0"
    assert not set(data) & {"user_id", "id"}
    ledger = PointsLedger(
        id=new_uuid7(),
        account_id=account.id,
        entry_type="reverse",
        available_delta=-exact,
        frozen_delta=0,
        debt_delta=2,
        source_type="refund",
        source_id=new_uuid7(),
        idempotency_key="private",
        note="private",
        reverses_ledger_id=new_uuid7(),
        created_at=now,
    )
    data = MiniappPointsLedgerRead.model_validate(ledger).model_dump(mode="json")
    assert data["available_delta"] == str(-exact) and data["debt_delta"] == "2"
    assert not set(data) & {"account_id", "source_id", "idempotency_key", "note", "reverses_ledger_id"}
