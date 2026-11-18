"""Recover one attention task after inspecting and fixing its cause."""

import argparse
import asyncio
from uuid import UUID

from app.core.config import get_settings
from app.core.resources import create_resources
from app.services.durable_task_recovery import recover_task
from scripts._database_target import validate_database_target


async def run(args: argparse.Namespace) -> None:
    settings = get_settings()
    validate_database_target(settings, args.confirm_database)
    resources = create_resources(settings)
    try:
        async with resources.session_factory() as session:
            print(
                await recover_task(
                    session,
                    task_id=args.task_id,
                    revision=args.revision,
                    operator=args.operator,
                    reason=args.reason,
                    apply=args.apply,
                    release_version=settings.release_version,
                )
            )
    finally:
        await resources.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-database", required=True)
    parser.add_argument("--task-id", required=True, type=UUID)
    parser.add_argument("--revision", required=True, type=int)
    parser.add_argument("--operator", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--apply", action="store_true")
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
