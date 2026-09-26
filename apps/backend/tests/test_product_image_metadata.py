"""商品图片元数据、详情预算与锁序的回归源码；实际执行须明确授权 pytest。"""

import asyncio
import hashlib
import io
import threading
from types import SimpleNamespace
from uuid import UUID

import pytest
from PIL import Image

from app.core.identifiers import new_uuid7
from app.domains.products.image_policy import validate_detail_images
from app.domains.products.schemas import ProductImageRead, ProductUpdate
from app.services.storage import LocalStorageProvider
from app.services.storage.images import ImageMetadata, inspect_image_bytes


def image_bytes(fmt="PNG", *, orientation=1, animated=False):
    output = io.BytesIO()
    image = Image.new("RGB", (12, 8), "red")
    kwargs = {}
    if fmt == "JPEG":
        exif = Image.Exif()
        exif[274] = orientation
        kwargs["exif"] = exif
    if animated:
        kwargs.update(save_all=True, append_images=[Image.new("RGB", (12, 8), "blue")], duration=100)
    image.save(output, format=fmt, **kwargs)
    return output.getvalue()


@pytest.mark.parametrize(("fmt", "mime"), [("PNG", "image/png"), ("JPEG", "image/jpeg"), ("WEBP", "image/webp")])
def test_complete_image_decode_and_mime(fmt, mime):
    payload = image_bytes(fmt)
    assert inspect_image_bytes(payload, mime) == ImageMetadata(12, 8, 1)
    with pytest.raises(ValueError):
        inspect_image_bytes(payload, "image/jpeg" if fmt != "JPEG" else "image/png")
    with pytest.raises(ValueError):
        inspect_image_bytes(payload[:20], mime)


def test_orientation_and_animation_are_recorded():
    assert inspect_image_bytes(image_bytes("JPEG", orientation=6), "image/jpeg") == ImageMetadata(8, 12, 1)
    assert inspect_image_bytes(image_bytes(animated=True), "image/png").frame_count == 2


def test_image_decode_resource_limits_are_enforced():
    output = io.BytesIO()
    Image.new("1", (8193, 1)).save(output, format="PNG")
    with pytest.raises(ValueError, match="resource"):
        inspect_image_bytes(output.getvalue(), "image/png")
    output = io.BytesIO()
    Image.new("1", (5000, 4001)).save(output, format="PNG")
    with pytest.raises(ValueError, match="resource"):
        inspect_image_bytes(output.getvalue(), "image/png")


