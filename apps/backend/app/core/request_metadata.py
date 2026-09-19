import ipaddress
import re
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import Request
from loguru import logger
from redis.exceptions import RedisError

from app.core.cache_keys import cache_keys
from app.core.context import current_request_id, current_trace_id
from app.core.security import token_digest

_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")


@dataclass(frozen=True, slots=True)
class RequestMetadata:
    request_id: str
    trace_id: str
    ip_address: str | None
    user_agent_summary: str | None
    release_version: str | None


def trusted_client_ip(request: Request) -> str | None:
    direct_ip = request.client.host if request.client else None
    if direct_ip is None:
        return None
    try:
        peer = ipaddress.ip_address(direct_ip)
        trusted_networks = [
            ipaddress.ip_network(value, strict=False) for value in request.app.state.settings.trusted_proxy_cidrs
        ]
    except ValueError:
        return direct_ip
    if not any(peer in network for network in trusted_networks):
        return direct_ip

    forwarded = request.headers.get("x-forwarded-for")
    if not forwarded:
        return direct_ip
    hops = [item.strip() for item in forwarded.split(",")]
    if not hops or len(hops) > 20:
        return direct_ip
    try:
        chain = [ipaddress.ip_address(item) for item in hops]
    except ValueError:
        return direct_ip
    for candidate in reversed(chain):
        if not any(candidate in network for network in trusted_networks):
            return str(candidate)
    return str(chain[0])


def request_metadata(request: Request) -> RequestMetadata:
    user_agent = _CONTROL_CHARACTERS.sub("", request.headers.get("user-agent", "")).strip()[:512] or None
    settings = request.app.state.settings
    return RequestMetadata(
        request_id=current_request_id(),
        trace_id=current_trace_id(),
        ip_address=trusted_client_ip(request),
        user_agent_summary=user_agent,
        release_version=settings.release_version,
    )


async def publish_request_log(
    request: Request,
    *,
    status_code: int,
    duration_ms: int,
    route_template: str,
    request_body: str | None = None,
) -> None:
    settings = request.app.state.settings
    if settings.request_log_mode != "metadata":
        return
    resources = getattr(request.app.state, "resources", None)
    if resources is None or resources.redis is None:
        logger.bind(request_id=current_request_id()).critical("request metadata stream is enabled without Redis")
        return
    principal_type: str | None = None
    principal_id: str | None = None
    hmac_key: str | None = None
    # 直接读取字段值避免热路径重复执行 authentication_secrets() 的完整校验逻辑
    web_hmac = settings.web_token_hmac_key
    admin_hmac = settings.admin_token_hmac_key
    if value := getattr(request.state, "current_admin_id", None):
        principal_type = "admin"
        principal_id = str(value)
        hmac_key = admin_hmac
    elif value := getattr(request.state, "current_user_id", None):
        principal_type = "user"
        principal_id = str(value)
        hmac_key = web_hmac
    fields = {
        "request_id": current_request_id(),
        "trace_id": current_trace_id(),
        "method": request.method,
        "route_template": route_template[:255],
        "status_code": str(status_code),
        "duration_ms": str(max(0, duration_ms)),
        "principal_type": principal_type or "",
        "principal_digest": token_digest(principal_id, hmac_key) if principal_id and hmac_key else "",
        "release_version": settings.release_version or "",
        "occurred_at": datetime.now(UTC).isoformat(),
    }
    if request_body is not None:
        fields["request_body"] = request_body
    try:
        await resources.redis.xadd(
            cache_keys(settings).request_log_stream(),
            fields,
            maxlen=settings.request_log_stream_maxlen,
            approximate=True,
        )
    except RedisError as exc:
        logger.bind(request_id=current_request_id()).opt(exception=exc).critical("failed to publish request metadata")


__all__ = ["RequestMetadata", "publish_request_log", "request_metadata", "trusted_client_ip"]
