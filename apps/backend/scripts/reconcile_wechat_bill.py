"""Explicit, bounded daily reconciliation. No credentials or raw bills are printed."""

import argparse
import asyncio
from datetime import date, datetime, timedelta, timezone

from app.core.config import get_settings
from app.core.resources import create_resources
from app.db.transaction import transaction_scope
from app.services.payment_lifecycle import LifecycleService
from app.services.wechat_pay_client import WechatPayClient
from app.services.wechat_reconciliation import parse_bill
from scripts._database_target import validate_database_target


async def run(args: argparse.Namespace) -> None:
    bill_date = date.fromisoformat(args.date)
    today = datetime.now(timezone(timedelta(hours=8))).date()
    if not today - timedelta(days=90) <= bill_date < today:
        raise ValueError("bill date must be a completed day within 90 days")
    settings = get_settings()
    validate_database_target(settings, args.confirm_database)
    settings.validate_wechat_pay()
    if not settings.wechat_pay_active:
        raise ValueError("payment recovery must be enabled")
    resources = create_resources(settings)
    try:
        if resources.wechat_http is None:
            raise ValueError("payment HTTP client is unavailable")
        client = await asyncio.to_thread(WechatPayClient, settings, resources.wechat_http)
        total = pending = discrepancies = 0
        for kind in ("SUCCESS", "REFUND"):
            metadata = await client.request(
                "GET", f"/v3/bill/tradebill?bill_date={bill_date.isoformat()}&bill_type={kind}"
            )
            content = await client.download_bill(metadata)
            records, unresolved = parse_bill(
                content, merchant_id=settings.wechat_pay_mch_id, bill_date=bill_date.isoformat(), kind=kind
            )
            pending += unresolved
            total += len(records)
            if args.apply:
                for record in records:
                    async with resources.session_factory() as session, transaction_scope(session):
                        result = await LifecycleService(session).reconcile_in_open_transaction(record)
                        discrepancies += result.status == "discrepancy"
        print(f"records={total}; non_success_refunds={pending}; discrepancies={discrepancies}; applied={args.apply}")
    finally:
        await resources.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch signed WeChat bill metadata and reconcile verified bill records"
    )
    parser.add_argument("--date", required=True)
    parser.add_argument("--confirm-database", required=True)
    parser.add_argument("--apply", action="store_true")
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
