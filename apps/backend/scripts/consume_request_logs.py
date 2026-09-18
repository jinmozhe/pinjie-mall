import argparse
import asyncio
import os
import socket
from datetime import datetime
from typing import cast

from loguru import logger
from redis.asyncio import Redis
from redis.exceptions import ResponseError
from redis.typing import EncodableT
from sqlalchemy.exc import IntegrityError

from app.core.cache_keys import cache_keys
from app.core.config import get_settings
from app.core.identifiers import new_uuid7
from app.core.resources import AppResources, create_resources
from app.db.models import RequestLog
from app.db.repositories import RequestLogRepository
from app.db.transaction import transaction_scope

GROUP_NAME = "request-log-writers-v1"
StreamFields = dict[str, str]
StreamMessage = tuple[str, StreamFields]


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Persist request metadata from Redis Stream")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--reclaim-idle-ms", type=int, default=60_000)
    return parser.parse_args()


def _request_log(fields: StreamFields) -> RequestLog:
    return RequestLog(
        id=new_uuid7(),
        request_id=fields["request_id"],
        trace_id=fields["trace_id"],
        method=fields["method"],
        route_template=fields["route_template"],
        status_code=int(fields["status_code"]),
        duration_ms=int(fields["duration_ms"]),
        principal_type=fields.get("principal_type") or None,
        principal_digest=fields.get("principal_digest") or None,
        release_version=fields.get("release_version") or None,
        occurred_at=datetime.fromisoformat(fields["occurred_at"]),
        request_body=fields.get("request_body") or None,
    )


async def _persist(
    resources: AppResources,
    stream: str,
    dead_letter: str,
    redis: Redis,
    message_id: str,
    fields: StreamFields,
) -> None:
    try:
        item = _request_log(fields)
        async with resources.session_factory() as session, transaction_scope(session):
            RequestLogRepository(session).add(item)
    except IntegrityError:
        # 重复日志消息幂等忽略
        logger.bind(message_id=message_id).debug("忽略已存在的重复请求日志")
    except (KeyError, TypeError, ValueError) as exc:
        dead_letter_fields = cast(dict[EncodableT, EncodableT], fields.copy())
        dead_letter_fields["source_message_id"] = message_id
        dead_letter_fields["error"] = type(exc).__name__
        await redis.xadd(dead_letter, dead_letter_fields)
    await redis.xack(stream, GROUP_NAME, message_id)


async def _reclaim_pending(
    resources: AppResources,
    *,
    stream: str,
    dead_letter: str,
    redis: Redis,
    consumer: str,
    batch_size: int,
    min_idle_ms: int,
) -> int:
    claimed = await redis.xautoclaim(
        stream,
        GROUP_NAME,
        consumer,
        min_idle_ms,
        "0-0",
        count=batch_size,
    )
    messages = cast(list[StreamMessage], claimed[1])
    for message_id, fields in messages:
        await _persist(resources, stream, dead_letter, redis, message_id, fields)
    return len(messages)


async def _run(args: argparse.Namespace) -> None:
    settings = get_settings()
    settings.validate_runtime()
    if settings.request_log_mode != "metadata":
        raise ValueError("REQUEST_LOG_MODE must be metadata")
    resources = create_resources(settings)
    if resources.redis is None:
        await resources.close()
        raise ValueError("Redis is required")
    redis = resources.redis
    keys = cache_keys(settings)
    stream = keys.request_log_stream()
    dead_letter = keys.request_log_dead_letter()
    consumer = f"{socket.gethostname()}-{os.getpid()}"
    try:
        try:
            await redis.xgroup_create(stream, GROUP_NAME, id="0", mkstream=True)
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise
        while True:
            await _reclaim_pending(
                resources,
                stream=stream,
                dead_letter=dead_letter,
                redis=redis,
                consumer=consumer,
                batch_size=max(1, min(args.batch_size, 1000)),
                min_idle_ms=max(0, args.reclaim_idle_ms),
            )
            batches = cast(
                list[tuple[str, list[StreamMessage]]],
                await redis.xreadgroup(
                    GROUP_NAME,
                    consumer,
                    {stream: ">"},
                    count=max(1, min(args.batch_size, 1000)),
                    block=1 if args.once else 1000,
                ),
            )
            for _, messages in batches:
                for message_id, fields in messages:
                    await _persist(resources, stream, dead_letter, redis, message_id, fields)
            if args.once:
                return
    finally:
        await resources.close()


def main() -> None:
    asyncio.run(_run(_arguments()))


if __name__ == "__main__":
    main()
