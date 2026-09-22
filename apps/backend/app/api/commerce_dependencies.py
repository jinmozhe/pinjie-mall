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
from app.domains.addresses.repository import AddressRepository
from app.domains.addresses.service import AddressService
from app.domains.inventory.repository import InventoryRepository
from app.domains.inventory.service import InventoryService
from app.domains.products.repository import ProductRepository
from app.domains.products.service import ProductService
from app.domains.shipping.repository import ShippingRepository
from app.domains.shipping.service import ShippingService
from app.services.commerce import AddressApplicationService, CommerceService
from app.services.security_events import AuditCoordinator


def get_public_commerce(session: DatabaseSession) -> CommerceService:
    return CommerceService(
        products=ProductService(ProductRepository(session)),
        inventory=InventoryService(InventoryRepository(session)),
        shipping=ShippingService(ShippingRepository(session)),
        access=CommerceAccessRepository(session),
    )


def get_admin_commerce(
    request: Request,
    session: DatabaseSession,
    current: Annotated[CurrentAdmin, Depends(get_current_admin)],
) -> CommerceService:
    return CommerceService(
        products=ProductService(ProductRepository(session)),
        inventory=InventoryService(InventoryRepository(session)),
        shipping=ShippingService(ShippingRepository(session)),
        access=CommerceAccessRepository(session),
        audit=AuditCoordinator(
            session=session,
            session_factory=get_resources(request).session_factory,
            actor_id=current.admin.id,
            metadata=request_metadata(request),
        ),
        actor_id=current.admin.id,
        actor_session_id=current.login_session.id,
    )


def get_addresses(
    session: DatabaseSession,
    current: Annotated[CurrentUser, Depends(get_current_user)],
) -> AddressApplicationService:
    return AddressApplicationService(
        session, AddressService(AddressRepository(session)), CommerceAccessRepository(session), current.user.id
    )


PublicCommerce = Annotated[CommerceService, Depends(get_public_commerce)]
AdminCommerce = Annotated[CommerceService, Depends(get_admin_commerce)]
UserAddresses = Annotated[AddressApplicationService, Depends(get_addresses)]
