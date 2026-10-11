"""已确认静态问题的回归场景；动态执行遵守项目授权边界。"""

import asyncio
import os
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid7

import pytest

from app.core.exceptions import AppException
from app.domains.lifecycle.schemas import RefundReview
from app.domains.products.repository import ProductRepository
from app.domains.products.service import ProductService
from app.services.payment_lifecycle import LifecycleService
from app.services.storage import LocalStorageProvider


@pytest.mark.asyncio
@pytest.mark.parametrize("before_move", [False, True])
async def test_deletion_journal_recovers_across_provider_restart(tmp_path: Path, before_move: bool) -> None:
    root = tmp_path / "uploads"
    root.mkdir()
    original = root / "image.png"
    original.write_bytes(b"original-image")
    storage = LocalStorageProvider(root, io_concurrency=1)
    deletion = await storage.stage_delete("image.png")
    if before_move:
        os.replace(deletion.token, original)  # Crash after journal publication, before moving the original.
    restarted = LocalStorageProvider(root, io_concurrency=1)
    assert await restarted.pending_deletions() == [deletion]
    await restarted.restore(deletion)
    await restarted.restore(deletion)
    assert original.read_bytes() == b"original-image"
    assert await restarted.pending_deletions() == []
    deletion = await restarted.stage_delete("image.png")
    await restarted.purge(deletion)
    await restarted.purge(deletion)
    assert not original.exists()
    assert await restarted.pending_deletions() == []


@pytest.mark.asyncio
async def test_restore_never_overwrites_replacement_bytes(tmp_path: Path) -> None:
    root = tmp_path / "uploads"
    root.mkdir()
    original = root / "image.png"
    original.write_bytes(b"old")
    storage = LocalStorageProvider(root, io_concurrency=1)
    deletion = await storage.stage_delete("image.png")
    original.write_bytes(b"replacement")
    with pytest.raises(OSError, match="different content"):
        await storage.restore(deletion)
    assert original.read_bytes() == b"replacement"
    assert Path(deletion.token).read_bytes() == b"old"
    assert await storage.pending_deletions() == [deletion]


@pytest.mark.asyncio
async def test_cancelled_delete_waits_for_thread_and_restores_bytes(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "uploads"
    root.mkdir()
    original = root / "image.png"
    original.write_bytes(b"image")
    storage = LocalStorageProvider(root, io_concurrency=1)
    staged = asyncio.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()
    stage = storage._stage_delete_sync

    def slow_stage(key):
        result = stage(key)
        loop.call_soon_threadsafe(staged.set)
        if not release.wait(5):
            raise TimeoutError("test failed to release file worker")
        return result

    monkeypatch.setattr(storage, "_stage_delete_sync", slow_stage)
    task = asyncio.create_task(storage.stage_delete("image.png"))
    try:
        await asyncio.wait_for(staged.wait(), timeout=5)
        task.cancel()
    finally:
        release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert original.read_bytes() == b"image"
    assert await storage.pending_deletions() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["approve_refund_in_open_transaction", "reject_refund_in_open_transaction"])
async def test_refund_review_locks_order_first_and_rechecks_after_lock(action) -> None:
    order_id, refund_id = uuid7(), uuid7()
    locks = []

    async def refund(_id, *, lock=False):
        if lock:
            locks.append("refund")
        return SimpleNamespace(
            id=refund_id, order_id=order_id, status="rejected" if lock else "requested", revision=2 if lock else 1
        )

    async def order(_id, *, lock=False):
        assert _id == order_id and lock
        locks.append("order")
        return SimpleNamespace(id=order_id)

    repository = SimpleNamespace(refund=AsyncMock(side_effect=refund), save=AsyncMock())
    service = LifecycleService(AsyncMock(), repository=repository, orders=SimpleNamespace(order=order))
    with pytest.raises(AppException) as conflict:
        await getattr(service, action)(refund_id, RefundReview(revision=1, note="审核"), uuid7())
    assert conflict.value.status_code == 409
    assert locks == ["order", "refund"]
    repository.save.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("size", [1, 20])
async def test_public_product_page_uses_shared_queries_for_all_skus(size) -> None:
    category_id = uuid7()
    products = [
        SimpleNamespace(
            id=uuid7(),
            name="商品",
            status="on_sale",
            description="",
            description_version=1,
            product_type="physical",
            category_id=category_id,
            brand_id=None,
        )
        for _ in range(size)
    ]
    skus = [
        SimpleNamespace(
            id=uuid7(),
            product_id=product.id,
            code=f"sku-{index}",
            sku_no=index + 1,
            archived_at=None,
            is_active=True,
            specifications={},
            price="1.00",
            market_price=None,
            wholesale_prices=[],
            weight_grams=None,
        )
        for product in products
        for index in range(5)
    ]
    session = AsyncMock()
    session.scalars.side_effect = [[], [], [], [], skus]
    session.execute.return_value = []
    repository = ProductRepository(session)
    repository.page = AsyncMock(return_value=(products, size))
    repository.categories = AsyncMock(return_value=[SimpleNamespace(id=category_id, parent_id=None, is_active=True)])
    result = await ProductService(repository).public_page(1, 20)
    assert len(result.items) == size and all(len(item.skus) == 5 for item in result.items)
    assert session.scalars.await_count == 5
    assert session.execute.await_count == 1
    repository.categories.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("database_committed", [False, True])
async def test_startup_recovery_uses_committed_asset_existence(tmp_path, monkeypatch, database_committed) -> None:
    from app.core.config import Settings
    from app.services import assets

    root = tmp_path / "uploads"
    root.mkdir()
    original = root / "image.png"
    original.write_bytes(b"image")
    storage = LocalStorageProvider(root, io_concurrency=1)
    await storage.stage_delete("image.png")
    repository = SimpleNamespace(get_by_file_key=AsyncMock(return_value=None if database_committed else object()))
    monkeypatch.setattr(assets, "AssetRepository", lambda session: repository)
    monkeypatch.setattr(assets, "create_storage_provider", lambda settings: storage)
    session = AsyncMock()
    session.__aenter__.return_value = session
    await assets.recover_asset_deletions(
        session_factory=MagicMock(return_value=session), settings=Settings.model_construct()
    )
    assert original.exists() is (not database_committed)
    repository.get_by_file_key.assert_awaited_once_with("image.png", for_update=True)
    assert await storage.pending_deletions() == []
