import argparse
import asyncio
from datetime import UTC, datetime

from app.core.config import get_settings
from app.core.resources import create_resources
from app.domains.lifecycle.repository import LifecycleRepository
from app.domains.lifecycle.service import LifecycleService
from scripts._database_target import validate_database_target


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Preview or auto-confirm shipped physical fulfillments")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-database", required=True)
    parser.add_argument("--limit", type=int, default=100)
    return parser.parse_args()


async def run(args: argparse.Namespace) -> None:
    if not 1 <= args.limit <= 1000:
        raise ValueError("--limit must be between 1 and 1000")
    settings = get_settings()
    validate_database_target(settings, args.confirm_database)
    resources = create_resources(settings)
    try:
        async with resources.session_factory() as session:
            repository = LifecycleRepository(session)
            if not args.apply:
                count = await repository.count_due_fulfillments(datetime.now(UTC))
                print(f"due_fulfillments={count}; dry run only")
                return
            completed = await LifecycleService(session, repository).auto_confirm_due(args.limit)
            print(f"auto_confirmed_fulfillments={completed}; apply completed")
    finally:
        await resources.close()


def main() -> None:
    asyncio.run(run(arguments()))


if __name__ == "__main__":
    main()
