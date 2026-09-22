from typing import Annotated

from fastapi import Depends, Request

from app.api.dependencies import CurrentAdmin, DatabaseSession, get_current_admin, get_resources
from app.core.request_metadata import request_metadata
from app.domains.commissioning import CommissionPolicyService
from app.services.security_events import AuditCoordinator


def get_admin_commission_policy_service(
    request: Request,
    session: DatabaseSession,
    current: Annotated[CurrentAdmin, Depends(get_current_admin)],
) -> CommissionPolicyService:
    return CommissionPolicyService(
        session=session,
        actor_id=current.admin.id,
        audit=AuditCoordinator(
            session=session,
            session_factory=get_resources(request).session_factory,
            actor_id=current.admin.id,
            metadata=request_metadata(request),
        ),
    )


AdminCommissionPolicies = Annotated[CommissionPolicyService, Depends(get_admin_commission_policy_service)]

__all__ = ["AdminCommissionPolicies"]
