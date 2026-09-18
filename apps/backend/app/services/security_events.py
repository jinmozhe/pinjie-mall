import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import TypeVar

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.core.identifiers import new_uuid7
from app.core.request_metadata import RequestMetadata
from app.db.models import AuditEvent, SecurityLoginEvent
from app.db.repositories import SecurityRepository
from app.db.transaction import transaction_scope

T = TypeVar("T")


def login_event(
    *,
    principal_type: str,
    principal_id: uuid.UUID | None,
    identifier_digest: str | None,
    event_type: str,
    succeeded: bool,
    reason_code: str,
    metadata: RequestMetadata,
    now: datetime | None = None,
) -> SecurityLoginEvent:
    return SecurityLoginEvent(
        id=new_uuid7(),
        principal_type=principal_type,
        principal_id=principal_id,
        identifier_digest=identifier_digest,
        event_type=event_type,
        succeeded=succeeded,
        reason_code=reason_code,
        ip_address=metadata.ip_address,
        user_agent_summary=metadata.user_agent_summary,
        request_id=metadata.request_id,
        trace_id=metadata.trace_id,
        release_version=metadata.release_version,
        occurred_at=now or datetime.now(UTC),
    )


class SecurityEventWriter:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def record_login(self, event: SecurityLoginEvent) -> None:
        try:
            async with self._session_factory() as session, transaction_scope(session):
                SecurityRepository(session).add_login_event(event)
        except Exception as exc:
            # 安全审计写入降级：存储故障不阻断主业务流程（如认证失败 401）。
            # 只记录 critical 告警，不向上传播异常，保证可用性与审计完整性分离。
            from loguru import logger

            logger.opt(exception=exc).critical(
                "security login event write failed, event dropped: type={} principal={}",
                event.event_type,
                event.principal_id,
            )


class AuditCoordinator:
    def __init__(
        self,
        *,
        session: AsyncSession,
        session_factory: async_sessionmaker[AsyncSession],
        actor_id: uuid.UUID,
        metadata: RequestMetadata,
    ) -> None:
        self._session = session
        self._session_factory = session_factory
        self._actor_id = actor_id
        self._metadata = metadata

    async def execute(
        self,
        *,
        action: str,
        target_type: str,
        target_id: uuid.UUID | None,
        changed_fields: dict[str, object],
        operation: Callable[[], Awaitable[T]],
    ) -> T:
        event_id = await self._start(action=action, target_type=target_type, target_id=target_id)
        try:
            async with transaction_scope(self._session):
                result = await operation()
                event = await SecurityRepository(self._session).get_audit_event(event_id, for_update=True)
                if event is None:
                    raise AppException(
                        status_code=503,
                        code=ErrorCode.SERVICE_UNAVAILABLE,
                        message="审计事件存储暂时不可用",
                    )
                event.result = "succeeded"
                event.changed_fields = changed_fields
                event.completed_at = datetime.now(UTC)
            return result
        except AppException:
            await self._finish_failed(event_id, result="denied")
            raise
        except Exception:
            await self._finish_failed(event_id, result="failed")
            raise

    async def _start(self, *, action: str, target_type: str, target_id: uuid.UUID | None) -> uuid.UUID:
        event_id = new_uuid7()
        event = AuditEvent(
            id=event_id,
            actor_id=self._actor_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            result="started",
            changed_fields={},
            request_id=self._metadata.request_id,
            trace_id=self._metadata.trace_id,
            release_version=self._metadata.release_version,
            ip_address=self._metadata.ip_address,
            occurred_at=datetime.now(UTC),
            completed_at=None,
        )
        try:
            async with self._session_factory() as session, transaction_scope(session):
                SecurityRepository(session).add_audit_event(event)
        except Exception as exc:
            raise AppException(
                status_code=503,
                code=ErrorCode.SERVICE_UNAVAILABLE,
                message="审计存储暂时不可用",
            ) from exc
        return event_id

    async def _finish_failed(self, event_id: uuid.UUID, *, result: str) -> None:
        try:
            async with self._session_factory() as session, transaction_scope(session):
                event = await SecurityRepository(session).get_audit_event(event_id, for_update=True)
                if event is not None and event.result == "started":
                    event.result = result
                    event.completed_at = datetime.now(UTC)
        except Exception as exc:
            from loguru import logger

            logger.bind(audit_event_id=str(event_id), result=result).opt(exception=exc).critical(
                "failed to finalize audit event"
            )


__all__ = ["AuditCoordinator", "SecurityEventWriter", "login_event"]
