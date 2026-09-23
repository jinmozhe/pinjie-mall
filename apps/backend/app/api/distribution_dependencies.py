from typing import Annotated

from fastapi import Depends, Request

from app.api.dependencies import (
    CurrentAdmin,
    CurrentUser,
    DatabaseSession,
    get_current_admin,
    get_current_user,
    get_resources,
)
from app.core.request_metadata import request_metadata
from app.db.repositories.commerce_access import CommerceAccessRepository
from app.domains.distribution import DistributionService
from app.services.distribution import AdminDistributionApplicationService, UserDistributionApplicationService
from app.services.security_events import AuditCoordinator


def get_distribution_service(session: DatabaseSession) -> DistributionService:
    return DistributionService(session)


def get_admin_distribution_service(
    request: Request,
    session: DatabaseSession,
    current: Annotated[CurrentAdmin, Depends(get_current_admin)],
) -> AdminDistributionApplicationService:
    return AdminDistributionApplicationService(
        distribution=DistributionService(session),
        access=CommerceAccessRepository(session),
        audit=AuditCoordinator(
            session=session,
            session_factory=get_resources(request).session_factory,
            actor_id=current.admin.id,
            metadata=request_metadata(request),
        ),
        actor_id=current.admin.id,
    )


def get_user_distribution_service(
    request: Request,
    session: DatabaseSession,
    current: Annotated[CurrentUser, Depends(get_current_user)],
) -> UserDistributionApplicationService:
    return UserDistributionApplicationService(
        distribution=DistributionService(session),
        audit=AuditCoordinator(
            session=session,
            session_factory=get_resources(request).session_factory,
            actor_id=current.user.id,
            metadata=request_metadata(request),
        ),
        actor_id=current.user.id,
    )


Distribution = Annotated[DistributionService, Depends(get_distribution_service)]
AdminDistribution = Annotated[AdminDistributionApplicationService, Depends(get_admin_distribution_service)]
UserDistribution = Annotated[UserDistributionApplicationService, Depends(get_user_distribution_service)]
