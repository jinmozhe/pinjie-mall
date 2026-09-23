import json
import re
from typing import Any

from fastapi import Request
from starlette.requests import ClientDisconnect

MAX_REQUEST_BODY_CHARS = 4096
TRUNCATION_MARKER = "...[truncated]"

_SENSITIVE_KEY_PATTERN = re.compile(
    r"(?:password|pwd|token|secret|api[_-]?key|credit[_-]?card|id[_-]?card|cvv|cvc)",
    re.IGNORECASE,
)
_SENSITIVE_ROUTES = frozenset(
    {
        "/api/v1/auth/login",
        "/api/v1/admin/auth/login",
        "/api/v1/account/change-password",
        "/api/v1/admin/account/change-password",
        "/api/v1/admin/account/confirm",
        "/api/v1/users/me/password",
        "/api/v1/admin/auth/password",
    }
)
_COMMERCE_PRIVATE_PREFIXES = (
    "/api/v1/addresses",
    "/api/v1/orders",
    "/api/v1/order-items",
    "/api/v1/distribution",
    "/api/v1/admin/orders",
    "/api/v1/admin/refunds",
    "/api/v1/admin/withdrawals",
    "/api/v1/admin/reconciliation-records",
    "/api/v1/admin/payments",
    "/api/v1/admin/members",
    "/api/v1/admin/commissions",
    "/api/v1/admin/wallets",
)


def _normalize_path(path: str) -> str:
    normalized = path.strip()
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"
    return normalized.rstrip("/") or "/"


def is_sensitive_route(route_template: str) -> bool:
    path = _normalize_path(route_template)
    return path in _SENSITIVE_ROUTES or any(
        path == prefix or path.startswith(f"{prefix}/") for prefix in _COMMERCE_PRIVATE_PREFIXES
    )


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): "***" if _SENSITIVE_KEY_PATTERN.search(str(key)) else _sanitize_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    return value


def _truncate(value: str, *, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    if max_chars <= len(TRUNCATION_MARKER):
        return TRUNCATION_MARKER[:max_chars]
    return f"{value[: max_chars - len(TRUNCATION_MARKER)]}{TRUNCATION_MARKER}"


async def capture_error_request_body(
    request: Request,
    *,
    status_code: int,
    route_template: str,
    max_chars: int = MAX_REQUEST_BODY_CHARS,
) -> str | None:
    if status_code < 400 or is_sensitive_route(route_template):
        return None
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type != "application/json":
        return None

    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > max_chars:
                return TRUNCATION_MARKER
        except ValueError:
            pass

    try:
        body = getattr(request, "_body", None)
        if body is None:
            body = await request.body()
    except (ClientDisconnect, RuntimeError):  # fmt: skip
        return None
    if not body:
        return None
    try:
        parsed = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):  # fmt: skip
        return None
    sanitized = json.dumps(_sanitize_value(parsed), ensure_ascii=False, separators=(",", ":"))
    return _truncate(sanitized, max_chars=max_chars)


__all__ = [
    "MAX_REQUEST_BODY_CHARS",
    "TRUNCATION_MARKER",
    "capture_error_request_body",
    "is_sensitive_route",
]
