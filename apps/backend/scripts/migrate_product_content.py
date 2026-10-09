import argparse
import asyncio
from uuid import UUID

from app.core.config import get_settings
from app.core.resources import create_resources
from app.services.product_content_migration import ProductContentMigration
from scripts._database_target import validate_database_target


async def run(args: argparse.Namespace) -> None:
    settings = get_settings()
    validate_database_target(settings, args.confirm_database)
    resources = create_resources(settings)
    try:
        async with resources.session_factory() as session:
            ids = await ProductContentMigration(session).run(
                args.product_id, source=args.source_format, apply=args.apply
            )
        print(f"mode={'apply' if args.apply else 'dry-run'} validated={len(ids)}")
    finally:
        await resources.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="显式迁移受限商品说明，默认 dry-run；不输出内容")
    parser.add_argument("--confirm-database", required=True)
    parser.add_argument("--product-id", type=UUID, action="append", required=True)
    parser.add_argument("--source-format", choices=["text", "html"], required=True)
    parser.add_argument("--apply", action="store_true")
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