async def test_image_decode_queue_is_bounded(tmp_path, monkeypatch):
    from app.services.storage import local

    provider = LocalStorageProvider(tmp_path / "uploads", io_concurrency=2)
    payload = image_bytes()
    started = threading.Event()
    release = threading.Event()
    original = local.inspect_image_bytes

    def blocked(payload: bytes, mime_type: str) -> ImageMetadata:
        started.set()
        assert release.wait(timeout=5)
        return original(payload, mime_type)

    monkeypatch.setattr(local, "_IMAGE_DECODE_QUEUE_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(local, "inspect_image_bytes", blocked)
    first = asyncio.create_task(
        provider.stage(io.BytesIO(payload), extension="png", max_bytes=1024, inspect_image=True)
    )
    assert await asyncio.to_thread(started.wait, 1)
    with pytest.raises(ValueError, match="image_decode_busy"):
        await provider.stage(io.BytesIO(payload), extension="png", max_bytes=1024, inspect_image=True)
    release.set()
    assert (await first).image == ImageMetadata(12, 8, 1)


def detail_image(**changes):
    values = dict(
        asset_id=new_uuid7(),
        url="/static/uploads/product/test.png",
        original_name="test.png",
        file_size=2 * 1024 * 1024,
        width=2000,
        height=4000,
        frame_count=1,
    )
    return ProductImageRead(**(values | changes))


@pytest.mark.parametrize(
    "changes",
    [
        {"file_size": 2 * 1024 * 1024 + 1},
        {"width": 4097, "height": 1},
        {"width": 2001},
        {"width": None},
        {"height": None},
        {"frame_count": None},
        {"frame_count": 2},
    ],
)
def test_detail_policy_rejects_untrusted_or_over_budget(changes):
    with pytest.raises(ValueError):
        validate_detail_images([detail_image(**changes)])


def test_detail_total_count_duplicate_and_boundary():
    validate_detail_images([detail_image() for _ in range(10)])
    with pytest.raises(ValueError, match="总体积"):
        validate_detail_images([detail_image() for _ in range(11)])
    with pytest.raises(ValueError, match="最多"):
        validate_detail_images([detail_image(file_size=1) for _ in range(21)])
    image = detail_image()
    with pytest.raises(ValueError, match="重复"):
        validate_detail_images([image, image])
    validate_detail_images([])


def test_update_must_explicitly_preserve_or_clear_detail_images():
    from pydantic import ValidationError

    data = dict(name="商品", category_id=new_uuid7(), product_type="virtual", revision=1)
    with pytest.raises(ValidationError):
        ProductUpdate(**data)
    assert ProductUpdate(**data, detail_image_asset_ids=[]).detail_image_asset_ids == []


async def test_batch_publish_locks_all_image_assets_once_in_uuid_order():
    from app.services.commerce import CommerceService

    first_product, second_product = UUID(int=1), UUID(int=2)
    first_asset, second_asset = UUID(int=11), UUID(int=12)
    product_rows = {
        first_product: SimpleNamespace(image_asset_ids=[second_asset], detail_image_asset_ids=[]),
        second_product: SimpleNamespace(image_asset_ids=[], detail_image_asset_ids=[first_asset]),
    }

    class ProductProbe:
        async def lock_changes(self):
            return None

        async def detail_read(self, product_id):
            return product_rows[product_id]

        async def set_status(self, product_id, data):
            return None

    class AccessProbe:
        def __init__(self):
            self.calls = []

        async def get_images_for_update(self, asset_ids):
            self.calls.append(asset_ids)
            return [
                SimpleNamespace(
                    id=asset_id,
                    uploader_type="system",
                    scene="product",
                    mime_type="image/png",
                    url="/static/uploads/product/test.png",
                    original_name="test.png",
                    file_size=1,
                    width=1,
                    height=1,
                    frame_count=1,
                )
                for asset_id in asset_ids
            ]

    class AuditProbe:
        async def execute(self, *, operation, **kwargs):
            return await operation()

    access = AccessProbe()
    service = CommerceService(
        products=ProductProbe(), inventory=None, shipping=None, access=access, audit=AuditProbe(), actor_id=UUID(int=99)
    )
    batch = SimpleNamespace(
        status="on_sale",
        targets=[SimpleNamespace(id=second_product, revision=1), SimpleNamespace(id=first_product, revision=1)],
    )
    completed = await service.products_status_batch(batch)
    assert completed.completed_count == 2
    assert access.calls == [[first_asset, second_asset]]


async def test_storage_stages_metadata_and_verifies_historical_bytes(tmp_path):
    provider = LocalStorageProvider(tmp_path / "uploads", io_concurrency=1)
    payload = image_bytes()
    staged = await provider.stage(io.BytesIO(payload), extension="png", max_bytes=1024, inspect_image=True)
    assert staged.image == ImageMetadata(12, 8, 1)
    await provider.commit(staged, file_key="product/test.png")
    arguments = dict(expected_hash=hashlib.sha256(payload).hexdigest(), mime_type="image/png", max_bytes=len(payload))
    assert await provider.inspect_image("product/test.png", **arguments) == staged.image
    with pytest.raises(ValueError, match="hash"):
        await provider.inspect_image("product/test.png", **(arguments | {"expected_hash": "0" * 64}))
    with pytest.raises(ValueError, match="size"):
        await provider.inspect_image("product/test.png", **(arguments | {"max_bytes": len(payload) + 1}))
    with pytest.raises(ValueError, match="escapes"):
        await provider.inspect_image("../outside.png", **arguments)
    with pytest.raises(ValueError):
        await provider.stage(io.BytesIO(payload[:20]), extension="png", max_bytes=1024, inspect_image=True)
    assert not list((tmp_path / ".uploads-staging").iterdir())
