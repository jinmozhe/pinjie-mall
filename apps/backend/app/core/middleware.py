import re
import time
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from loguru import logger

from .context import request_id_context, trace_id_context
from .identifiers import new_uuid7
from .payload_sanitizer import capture_error_request_body
from .request_metadata import publish_request_log

_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def _valid_header(value: str | None) -> str | None:
    if value and _REQUEST_ID_PATTERN.fullmatch(value):
        return value
    return None


async def request_context_middleware(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    request_id = _valid_header(request.headers.get("X-Request-ID")) or str(new_uuid7())
    trace_id = _valid_header(request.headers.get("X-Trace-ID")) or str(new_uuid7())
    request_token = request_id_context.set(request_id)
    trace_token = trace_id_context.set(trace_id)
    started_at = time.perf_counter()
    try:
        response = await call_next(request)
        duration_ms = max(0, round((time.perf_counter() - started_at) * 1000))
        route = request.scope.get("route")
        route_template = getattr(route, "path", request.url.path)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Trace-ID"] = trace_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        logger.bind(
            request_id=request_id,
            trace_id=trace_id,
            method=request.method,
            route=route_template,
            duration_ms=duration_ms,
            status_code=response.status_code,
        ).info(
            "request completed method={} route={} status={} duration_ms={}",
            request.method,
            route_template,
            response.status_code,
            duration_ms,
        )
        request_body = await capture_error_request_body(
            request,
            status_code=response.status_code,
            route_template=route_template,
        )
        await publish_request_log(
            request,
            status_code=response.status_code,
            duration_ms=duration_ms,
            route_template=route_template,
            request_body=request_body,
        )
        return response
    except Exception:
        # call_next 本身抛出异常时，记录请求日志后重新抛出
        duration_ms = max(0, round((time.perf_counter() - started_at) * 1000))
        route = request.scope.get("route")
        route_template = getattr(route, "path", request.url.path)
        logger.bind(
            request_id=request_id,
            trace_id=trace_id,
            method=request.method,
            route=route_template,
            duration_ms=duration_ms,
            status_code=500,
        ).exception(
            "request failed method={} route={} duration_ms={}",
            request.method,
            route_template,
            duration_ms,
        )
        await publish_request_log(
            request,
            status_code=500,
            duration_ms=duration_ms,
            route_template=route_template,
            request_body=None,
        )
        raise
    finally:
        request_id_context.reset(request_token)
        trace_id_context.reset(trace_token)
