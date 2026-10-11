from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid7

from app.db.models import AdminSession


def admin_session(admin_id: UUID, *, session_id: UUID | None = None) -> AdminSession:
    now = datetime.now(UTC)
    return AdminSession(
        id=session_id or uuid7(),
        admin_id=admin_id,
        family_id=uuid7(),
        credential_profile="browser_cookie",
        client_id="pinjie-admin",
        csrf_digest="a" * 64,
        last_seen_at=now,
        idle_expires_at=now + timedelta(days=7),
        absolute_expires_at=now + timedelta(days=30),
    )
