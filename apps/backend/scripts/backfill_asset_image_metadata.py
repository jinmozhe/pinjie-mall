"""Inspect or explicitly backfill one bounded batch of product image metadata."""

import argparse
import asyncio
from collections import Counter
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.core.resources import create_resources
from app.db.repositories.asset import AssetRepository
from app.services.asset_image_backfill import AssetImageBackfill
from app.services.storage import create_storage_provider
from scripts._database_target import validate_database_target


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="检查或回填商品图片尺寸，不修改图片文件")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="只读检查，默认模式")
    mode.add_argument("--apply", action="store_true", help="显式写入已核验的图片尺寸")
    parser.add_argument("--confirm-database", required=True)
    parser.add_argument("--asset-id", action="append", type=UUID, default=[])
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    if not 1 <= args.limit <= 100 or len(args.asset_id) > 100 or len(set(args.asset_id)) != len(args.asset_id):
        parser.error("每批 1 至 100 项，资产 ID 不能重复")
    return args


async def _run(args: argparse.Namespace) -> int:
    settings = get_settings()
    validate_database_target(settings, args.confirm_database)
    resources = create_resources(settings)
    try:
        storage = create_storage_provider(settings)
        if args.asset_id:
            if len(args.asset_id) > args.limit:
                raise ValueError("明确指定的资产数量超过 --limit")
            ids = sorted(args.asset_id)
        else:
            async with resources.session_factory() as session:
                ids = [
                    asset.id
                    for asset in await AssetRepository(session).images_missing_metadata(
                        asset_ids=[],
                        limit=args.limit,
                    )
                ]
        service = AssetImageBackfill(resources.session_factory, storage)
        counts: Counter[str] = Counter()
        for asset_id in ids:
            result = await service.run_one(asset_id, apply=args.apply)
            counts[result.status] += 1
            print(f"asset_id={result.asset_id} status={result.status}")
        print("mode=" + ("apply" if args.apply else "check") + f" selected={len(ids)} counts={dict(counts)}")
        return 1 if any(status not in {"updated", "already_complete"} for status in counts) else 0
    except SQLAlchemyError:
        print("数据库操作失败；未完成批次不得视为成功，请通过服务日志核查。")
        return 1
    finally:
        await resources.close()


def main() -> None:
    raise SystemExit(asyncio.run(_run(_arguments())))


if __name__ == "__main__":
    main()
