"""管理查询的真实路由权限回归，业务服务使用边界替身；执行需 pytest 授权。"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.dependencies import get_current_admin, get_db_session
from app.api.lifecycle_dependencies import get_lifecycle_service
from app.api.transaction_dependencies import get_order_service
from app.core.config import Settings
from app.core.identifiers import new_uuid7
from app.core.pagination import PageResult
from app.domains.lifecycle import FulfillmentRead, RefundRequestRead
from app.domains.orders import OrderRead
from app.domains.orders.schemas import AdminOrderSummary
from app.main import create_app


class ReadService:
    def __init__(self):
        self.order_id = new_uuid7()
        self.calls = 0

    async def admin_page(self, page, page_size):
        self.calls += 1
        return PageResult[AdminOrderSummary].create(items=[], total=0, page=page, page_size=page_size)

    async def admin_read(self, order_id):
        self.calls += 1
        now = datetime.now(UTC)
        return OrderRead(
            id=order_id,
            status="pending_payment",
            product_type="virtual",
            items_amount=Decimal("1"),
            freight_amount=Decimal("0"),
            total_amount=Decimal("1"),
            address_snapshot=None,
            expires_at=now + timedelta(minutes=30),
            created_at=now,
            revision=1,
            items=[],
        )

    async def admin_refunds(self, page, page_size):
        self.calls += 1
        return PageResult[RefundRequestRead].create(items=[], total=0, page=page, page_size=page_size)

    async def admin_fulfillment(self, order_id):
        self.calls += 1
        return FulfillmentRead(
            id=new_uuid7(),
            order_id=order_id,
            product_type="virtual",
            status="awaiting_delivery",
            carrier=None,
            tracking_number=None,
            delivery_reference=None,
            shipped_at=None,
            delivered_at=None,
            auto_confirm_at=None,
            revision=1,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("route", "permission"),
    [
        ("/admin/orders", "orders:read"),
        ("/admin/orders/{id}", "orders:read"),
        ("/admin/orders/{id}/fulfillment", "orders:read"),
        ("/admin/refunds", "refunds:read"),
    ],
)
@pytest.mark.parametrize(("identity", "expected"), [("missing", 401), ("wrong_permission", 403), ("allowed", 200)])
async def test_management_read_requires_exact_permission(route, permission, identity, expected):
    app = create_app(Settings.model_construct(log_file_enabled=False))
    service = ReadService()

    async def session():
        yield object()

    app.dependency_overrides[get_db_session] = session
    app.dependency_overrides[get_order_service] = lambda: service
    app.dependency_overrides[get_lifecycle_service] = lambda: service
    if identity != "missing":
        app.dependency_overrides[get_current_admin] = lambda: SimpleNamespace(
            permissions=frozenset({permission if identity == "allowed" else "products:read"})
        )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get("/api/v1" + route.format(id=service.order_id))
    assert response.status_code == expected
    assert service.calls == (1 if expected == 200 else 0)
    if expected != 200:
        assert response.json()["code"] == ("AUTH_REQUIRED" if expected == 401 else "PERMISSION_DENIED")


@pytest.mark.asyncio
async def test_management_list_rejects_unbounded_page_size():
    app = create_app(Settings.model_construct(log_file_enabled=False))
    service = ReadService()
    app.dependency_overrides[get_order_service] = lambda: service
    app.dependency_overrides[get_current_admin] = lambda: SimpleNamespace(permissions=frozenset({"orders:read"}))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get("/api/v1/admin/orders?page_size=101")
    assert response.status_code == 422
    assert service.calls == 0
