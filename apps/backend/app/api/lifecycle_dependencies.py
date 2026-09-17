from typing import Annotated

from fastapi import Depends, Request

from app.api.dependencies import CurrentAdmin, DatabaseSession, get_current_admin, get_resources
from app.core.request_metadata import request_metadata
from app.db.repositories.commerce_access import CommerceAccessRepository
from app.services.lifecycle import AdminLifecycleApplicationService
from app.services.payment_lifecycle import LifecycleService
from app.services.security_events import AuditCoordinator


def get_lifecycle_service(session: DatabaseSession) -> LifecycleService:
    return LifecycleService(session)


def get_admin_lifecycle_service(
    request: Request,
    session: DatabaseSession,
    current: Annotated[CurrentAdmin, Depends(get_current_admin)],
) -> AdminLifecycleApplicationService:
    return AdminLifecycleApplicationService(
        lifecycle=LifecycleService(session),
        access=CommerceAccessRepository(session),
        audit=AuditCoordinator(
            session=session,
            session_factory=get_resources(request).session_factory,
            actor_id=current.admin.id,
            metadata=request_metadata(request),
        ),
        actor_id=current.admin.id,
    )


Lifecycle = Annotated[LifecycleService, Depends(get_lifecycle_service)]
AdminLifecycle = Annotated[AdminLifecycleApplicationService, Depends(get_admin_lifecycle_service)]
