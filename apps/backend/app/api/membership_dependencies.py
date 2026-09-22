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
from app.domains.membership.service import MembershipService
from app.domains.points.service import PointsService
from app.services.security_events import AuditCoordinator


def get_membership_service(session: DatabaseSession) -> MembershipService:
    return MembershipService(session=session)


def get_admin_membership_service(
    request: Request,
    session: DatabaseSession,
    current: Annotated[CurrentAdmin, Depends(get_current_admin)],
) -> MembershipService:
    return MembershipService(
        session=session,
        actor_id=current.admin.id,
        audit=AuditCoordinator(
            session=session,
            session_factory=get_resources(request).session_factory,
            actor_id=current.admin.id,
            metadata=request_metadata(request),
        ),
    )


Membership = Annotated[MembershipService, Depends(get_membership_service)]
AdminMembership = Annotated[MembershipService, Depends(get_admin_membership_service)]
UserMembership = Annotated[CurrentUser, Depends(get_current_user)]


def get_admin_points_service(
    request: Request,
    session: DatabaseSession,
    current: Annotated[CurrentAdmin, Depends(get_current_admin)],
) -> PointsService:
    return PointsService(
        session=session,
        actor_id=current.admin.id,
        audit=AuditCoordinator(
            session=session,
            session_factory=get_resources(request).session_factory,
            actor_id=current.admin.id,
            metadata=request_metadata(request),
        ),
    )


AdminPoints = Annotated[PointsService, Depends(get_admin_points_service)]

__all__ = ["AdminMembership", "AdminPoints", "Membership", "UserMembership"]
