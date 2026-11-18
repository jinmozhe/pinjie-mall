"""仅供本机开发库使用的首页八个一级分类与彩色图标资产幂等初始化入口。"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import io
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import Settings, get_settings
from app.core.identifiers import new_uuid7
from app.core.restricted_html import restricted_html
from app.db.models.asset import Asset
from app.db.models.product import Category
from app.services.storage import LocalStorageProvider, StagedFile
from app.services.storage.images import inspect_image_bytes
from scripts._database_target import validate_database_target

BACKEND_ROOT = Path(__file__).resolve().parents[1]
SEED_PATH = BACKEND_ROOT / "scripts" / "data" / "home_categories.v1.json"
ICONS_DIR = BACKEND_ROOT / "scripts" / "data" / "category_icons"
LOCAL_DATABASE_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
LOCAL_SERVER_ADDRESSES = frozenset({"127.0.0.1", "::1"})
SUPPORTED_REVISIONS = frozenset({"20260929_01", "20261009_01", "20261013_01"})
MAX_ICON_BYTES = 2 * 1024 * 1024


class HomeCategoryItem(BaseModel):
    """单个首页一级分类种子定义。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    slug: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9-]+$")
    name: str = Field(min_length=1, max_length=100)
    sort_order: int = Field(ge=1, le=8)
    description: str = Field(min_length=1, max_length=20000)
    icon_filename: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9-]+\.png$")

    @model_validator(mode="after")
    def validate_description(self) -> HomeCategoryItem:
        # 确保持久化到分类表中的 HTML 简述符合受限 HTML 规范
        self.description = restricted_html(self.description)
        return self


class HomeCategorySeed(BaseModel):
    """首页一级分类与图标种子文件契约。"""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    dataset_version: str = Field(min_length=1, max_length=64)
    icon_size: Literal[160]
    categories: list[HomeCategoryItem] = Field(min_length=8, max_length=8)

    @model_validator(mode="after")
    def validate_unique(self) -> HomeCategorySeed:
        if len({item.slug for item in self.categories}) != len(self.categories):
            raise ValueError("分类 slug 不能重复")
        if len({item.name for item in self.categories}) != len(self.categories):
            raise ValueError("分类名称不能重复")
        if {item.sort_order for item in self.categories} != set(range(1, 9)):
            raise ValueError("分类排序权重必须严格覆盖 1 至 8")
        if len({item.icon_filename for item in self.categories}) != len(self.categories):
            raise ValueError("分类图标文件名不能重复")
        return self


def resolve_storage(settings: Settings) -> LocalStorageProvider:
    """将配置中的相对上传根目录固定解析到 Backend 应用目录，避免跨工作目录写偏。"""
    if settings.upload_storage_driver != "local":
        raise ValueError("仅支持本地文件存储驱动")
    root = settings.upload_local_root
    if not root.is_absolute():
        root = (BACKEND_ROOT / root).resolve()
    return LocalStorageProvider(root, io_concurrency=settings.upload_io_concurrency)


def load_seed_assets(seed: HomeCategorySeed) -> dict[str, tuple[bytes, str]]:
    """读取并解码核验本地 8 张高清分类图标 PNG，返回 (字节, sha256) 映射。"""
    loaded: dict[str, tuple[bytes, str]] = {}
    for item in seed.categories:
        icon_path = ICONS_DIR / item.icon_filename
        if not icon_path.is_file():
            raise ValueError(f"缺少分类图标文件：{icon_path}")
        payload = icon_path.read_bytes()
        if not payload or len(payload) > MAX_ICON_BYTES:
            raise ValueError(f"分类图标体积超出允许范围：{icon_path}")
        metadata = inspect_image_bytes(payload, "image/png")
        if metadata.width != seed.icon_size or metadata.height != seed.icon_size or metadata.frame_count != 1:
            raise ValueError(f"分类图标尺寸或帧数不符合 {seed.icon_size}x{seed.icon_size} 静态图要求：{icon_path}")
        loaded[item.slug] = (payload, hashlib.sha256(payload).hexdigest())
    return loaded


