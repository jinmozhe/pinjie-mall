"""真实 PostgreSQL 库存并发与回滚回归；仅显式授权 pytest 时运行，不自动迁移。"""

import asyncio
import os
from collections.abc import AsyncIterator
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.core.exceptions import AppException
from app.core.identifiers import new_uuid7
from app.db.models.inventory import InventoryAccount, InventoryMovement
from app.db.models.product import Category, Product, ProductSku
from app.db.transaction import transaction_scope
from app.domains.inventory.repository import InventoryRepository
from app.domains.inventory.schemas import InventoryAdjustment, InventoryMovementRead
from app.domains.inventory.service import InventoryService


@pytest.fixture
async def inventory_database() -> AsyncIterator[tuple[async_sessionmaker[AsyncSession], UUID]]:
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.fail("TEST_DATABASE_URL is required for commerce integration tests")
    settings = Settings(ENVIRONMENT="test", DATABASE_URL=database_url, TEST_DATABASE_URL=database_url)
    settings.validate_database_runtime()
    engine = create_async_engine(database_url, pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    category_id, product_id, sku_id = new_uuid7(), new_uuid7(), new_uuid7()
    try:
        async with sessions() as session, transaction_scope(session):
            session.add(Category(id=category_id, name="并发回归"))
            await session.flush()
            session.add(Product(id=product_id, name="并发回归", product_type="virtual", category_id=category_id))
            await session.flush()
            session.add(
                ProductSku(
                    id=sku_id,
                    product_id=product_id,
                    code=f"TEST-{sku_id}",
                    specifications={},
                    price=Decimal("1.00"),
                    weight_grams=0,
                )
            )
            await session.flush()
            session.add(InventoryAccount(sku_id=sku_id, available=10, reserved=0, revision=1))
        yield sessions, sku_id
    finally:
        try:
            async with sessions() as session, transaction_scope(session):
                await session.execute(delete(InventoryMovement).where(InventoryMovement.sku_id == sku_id))
                await session.execute(delete(InventoryAccount).where(InventoryAccount.sku_id == sku_id))
                await session.execute(delete(ProductSku).where(ProductSku.id == sku_id))
                await session.execute(delete(Product).where(Product.id == product_id))
                await session.execute(delete(Category).where(Category.id == category_id))
        finally:
            await engine.dispose()


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize("same_request", [True, False])
async def test_concurrent_inventory_adjustments_commit_only_once(inventory_database, same_request: bool) -> None:
    sessions, sku_id = inventory_database
    actor_id = new_uuid7()
    request = InventoryAdjustment(request_id=new_uuid7(), revision=1, quantity_delta=-3, reason="并发盘点")
    other = request if same_request else request.model_copy(update={"request_id": new_uuid7()})
    gate = asyncio.Event()
    ready = 0

    async def adjust(data: InventoryAdjustment) -> InventoryMovementRead:
        nonlocal ready
        async with sessions() as session, transaction_scope(session):
            ready += 1
            if ready == 2:
                gate.set()
            await gate.wait()
            return await InventoryService(InventoryRepository(session)).adjust(sku_id, data, actor_id)

    results = await asyncio.wait_for(asyncio.gather(adjust(request), adjust(other), return_exceptions=True), timeout=15)
    successes = [result for result in results if isinstance(result, InventoryMovementRead)]
    failures = [result for result in results if isinstance(result, BaseException)]
    if same_request:
        assert len(successes) == 2 and not failures
        assert successes[0].id == successes[1].id
    else:
        assert len(successes) == 1 and len(failures) == 1
        assert isinstance(failures[0], AppException)
        assert failures[0].code == "INVENTORY_REVISION_CONFLICT"
    async with sessions() as session:
        account = await session.scalar(select(InventoryAccount).where(InventoryAccount.sku_id == sku_id))
        assert account is not None
        assert (account.available, account.reserved, account.revision) == (7, 0, 2)
        count = await session.scalar(
            select(func.count()).select_from(InventoryMovement).where(InventoryMovement.sku_id == sku_id)
        )
        assert count == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_inventory_account_and_movement_rollback_together(inventory_database) -> None:
    sessions, sku_id = inventory_database
    request = InventoryAdjustment(request_id=new_uuid7(), revision=1, quantity_delta=-3, reason="回滚盘点")
    with pytest.raises(RuntimeError, match="abort after flush"):
        async with sessions() as session, transaction_scope(session):
            await InventoryService(InventoryRepository(session)).adjust(sku_id, request, new_uuid7())
            raise RuntimeError("abort after flush")
    async with sessions() as session:
        account = await session.scalar(select(InventoryAccount).where(InventoryAccount.sku_id == sku_id))
        assert account is not None
        assert (account.available, account.revision) == (10, 1)
        assert await session.scalar(select(InventoryMovement.id).where(InventoryMovement.sku_id == sku_id)) is None
