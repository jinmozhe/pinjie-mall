from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.staticfiles import StaticFiles

from app.api_router import api_router
from app.core.config import Settings, get_settings
from app.core.context import current_request_id
from app.core.cookies import ADMIN_COOKIES, WEB_COOKIES, clear_auth_cookies
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.core.health import check_readiness
from app.core.logging import configure_logging
from app.core.middleware import request_context_middleware
from app.core.openapi import OPENAPI_TAGS, localize_openapi_schema
from app.core.resources import AppResources, create_resources
from app.core.response import public_message
from app.domains.system.router import readiness_response
from app.domains.system.schemas import LiveStatus, ReadinessStatus
from app.services.settings_media import SettingsMediaStore
from app.services.storage import create_storage_provider
from app.services.system_settings import recover_settings_media

_HTTP_ERROR_MESSAGES = {
    400: "请求内容有误",
    401: "需要身份认证",
    403: "请求被拒绝",
    404: "请求的资源不存在",
    405: "请求方法不允许",
    413: "请求内容过大",
    422: "请求参数校验失败",
    429: "请求过于频繁",
}


def _error_response(*, request_id: str, code: str, message: str, details: Any = None, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "code": code,
            "message": public_message(message, fallback="请求处理失败"),
            "details": details,
            "request_id": request_id,
        },
    )


def _safe_validation_details(exc: RequestValidationError) -> list[dict[str, Any]]:
    details: list[dict[str, Any]] = []
    for error in exc.errors():
        location = [str(item) if not isinstance(item, int) else item for item in error.get("loc", [])]
        details.append(
            {
                "loc": location,
                "msg": str(error.get("msg", "Invalid input")),
                "type": str(error.get("type", "value_error")),
            }
        )
    return details


def _register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
        response = _error_response(
            request_id=current_request_id(),
            code=exc.code,
            message=exc.message,
            details=exc.details,
            status_code=exc.status_code,
        )
        response.headers.update(exc.headers)
        clear_profile = getattr(request.state, "clear_auth_profile", None)
        if clear_profile == "web":
            clear_auth_cookies(response, names=WEB_COOKIES, settings=request.app.state.settings)
        elif clear_profile == "admin":
            clear_auth_cookies(response, names=ADMIN_COOKIES, settings=request.app.state.settings)
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        return _error_response(
            request_id=current_request_id(),
            code=ErrorCode.VALIDATION_ERROR,
            message="请求参数校验失败",
            details=_safe_validation_details(exc),
            status_code=422,
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = ErrorCode.NOT_FOUND if exc.status_code == 404 else f"HTTP_{exc.status_code}"
        return _error_response(
            request_id=current_request_id(),
            code=code,
            message=_HTTP_ERROR_MESSAGES.get(exc.status_code, "请求处理失败"),
            status_code=exc.status_code,
        )

    @app.exception_handler(Exception)
    async def unknown_exception_handler(_: Request, exc: Exception) -> JSONResponse:
        from loguru import logger

        logger.opt(exception=exc).error("unhandled application exception")
        return _error_response(
            request_id=current_request_id(),
            code=ErrorCode.INTERNAL_ERROR,
            message="服务器内部错误",
            status_code=500,
        )


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app_settings.validate_runtime()
        configure_logging(app_settings)
        resources: AppResources = create_resources(app_settings)
        app.state.started_at = datetime.now(UTC)
        app.state.settings = app_settings
        app.state.resources = resources
        try:
            await recover_settings_media(session_factory=resources.session_factory, settings=app_settings)
            resources.settings_media_ready = True
            yield
        finally:
            await resources.close()

    app = FastAPI(
        title=app_settings.project_name,
        description="独立商城的后端 API，当前提供用户认证、账户管理、后台管理和系统状态能力。",
        version=app_settings.release_version or "0.1.0",
        docs_url=app_settings.docs_url,
        redoc_url=app_settings.redoc_url,
        openapi_tags=OPENAPI_TAGS,
        lifespan=lifespan,
    )
    app.state.settings = app_settings
    app.state.storage_provider = create_storage_provider(app_settings)
    app.state.settings_media_store = SettingsMediaStore(app_settings.settings_media_root)
    app.middleware("http")(request_context_middleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Accept",
            "Content-Type",
            "X-CSRF-Token",
            "X-Request-ID",
            "X-Trace-ID",
        ],
        expose_headers=["X-Request-ID", "X-Trace-ID"],
    )
    if "*" not in app_settings.trusted_hosts:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=app_settings.trusted_hosts)
    _register_exception_handlers(app)

    app.include_router(api_router, prefix=app_settings.api_v1_str)
    app.mount(
        app_settings.upload_base_url,
        StaticFiles(directory=app_settings.upload_local_root, check_dir=False),
        name="uploaded-assets",
    )
    app.mount(
        app_settings.settings_media_base_url,
        StaticFiles(directory=app_settings.settings_media_root, check_dir=False),
        name="settings-media",
    )

    @app.get("/health/live", response_model=LiveStatus, tags=["健康检查"], summary="检查应用存活状态")
    async def health_live() -> LiveStatus:
        return LiveStatus(status="alive")

    @app.get("/health/ready", response_model=ReadinessStatus, tags=["健康检查"], summary="检查应用就绪状态")
    async def health_ready(request: Request) -> JSONResponse:
        resources = getattr(request.app.state, "resources", None)
        settings = getattr(request.app.state, "settings", None)
        if resources is None or settings is None:
            return readiness_response(status_code=503, status="unavailable", checks={"application": "unavailable"})
        result = await check_readiness(resources, settings)
        return readiness_response(
            status_code=200 if result.ready else 503,
            status="ready" if result.ready else "unavailable",
            checks=result.checks,
        )

    app.openapi_schema = localize_openapi_schema(app.openapi())
    return app


app = create_app()

__all__ = ["app", "create_app"]
