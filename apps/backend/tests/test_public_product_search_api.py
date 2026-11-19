from uuid import UUID

import pytest

from app.api.commerce_dependencies import get_public_commerce
from app.core.identifiers import new_uuid7
from app.core.pagination import PageResult
from app.domains.products.schemas import PublicProductRead


class PublicCatalogStub:
    """HTTP boundary substitute; the real query is covered by PostgreSQL integration cases."""

    def __init__(self) -> None:
        self.received: tuple[int, int, UUID | None, str | None] | None = None

    async def public_product_page(
        self, page: int, page_size: int, *, category_id: UUID | None = None, search: str | None = None
    ) -> PageResult[PublicProductRead]:
        self.received = (page, page_size, category_id, search)
        return PageResult[PublicProductRead].create(items=[], page=page, page_size=page_size, total=0)


@pytest.mark.asyncio
async def test_public_search_forwards_category_and_validates_keyword_without_authentication(client) -> None:
    from app.main import app

    service = PublicCatalogStub()
    category_id = new_uuid7()
    app.dependency_overrides[get_public_commerce] = lambda: service
    try:
        response = await client.get(
            "/api/v1/products",
            params={"page": 2, "page_size": 20, "category_id": str(category_id), "search": "  礼盒  "},
        )
        assert response.status_code == 200
        assert service.received == (2, 20, category_id, "  礼盒  ")
        assert response.json()["data"]["items"] == []
        service.received = None
        invalid = await client.get("/api/v1/products", params={"search": "礼" * 201})
        assert invalid.status_code == 422
        assert invalid.json()["code"] == "VALIDATION_ERROR"
        assert service.received is None
        omitted = await client.get("/api/v1/products")
        assert omitted.status_code == 200
        assert service.received == (1, 20, None, None)
    finally:
        app.dependency_overrides.pop(get_public_commerce, None)
