import asyncio

from redis.asyncio import Redis

from .config import Settings


def create_redis_client(settings: Settings) -> Redis | None:
    if settings.redis_mode == "disabled":
        return None
    if not settings.redis_url:
        raise ValueError("REDIS_URL is required when Redis is enabled")
    return Redis.from_url(settings.redis_url, decode_responses=True)


async def check_redis(client: Redis | None, timeout: float) -> bool:
    if client is None:
        return True
    try:
        async with asyncio.timeout(timeout):
            return bool(await client.ping())
    except Exception, TimeoutError:
        return False