def validate_local_settings(settings: Settings, confirmed_database: str) -> URL:
    """严格核验仅允许在本机 local 开发库执行。"""
    if settings.database_url is None:
        raise ValueError("缺少 DATABASE_URL 配置")
    url = make_url(settings.database_url)
    if url.query:
        raise ValueError("DATABASE_URL 不允许附带查询参数")
    database_name = validate_database_target(settings, confirmed_database)
    if url.database is None or url.database != database_name:
        raise ValueError("DATABASE_URL 数据库名称与确认目标不一致")
    if (
        settings.environment != "local"
        or url.host not in LOCAL_DATABASE_HOSTS
        or url.drivername != "postgresql+asyncpg"
    ):
        raise ValueError("仅允许本机 local PostgreSQL 开发库")
    if url.database.endswith("_test"):
        raise ValueError("本脚本不允许操作测试库")
    return url


async def verify_connected_target(connection: AsyncConnection, url: URL) -> None:
    """核实真实连接的 PostgreSQL 实例与数据库名称。"""
    target = (
        (
            await connection.execute(
                text(
                    "SELECT current_database() AS database_name, "
                    "host(inet_server_addr()) AS server_address, inet_server_port() AS server_port"
                )
            )
        )
        .mappings()
        .one()
    )
    if (
        target["database_name"] != url.database
        or target["server_address"] not in LOCAL_SERVER_ADDRESSES
        or target["server_port"] != (url.port or 5432)
    ):
        raise ValueError("实际连接目标与已确认本机开发库不一致")
    revisions = list((await connection.execute(text("SELECT version_num FROM public.alembic_version"))).scalars())
    if not revisions or revisions[0] not in SUPPORTED_REVISIONS:
        raise ValueError("数据库迁移版本不在支持范围，请先确认 Alembic 版本")


async def inspect_state(
    session: AsyncSession,
    storage: LocalStorageProvider,
    seed: HomeCategorySeed,
    icons: dict[str, tuple[bytes, str]],
) -> dict[str, object]:
    """只读检查当前分类表、资产表和本地磁盘文件匹配状态。"""
    all_categories = list(
        await session.scalars(select(Category).order_by(Category.sort_order.asc().nulls_last(), Category.id.desc()))
    )
    top_by_name = {row.name: row for row in all_categories if row.parent_id is None}
    asset_ids = {row.icon_asset_id for row in all_categories if row.icon_asset_id is not None}
    assets_by_id: dict[UUID, Asset] = {}
    if asset_ids:
        for asset_row in await session.scalars(select(Asset).where(Asset.id.in_(asset_ids))):
            assets_by_id[asset_row.id] = asset_row

    items_status: list[dict[str, object]] = []
    ready_count = 0
    for item in seed.categories:
        _, expected_hash = icons[item.slug]
        category = top_by_name.get(item.name)
        asset = assets_by_id.get(category.icon_asset_id) if category and category.icon_asset_id else None
        file_exists = await storage.exists(asset.file_key) if asset is not None else False
        is_synced = (
            category is not None
            and category.is_active is True
            and category.sort_order == item.sort_order
            and category.description == item.description
            and asset is not None
            and asset.file_hash == expected_hash
            and file_exists
        )
        if is_synced:
            ready_count += 1
        items_status.append(
            {
                "sort_order": item.sort_order,
                "name": item.name,
                "exists": category is not None,
                "current_sort_order": category.sort_order if category else None,
                "is_active": category.is_active if category else None,
                "has_icon_asset": asset is not None,
                "icon_hash_matched": asset is not None and asset.file_hash == expected_hash,
                "icon_file_exists": file_exists,
                "synced": is_synced,
                "icon_url": asset.url if asset else None,
            }
        )

    other_top = [
        {"name": row.name, "sort_order": row.sort_order, "is_active": row.is_active}
        for row in all_categories
        if row.parent_id is None and row.name not in {item.name for item in seed.categories}
    ]
    return {
        "total_categories": len(all_categories),
        "synced_count": ready_count,
        "expected_count": len(seed.categories),
        "all_synced": ready_count == len(seed.categories),
        "target_categories": items_status,
        "other_top_categories": other_top,
    }


