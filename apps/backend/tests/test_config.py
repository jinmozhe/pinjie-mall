import json
import sys

import pytest
from loguru import logger

from app.core.config import Settings
from app.core.logging import configure_logging
from tests.conftest import TEST_SECRETS


def test_test_secrets_use_one_redis_target() -> None:
    assert TEST_SECRETS["REDIS_URL"] == TEST_SECRETS["TEST_REDIS_URL"]


def test_local_settings_require_database_url() -> None:
    settings = Settings(ENVIRONMENT="local", DATABASE_URL="postgresql+asyncpg://u:p@localhost:5432/app", **TEST_SECRETS)
    settings.validate_runtime()


def test_test_database_requires_matching_test_target() -> None:
    settings = Settings(
        ENVIRONMENT="test",
        DATABASE_URL="postgresql+asyncpg://u:p@localhost:5432/app_test",
        TEST_DATABASE_URL="postgresql+asyncpg://u:p@localhost:5432/app_test",
        **TEST_SECRETS,
    )
    settings.validate_runtime()


def test_test_database_rejects_different_runtime_target() -> None:
    settings = Settings(
        ENVIRONMENT="test",
        DATABASE_URL="postgresql+asyncpg://u:p@localhost:5432/app",
        TEST_DATABASE_URL="postgresql+asyncpg://u:p@localhost:5432/app_test",
        **TEST_SECRETS,
    )
    with pytest.raises(ValueError, match="DATABASE_URL must match TEST_DATABASE_URL"):
        settings.validate_runtime()


def test_runtime_rejects_disabled_redis_when_authentication_is_enabled() -> None:
    settings = Settings(
        ENVIRONMENT="local",
        DATABASE_URL="postgresql+asyncpg://u:p@localhost:5432/app",
        **{**TEST_SECRETS, "REDIS_MODE": "disabled"},
    )
    with pytest.raises(ValueError, match="REDIS_MODE"):
        settings.validate_runtime()


def test_production_rejects_debug_sql_logging() -> None:
    settings = Settings(
        ENVIRONMENT="production",
        DATABASE_URL="postgresql+asyncpg://u:p@localhost:5432/app",
        DEBUG=True,
        AUTH_COOKIE_SECURE=True,
        RELEASE_VERSION="test",
        TRUSTED_HOSTS=["mall.example.com"],
        TRUSTED_PROXY_CIDRS=["127.0.0.1/32"],
        **{**TEST_SECRETS, "REDIS_URL": "redis://localhost:6379/0"},
    )
    with pytest.raises(ValueError, match="DEBUG"):
        settings.validate_runtime()


def test_required_redis_requires_url() -> None:
    settings = Settings(
        ENVIRONMENT="local",
        DATABASE_URL="postgresql+asyncpg://u:p@localhost:5432/app",
        **{**TEST_SECRETS, "REDIS_URL": None},
    )
    with pytest.raises(ValueError, match="REDIS_URL"):
        settings.validate_runtime()


def test_environment_aliases_are_rejected() -> None:
    with pytest.raises(ValueError):
        Settings(ENVIRONMENT="development")


def test_file_logging_defaults_are_local_file_safe() -> None:
    settings = Settings()

    assert settings.log_file_enabled is True
    assert settings.log_file_path == "logs/app_{time:YYYY-MM-DD}.log"
    assert settings.log_file_rotation == "50 MB"
    assert settings.log_file_retention == "10 days"


def test_configure_logging_adds_async_file_sink_when_enabled(tmp_path, monkeypatch) -> None:
    settings = Settings(
        LOG_FILE_ENABLED=True,
        LOG_FILE_PATH=str(tmp_path / "logs" / "app_{time:YYYY-MM-DD}.log"),
    )
    added: list[tuple[object, dict[str, object]]] = []
    monkeypatch.setattr(logger, "remove", lambda: None)
    monkeypatch.setattr(logger, "add", lambda sink, **kwargs: added.append((sink, kwargs)) or 1)

    configure_logging(settings)

    assert (tmp_path / "logs").is_dir()
    assert len(added) == 2
    sink, options = added[1]
    assert sink == settings.log_file_path
    assert options["enqueue"] is True
    assert options["serialize"] is True
    assert options["rotation"] == "50 MB"
    assert options["retention"] == "10 days"
    assert options["compression"] == "zip"
    assert options["encoding"] == "utf-8"


def test_configure_logging_skips_file_sink_when_disabled(tmp_path, monkeypatch) -> None:
    settings = Settings(
        LOG_FILE_ENABLED=False,
        LOG_FILE_PATH=str(tmp_path / "logs" / "app.log"),
    )
    added: list[object] = []
    monkeypatch.setattr(logger, "remove", lambda: None)
    monkeypatch.setattr(logger, "add", lambda sink, **_: added.append(sink) or 1)

    configure_logging(settings)

    assert added == [sys.stderr]
    assert not (tmp_path / "logs").exists()


@pytest.mark.asyncio
async def test_file_logging_writes_structured_request_context_and_utf8(tmp_path, client) -> None:
    log_file = tmp_path / "logs" / "app.log"
    settings = Settings(LOG_FILE_ENABLED=True, LOG_FILE_PATH=str(log_file))
    configure_logging(settings)

    try:
        response = await client.get("/health/live")
        logger.info("中文日志可正常解析")
        logger.complete()

        assert response.status_code == 200
        records = [json.loads(line) for line in log_file.read_text(encoding="utf-8").splitlines()]
        request_record = next(
            record for record in records if record["record"]["message"].startswith("request completed")
        )
        request_extra = request_record["record"]["extra"]
        assert request_extra == {
            "request_id": response.headers["x-request-id"],
            "trace_id": response.headers["x-trace-id"],
            "method": "GET",
            "route": "/health/live",
            "duration_ms": request_extra["duration_ms"],
            "status_code": 200,
        }
        assert isinstance(request_extra["duration_ms"], int)
        assert request_extra["duration_ms"] >= 0

        plain_record = next(record for record in records if record["record"]["message"] == "中文日志可正常解析")
        assert plain_record["record"]["extra"] == {}
    finally:
        logger.remove()
        configure_logging(Settings(LOG_FILE_ENABLED=False))
