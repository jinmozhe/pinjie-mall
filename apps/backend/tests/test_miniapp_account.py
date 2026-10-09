"""Account security regression assets; pytest execution needs explicit authorization."""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.core.identifiers import new_uuid7
from app.db.models import UserSession
from app.services.miniapp_account import login_session_read
from app.services.miniapp_account_schemas import MiniappClosurePrecheckRead, MiniappSessionTargets


def test_session_projection_masks_network_and_distinguishes_terminal_states() -> None:
    now = datetime.now(UTC)
    row = UserSession(
        id=new_uuid7(),
        user_id=new_uuid7(),
        family_id=new_uuid7(),
        credential_profile="miniapp_bearer",
        client_id="pinjie-miniapp",
        csrf_digest=None,
        device_name="微信小程序",
        ip_address="192.0.2.123",
        user_agent_summary="private",
        created_at=now,
        last_seen_at=now,
        idle_expires_at=now + timedelta(days=1),
        absolute_expires_at=now + timedelta(days=2),
        revoked_at=None,
    )
    read = login_session_read(row, row.id, now)
    assert read.is_current and read.state == "active" and read.ip_masked == "192.0.2.0/24"
    assert not set(read.model_dump()) & {"user_id", "family_id", "csrf_digest", "user_agent_summary", "ip_address"}
    row.idle_expires_at = now
    assert login_session_read(row, new_uuid7(), now).state == "expired"
    row.revoked_at = now
    assert login_session_read(row, row.id, now).state == "revoked"


def test_targets_and_closed_self_service_contract_fail_closed() -> None:
    first = new_uuid7()
    assert MiniappSessionTargets(session_ids=[first]).session_ids == [first]
    for payload in [
        {"session_ids": []},
        {"session_ids": [first, first]},
        {"session_ids": [new_uuid7() for _ in range(101)]},
        {"session_ids": [first], "revoke_all": True},
    ]:
        with pytest.raises(ValidationError):
            MiniappSessionTargets.model_validate(payload)
    with pytest.raises(ValidationError):
        MiniappClosurePrecheckRead(
            self_service_enabled=True,
            checked_at=datetime.now(UTC),
            wallet_state="not_opened",
            points_state="not_opened",
            checks=[],
        )
