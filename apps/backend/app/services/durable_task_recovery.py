"""Explicit recovery of an inspected attention task, with atomic audit evidence."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.identifiers import new_uuid7
from app.db.models import AuditEvent
from app.db.repositories import SecurityRepository
from app.db.transaction import transaction_scope
from app.domains.durable_tasks.repository import DurableTaskRepository


async def recover_task(
    session: AsyncSession,
    *,
    task_id: UUID,
    revision: int,
    operator: str,
    reason: str,
    apply: bool,
    release_version: str | None,
) -> str:
    if not 1 <= len(operator.strip()) <= 80 or not 5 <= len(reason.strip()) <= 200:
        raise ValueError("operator and a specific recovery reason are required")
    repository = DurableTaskRepository(session)
    async with transaction_scope(session):
        task = await repository.task(task_id, lock=apply)
        if task is None or task.status != "attention" or task.revision != revision:
            raise ValueError("task must be attention with the exact inspected revision")
        if not apply:
            return f"task_id={task.id}; type={task.task_type}; revision={task.revision}; dry_run=true"
        now = await repository.database_now()
        previous_failures = task.failure_count
        task.status, task.failure_count, task.available_at = "pending", 0, now
        task.revision += 1
        task.updated_at = now
        correlation = str(new_uuid7())
        SecurityRepository(session).add_audit_event(
            AuditEvent(
                actor_id=None,
                actor_type="system",
                action="durable_task.recovered",
                target_type="durable_task",
                target_id=task.id,
                target_revision=task.revision,
                result="succeeded",
                changed_fields={
                    "operator": operator,
                    "reason": reason,
                    "from_status": "attention",
                    "to_status": "pending",
                    "previous_failure_count": previous_failures,
                    "previous_error_code": task.last_error_code,
                },
                request_id=correlation,
                trace_id=correlation,
                release_version=release_version,
                ip_address=None,
                occurred_at=now,
                completed_at=now,
            )
        )
        await repository.flush()
        return f"task_id={task.id}; revision={task.revision}; recovered=true"
