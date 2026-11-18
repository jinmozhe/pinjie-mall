import argparse
import asyncio

from app.core.config import get_settings
from app.core.resources import create_resources
from app.services.durable_task_runner import DurableTaskRunner
from app.services.wechat_pay_client import WechatPayClient
from scripts._database_target import validate_database_target


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Preview or run one bounded durable-task worker batch")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-database", required=True)
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--lease-seconds", type=int, default=60)
    parser.add_argument("--retry-delay-seconds", type=int, default=60)
    parser.add_argument("--watch", action="store_true", help="Run bounded batches continuously until interrupted")
    parser.add_argument("--poll-seconds", type=int, default=5)
    return parser.parse_args()


async def run(args: argparse.Namespace) -> None:
    if not 1 <= args.limit <= 100:
        raise ValueError("--limit must be between 1 and 100")
    if not 1 <= args.lease_seconds <= 900:
        raise ValueError("--lease-seconds must be between 1 and 900")
    if not 1 <= args.retry_delay_seconds <= 900:
        raise ValueError("--retry-delay-seconds must be between 1 and 900")
    settings = get_settings()
    settings.validate_wechat_pay()
    if args.watch and (not args.apply or not 1 <= args.poll_seconds <= 60):
        raise ValueError("--watch requires --apply and --poll-seconds 1..60")
    validate_database_target(settings, args.confirm_database)
    resources = create_resources(settings)
    try:
        client = (
            await asyncio.to_thread(WechatPayClient, settings, resources.wechat_http)
            if settings.wechat_pay_active and resources.wechat_http is not None
            else None
        )
        runner = DurableTaskRunner(
            resources.session_factory,
            settings=settings,
            wechat_pay=client,
            wechat_http=resources.wechat_http,
            redis=resources.redis,
        )
        if not args.apply:
            print(f"due_durable_tasks={await runner.due_count()}; dry run only")
            return
        while True:
            result = await runner.run_once(
                limit=args.limit,
                lease_seconds=args.lease_seconds,
                retry_delay_seconds=args.retry_delay_seconds,
            )
            print(
                "durable_tasks="
                f"leased:{result.leased},succeeded:{result.succeeded},retried:{result.retried},"
                f"attention:{result.attention},lease_lost:{result.lease_lost},deferred:{result.deferred}",
                flush=True,
            )
            if not args.watch:
                break
            await asyncio.sleep(args.poll_seconds)
    finally:
        await resources.close()


def main() -> None:
    asyncio.run(run(arguments()))


if __name__ == "__main__":
    main()