async def apply_seed(
    session: AsyncSession,
    settings: Settings,
    storage: LocalStorageProvider,
    seed: HomeCategorySeed,
    icons: dict[str, tuple[bytes, str]],
) -> dict[str, int]:
    """在单一事务内幂等写入 8 个图标资产与 8 个一级分类，同时保护既有分类与商品。"""
    await session.execute(text("SELECT pg_advisory_xact_lock(722341901)"))
    all_categories = list(
        await session.scalars(
            select(Category).order_by(Category.sort_order.asc().nulls_last(), Category.id.desc()).with_for_update()
        )
    )
    target_names = {item.name for item in seed.categories}

    # 若非目标列表中的既有顶级分类占用了 1..8 排序位置，顺延其排序权重到 9 及之后并保留原记录
    other_top_categories = [row for row in all_categories if row.parent_id is None and row.name not in target_names]
    max_existing_sort = max((row.sort_order for row in other_top_categories if row.sort_order is not None), default=8)
    next_shifted_sort = max(9, max_existing_sort + 1)
    shifted_count = 0
    for row in other_top_categories:
        if row.sort_order is not None and 1 <= row.sort_order <= 8:
            row.sort_order = next_shifted_sort
            row.revision += 1
            next_shifted_sort += 1
            shifted_count += 1

    top_by_name = {row.name: row for row in all_categories if row.parent_id is None}
    date_bucket = datetime.now(UTC).strftime("%Y%m%d")

    created_assets = 0
    repaired_files = 0
    created_categories = 0
    updated_categories = 0
    staged_items: list[tuple[StagedFile, str]] = []

    try:
        for item in seed.categories:
            png_bytes, file_hash = icons[item.slug]
            existing_asset = await session.scalar(
                select(Asset)
                .where(
                    Asset.uploader_type == "system",
                    Asset.uploader_id.is_(None),
                    Asset.scene == "product",
                    Asset.file_hash == file_hash,
                )
                .order_by(Asset.id)
                .limit(1)
            )
            if existing_asset is not None:
                asset_id = existing_asset.id
                if not await storage.exists(existing_asset.file_key):
                    staged = await storage.stage(
                        io.BytesIO(png_bytes),
                        extension="png",
                        max_bytes=MAX_ICON_BYTES,
                        inspect_image=True,
                    )
                    staged_items.append((staged, existing_asset.file_key))
                    repaired_files += 1
            else:
                asset_id = new_uuid7()
                file_key = f"product/{date_bucket}/{file_hash[:16]}_{asset_id.hex}.png"
                staged = await storage.stage(
                    io.BytesIO(png_bytes),
                    extension="png",
                    max_bytes=MAX_ICON_BYTES,
                    inspect_image=True,
                )
                staged_items.append((staged, file_key))
                asset = Asset(
                    id=asset_id,
                    uploader_type="system",
                    uploader_id=None,
                    storage_driver=storage.driver,
                    file_key=file_key,
                    original_name=item.icon_filename,
                    mime_type=staged.mime_type,
                    file_size=staged.file_size,
                    width=staged.image.width if staged.image else seed.icon_size,
                    height=staged.image.height if staged.image else seed.icon_size,
                    frame_count=staged.image.frame_count if staged.image else 1,
                    file_hash=file_hash,
                    url=f"{settings.upload_base_url}/{file_key}",
                    scene="product",
                )
                session.add(asset)
                created_assets += 1

            category = top_by_name.get(item.name)
            if category is None:
                session.add(
                    Category(
                        id=new_uuid7(),
                        name=item.name,
                        parent_id=None,
                        icon_asset_id=asset_id,
                        description=item.description,
                        sort_order=item.sort_order,
                        is_active=True,
                        revision=1,
                    )
                )
                created_categories += 1
            else:
                changed = False
                if category.icon_asset_id != asset_id:
                    category.icon_asset_id = asset_id
                    changed = True
                if category.description != item.description:
                    category.description = item.description
                    changed = True
                if category.sort_order != item.sort_order:
                    category.sort_order = item.sort_order
                    changed = True
                if not category.is_active:
                    category.is_active = True
                    changed = True
                if changed:
                    category.revision += 1
                    updated_categories += 1

        # 事务提交前将暂存的图片原子提交到磁盘；若后续数据库提交失败则不会进入数据库引用
        for staged, file_key in staged_items:
            await storage.commit(staged, file_key=file_key)
        staged_items.clear()
        await session.flush()
    except BaseException:
        for staged, _ in staged_items:
            await storage.discard(staged)
        raise

    return {
        "created_assets": created_assets,
        "repaired_files": repaired_files,
        "created_categories": created_categories,
        "updated_categories": updated_categories,
        "shifted_other_categories": shifted_count,
    }


