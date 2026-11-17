from dataclasses import dataclass

from loguru import logger
from redis.asyncio import Redis
from redis.exceptions import AuthenticationError as RedisAuthenticationError
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import RedisError
from redis.exceptions import TimeoutError as RedisTimeoutError

from app.core.context import current_request_id, current_trace_id
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException

_FIXED_WINDOW_SCRIPT = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
local ttl = redis.call('TTL', KEYS[1])
return {current, ttl}
"""


@dataclass(frozen=True, slots=True)
class RateLimitState:
    count: int
    retry_after: int


def _redis_unavailable(*, operation: str, error: RedisError | None = None) -> AppException:
    if error is None:
        reason = "not_initialized"
        local_message = "认证依赖的 Redis 未初始化，请检查后端 Redis 配置并重启后端"
    elif isinstance(error, RedisAuthenticationError):
        reason = "authentication_failed"
        local_message = "Redis 认证失败，请检查后端 REDIS_URL 中的认证配置"
    elif isinstance(error, RedisTimeoutError):
        reason = "timeout"
        local_message = "Redis 请求超时，请检查 Redis 服务和连接配置"
    elif isinstance(error, RedisConnectionError):
        reason = "connection_failed"
        local_message = "无法连接 Redis，请确认 Docker Desktop 和 Redis 容器已启动，并检查 REDIS_URL 配置"
    else:
        reason = "command_failed"
        local_message = "Redis 安全校验失败，请检查 Redis 服务和命令权限"
    logger.bind(
        request_id=current_request_id(),
        trace_id=current_trace_id(),
        dependency="redis",
        operation=operation,
        reason=reason,
    ).warning("authentication dependency unavailable: dependency=redis operation={} reason={}", operation, reason)
    return AppException(
        status_code=503,
        code=ErrorCode.SERVICE_UNAVAILABLE,
        message="登录安全校验服务暂时不可用，请稍后重试",
        local_message=local_message,
    )


async def enforce_rate_limit(redis: Redis | None, *, key: str, limit: int, window_seconds: int) -> RateLimitState:
    if redis is None:
        raise _redis_unavailable(operation="rate_limit")
    try:
        raw = await redis.eval(_FIXED_WINDOW_SCRIPT, 1, key, window_seconds)
    except RedisError as exc:
        raise _redis_unavailable(operation="rate_limit", error=exc) from exc
    if not isinstance(raw, (list, tuple)) or len(raw) != 2:
        raise AppException(
            status_code=503,
            code=ErrorCode.SERVICE_UNAVAILABLE,
            message="认证服务返回了无效的限流状态",
        )
    state = RateLimitState(count=int(raw[0]), retry_after=max(1, int(raw[1])))
    if state.count > limit:
        raise AppException(
            status_code=429,
            code=ErrorCode.RATE_LIMITED,
            message="请求过于频繁",
            details={"retry_after": state.retry_after},
            headers={"Retry-After": str(state.retry_after)},
        )
    return state


async def acquire_refresh_lock(redis: Redis | None, *, key: str, owner: str, ttl_seconds: int = 10) -> bool:
    if redis is None:
        raise _redis_unavailable(operation="refresh_lock")
    try:
        return bool(await redis.set(key, owner, ex=ttl_seconds, nx=True))
    except RedisError as exc:
        raise _redis_unavailable(operation="refresh_lock", error=exc) from exc


async def release_refresh_lock(redis: Redis | None, *, key: str, owner: str) -> None:
    if redis is None:
        return
    script = "if redis.call('GET', KEYS[1]) == ARGV[1] then return redis.call('DEL', KEYS[1]) else return 0 end"
    try:
        await redis.eval(script, 1, key, owner)
    except RedisError as exc:
        logger.bind(cache_key=key).opt(exception=exc).critical("failed to release authentication refresh lock")


__all__ = ["RateLimitState", "acquire_refresh_lock", "enforce_rate_limit", "release_refresh_lock"]
