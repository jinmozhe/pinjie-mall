from typing import Annotated

from fastapi import Depends, Request

from app.api.dependencies import (
    CurrentAdmin,
    CurrentUser,
    DatabaseSession,
    get_current_admin,
    get_phone_user,
    get_resources,
)
from app.core.request_metadata import request_metadata
from app.domains.distribution import DistributionService
from app.services.admin_audit import AdminAuditCoordinator
from app.services.distribution import AdminDistributionApplicationService, UserDistributionApplicationService
from app.services.engagement import ConsumerEngagementService
from app.services.finance_queries import ConsumerFinanceService
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
        audit=AdminAuditCoordinator(
            audit=AuditCoordinator(
                session=session,
                session_factory=get_resources(request).session_factory,
                actor_id=current.admin.id,
                metadata=request_metadata(request),
            ),
            session=session,
            actor_id=current.admin.id,
            session_id=current.login_session.id,
        ),
        actor_id=current.admin.id,
    )


def get_user_distribution_service(
    request: Request,
    session: DatabaseSession,
    current: Annotated[CurrentUser, Depends(get_phone_user)],
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


def consumer_finance(session: DatabaseSession) -> ConsumerFinanceService:
    return ConsumerFinanceService(session)


def consumer_engagement(session: DatabaseSession) -> ConsumerEngagementService:
    return ConsumerEngagementService(session)


ConsumerFinance = Annotated[ConsumerFinanceService, Depends(consumer_finance)]
ConsumerEngagement = Annotated[ConsumerEngagementService, Depends(consumer_engagement)]