async def run(args: argparse.Namespace) -> None:
    seed = HomeCategorySeed.model_validate_json(SEED_PATH.read_bytes())
    icons = load_seed_assets(seed)
    settings = get_settings()
    url = validate_local_settings(settings, args.confirm_database)
    storage = resolve_storage(settings)

    engine = create_async_engine(
        url,
        connect_args={
            "server_settings": {
                "search_path": "public",
                "lock_timeout": "10000",
                "statement_timeout": "30000",
            }
        },
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    try:
        if not args.apply:
            async with session_factory() as session:
                async with session.begin():
                    await session.execute(text("SET TRANSACTION READ ONLY"))
                    connection = await session.connection()
                    await verify_connected_target(connection, url)
                    state = await inspect_state(session, storage, seed, icons)
            print(json.dumps({"mode": "check", "database": url.database, **state}, ensure_ascii=False, indent=2))
            return

        async with session_factory() as session:
            async with session.begin():
                connection = await session.connection()
                await verify_connected_target(connection, url)
                summary = await apply_seed(session, settings, storage, seed, icons)

        # 使用新的只读会话独立复核提交后的持久化结果与公开排序顺序
        await engine.dispose()
        async with session_factory() as verify_session:
            async with verify_session.begin():
                await verify_session.execute(text("SET TRANSACTION READ ONLY"))
                connection = await verify_session.connection()
                await verify_connected_target(connection, url)
                state = await inspect_state(verify_session, storage, seed, icons)
                top_eight = list(
                    await verify_session.scalars(
                        select(Category.name)
                        .where(Category.parent_id.is_(None), Category.is_active.is_(True))
                        .order_by(Category.sort_order.asc().nulls_last(), Category.id.desc())
                        .limit(8)
                    )
                )
        expected_names = [item.name for item in sorted(seed.categories, key=lambda row: row.sort_order)]
        if not state["all_synced"] or top_eight != expected_names:
            raise ValueError(f"独立核验失败：预期前 8 类目 {expected_names}，实际 {top_eight}")
        print(
            json.dumps(
                {"mode": "apply", "database": url.database, "summary": summary, "verified_top_eight": top_eight},
                ensure_ascii=False,
                indent=2,
            )
        )
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="只读检查当前开发库分类与图标同步状态")
    mode.add_argument("--apply", action="store_true", help="幂等创建或更新 8 个一级分类与彩色图标资产")
    parser.add_argument("--confirm-database", required=True, help="必须与当前 DATABASE_URL 的数据库名称完全一致")
    args = parser.parse_args()
    try:
        asyncio.run(run(args))
    except ValueError as exc:
        parser.exit(1, f"首页分类初始化拒绝：{exc}\n")
    except Exception as exc:
        # 防止驱动异常打印敏感连接信息
        parser.exit(1, f"首页分类初始化失败：{type(exc).__name__}。请检查本机数据库与存储状态。\n")


if __name__ == "__main__":
    main()
