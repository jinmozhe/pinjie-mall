import argparse
import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, or_, select

from app.core.config import get_settings
from app.core.resources import create_resources
from app.db.models import AdminSession, AuditEvent, RequestLog, SecurityLoginEvent, UserSession
from app.db.transaction import transaction_scope
from scripts._database_target import validate_database_target


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Preview or apply security log retention")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-database", required=True)
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> None:
    settings = get_settings()
    validate_database_target(settings, args.confirm_database)
    security_cutoff = datetime.now(UTC) - timedelta(days=settings.security_event_retention_days)
    request_cutoff = datetime.now(UTC) - timedelta(days=settings.request_log_retention_days)
    session_cutoff = datetime.now(UTC) - timedelta(days=settings.session_retention_days)
    user_session_predicate = or_(
        UserSession.absolute_expires_at < session_cutoff,
        UserSession.revoked_at < session_cutoff,
    )
    admin_session_predicate = or_(
        AdminSession.absolute_expires_at < session_cutoff,
        AdminSession.revoked_at < session_cutoff,
    )
    resources = create_resources(settings)
    try:
        async with resources.session_factory() as session:
            login_count_raw = await session.scalar(
                select(func.count())
                .select_from(SecurityLoginEvent)
                .where(SecurityLoginEvent.occurred_at < security_cutoff)
            )
            audit_count_raw = await session.scalar(
                select(func.count()).select_from(AuditEvent).where(AuditEvent.occurred_at < security_cutoff)
            )
            request_count_raw = await session.scalar(
                select(func.count()).select_from(RequestLog).where(RequestLog.occurred_at < request_cutoff)
            )
            user_session_count_raw = await session.scalar(
                select(func.count()).select_from(UserSession).where(user_session_predicate)
            )
            admin_session_count_raw = await session.scalar(
                select(func.count()).select_from(AdminSession).where(admin_session_predicate)
            )
            login_count = int(login_count_raw or 0)
            audit_count = int(audit_count_raw or 0)
            request_count = int(request_count_raw or 0)
            user_session_count = int(user_session_count_raw or 0)
            admin_session_count = int(admin_session_count_raw or 0)
            print(
                f"login_events={login_count} audit_events={audit_count} request_logs={request_count} "
                f"user_sessions={user_session_count} admin_sessions={admin_session_count}"
            )
            if not args.apply:
                print("Dry run only; no rows deleted")
                return
            async with transaction_scope(session):
                await session.execute(
                    delete(SecurityLoginEvent).where(SecurityLoginEvent.occurred_at < security_cutoff)
                )
                await session.execute(delete(AuditEvent).where(AuditEvent.occurred_at < security_cutoff))
                await session.execute(delete(RequestLog).where(RequestLog.occurred_at < request_cutoff))
                await session.execute(delete(UserSession).where(user_session_predicate))
                await session.execute(delete(AdminSession).where(admin_session_predicate))
            print("Retention cleanup applied")
    finally:
        await resources.close()


def main() -> None:
    asyncio.run(_run(_arguments()))


if __name__ == "__main__":
    main()
