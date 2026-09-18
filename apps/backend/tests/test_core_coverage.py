import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient
from jwt import InvalidTokenError
from redis.exceptions import RedisError

from app.core.config import Settings
from app.core.csrf import new_csrf_token, verify_csrf_token
from app.core.exceptions import AppException
from app.core.health import ReadinessResult, check_database, check_readiness
from app.core.identifiers import new_uuid7
from app.core.privacy import masked_ip
from app.core.rate_limit import acquire_refresh_lock, enforce_rate_limit, release_refresh_lock
from app.core.redis import check_redis, create_redis_client
from app.core.request_metadata import RequestMetadata, publish_request_log, request_metadata, trusted_client_ip
from app.core.resources import AppResources, create_resources
from app.core.security import PasswordManager, create_access_token, decode_access_token, new_anonymized_username
from app.main import create_app
from app.services.authentication import WebAuthService
from tests.conftest import TEST_SECRETS

DATABASE_URL = "postgresql+asyncpg://u:p@localhost:5432/app"


def test_anonymized_username_is_unique_and_within_database_limit() -> None:
    user_id = new_uuid7()
    first = new_anonymized_username(user_id)
    second = new_anonymized_username(user_id)

    assert first.startswith("deleted-")
    assert len(first) <= 50
    assert first != second


def _settings(**updates: object) -> Settings:
    values: dict[str, object] = {
        "ENVIRONMENT": "local",
        "DATABASE_URL": DATABASE_URL,
        **TEST_SECRETS,
    }
    values.update(updates)
    return Settings(_env_file=None, **values)


@pytest.mark.parametrize("prefix", ["api/v1", "/api/v1/"])
def test_settings_reject_invalid_api_prefix(prefix: str) -> None:
    with pytest.raises(ValueError, match="API_V1_STR"):
        _settings(API_V1_STR=prefix)


def test_settings_normalize_and_reject_log_levels() -> None:
    assert _settings(LOG_LEVEL="warning").log_level == "WARNING"
    with pytest.raises(ValueError, match="LOG_LEVEL"):
        _settings(LOG_LEVEL="TRACE")


@pytest.mark.parametrize(
    "origin",
    [
        "https://user@example.test",
        "https://*:443",
        "https://example.test:invalid",
        "https://example.test/path",
    ],
)
def test_settings_reject_non_origin_browser_urls(origin: str) -> None:
    with pytest.raises(ValueError, match="browser origins"):
        _settings(WEB_ORIGINS=[origin])


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"REDIS_URL": "http://localhost:6379"}, "REDIS_URL"),
        ({"REDIS_MODE": "disabled"}, "REDIS_MODE"),
        ({"SESSION_ABSOLUTE_TTL_DAYS": 7}, "SESSION_ABSOLUTE_TTL_DAYS"),
    ],
)
def test_settings_reject_invalid_runtime_combinations(updates: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        _settings(**updates).validate_runtime()


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"API_DOCS_ENABLED": True}, "API_DOCS_ENABLED"),
        ({"RELEASE_VERSION": None}, "RELEASE_VERSION"),
        ({"TRUSTED_HOSTS": []}, "TRUSTED_HOSTS"),
        ({"WEB_ORIGINS": []}, "WEB_ORIGINS"),
        ({"ADMIN_ORIGINS": []}, "ADMIN_ORIGINS"),
        ({"ADMIN_ORIGINS": ["https://web.example.test"]}, "must not overlap"),
        ({"AUTH_COOKIE_SECURE": False}, "AUTH_COOKIE_SECURE"),
        ({"TRUSTED_PROXY_CIDRS": []}, "TRUSTED_PROXY_CIDRS"),
    ],
)
def test_production_settings_fail_closed(updates: dict[str, object], message: str) -> None:
    production = {
        "ENVIRONMENT": "production",
        "API_DOCS_ENABLED": False,
        "RELEASE_VERSION": "coverage-test",
        "TRUSTED_HOSTS": ["example.test"],
        "WEB_ORIGINS": ["https://web.example.test"],
        "ADMIN_ORIGINS": ["https://admin.example.test"],
        "AUTH_COOKIE_SECURE": True,
        "TRUSTED_PROXY_CIDRS": ["127.0.0.1/32"],
    }
    production.update(updates)
    with pytest.raises(ValueError, match=message):
        _settings(**production).validate_runtime()


@pytest.mark.parametrize(
    ("database_url", "message"),
    [
        (None, "DATABASE_URL"),
        ("postgresql://u:p@localhost/app", r"postgresql\+asyncpg"),
        ("postgresql+asyncpg://u:p@localhost", r"postgresql\+asyncpg"),
    ],
)
def test_database_settings_reject_invalid_urls(database_url: str | None, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        _settings(DATABASE_URL=database_url).validate_database_runtime()


@pytest.mark.parametrize("test_database_url", [None, "postgresql+asyncpg://u:p@localhost/app"])
def test_test_environment_requires_isolated_database(test_database_url: str | None) -> None:
    with pytest.raises(ValueError, match="TEST_DATABASE_URL"):
        _settings(ENVIRONMENT="test", TEST_DATABASE_URL=test_database_url).validate_database_runtime()


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"WEB_JWT_SECRET": None}, "WEB_JWT_SECRET"),
        ({"WEB_JWT_SECRET": "short"}, "WEB_JWT_SECRET"),
        ({"WEB_JWT_SECRET": "replace_with_a_real_secret_value_123"}, "template"),
        ({"ADMIN_JWT_SECRET": TEST_SECRETS["WEB_JWT_SECRET"]}, "different"),
    ],
)
def test_authentication_secrets_fail_closed(updates: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        _settings(**updates).authentication_secrets()


def test_settings_validate_proxy_networks_and_documentation_urls() -> None:
    with pytest.raises(ValueError, match="invalid network"):
        _settings(TRUSTED_PROXY_CIDRS=["invalid-network"]).validate_runtime()
    assert _settings(API_DOCS_ENABLED=False).docs_url is None
    assert _settings(API_DOCS_ENABLED=False).redoc_url is None
    assert _settings(ENVIRONMENT="production").docs_url is None
    assert _settings().authentication_secrets() == tuple(
        TEST_SECRETS[key] for key in TEST_SECRETS if "SECRET" in key or "HMAC" in key
    )


def test_csrf_tokens_and_ip_masking() -> None:
    token, digest = new_csrf_token("k" * 32)
    assert verify_csrf_token(token, digest, "k" * 32)
    assert not verify_csrf_token("different", digest, "k" * 32)
    assert masked_ip(None) is None
    assert masked_ip("invalid") is None
    assert masked_ip("192.0.2.129") == "192.0.2.0/24"
    assert masked_ip("2001:db8::1234") == "2001:db8::/64"


def test_uuid7_rejects_missing_or_invalid_runtime_generator() -> None:
    with patch("app.core.identifiers.uuid.uuid7", None):
        with pytest.raises(RuntimeError, match="Python 3.14"):
            new_uuid7()
    with patch("app.core.identifiers.uuid.uuid7", return_value=uuid.uuid4()):
        with pytest.raises(RuntimeError, match="invalid value"):
            new_uuid7()


class _RedisProbe:
    def __init__(self, *, result: bool = True, error: Exception | None = None, delay: float = 0) -> None:
        self.result = result
        self.error = error
        self.delay = delay

    async def ping(self) -> bool:
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        return self.result


@pytest.mark.asyncio
async def test_redis_client_and_probe_states() -> None:
    assert create_redis_client(_settings(REDIS_MODE="disabled")) is None
    with pytest.raises(ValueError, match="REDIS_URL"):
        create_redis_client(_settings(REDIS_URL=None))
    marker = object()
    with patch("app.core.redis.Redis.from_url", return_value=marker) as from_url:
        assert create_redis_client(_settings()) is marker
    from_url.assert_called_once_with(TEST_SECRETS["REDIS_URL"], decode_responses=True)
    assert await check_redis(None, 0.01)
    assert await check_redis(_RedisProbe(result=True), 0.01)  # type: ignore[arg-type]
    assert not await check_redis(_RedisProbe(error=RuntimeError("offline")), 0.01)  # type: ignore[arg-type]
    assert not await check_redis(_RedisProbe(delay=0.02), 0.001)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_rate_limit_failure_and_lock_states() -> None:
    with pytest.raises(AppException) as unavailable:
        await enforce_rate_limit(None, key="key", limit=1, window_seconds=60)
    assert unavailable.value.status_code == 503

    failing = SimpleNamespace(eval=AsyncMock(side_effect=RedisError("offline")))
    with pytest.raises(AppException) as redis_failure:
        await enforce_rate_limit(failing, key="key", limit=1, window_seconds=60)  # type: ignore[arg-type]
    assert redis_failure.value.status_code == 503

    malformed = SimpleNamespace(eval=AsyncMock(return_value=[1]))
    with pytest.raises(AppException) as invalid_state:
        await enforce_rate_limit(malformed, key="key", limit=1, window_seconds=60)  # type: ignore[arg-type]
    assert invalid_state.value.status_code == 503

    limited = SimpleNamespace(eval=AsyncMock(return_value=[2, 0]))
    with pytest.raises(AppException) as rate_limited:
        await enforce_rate_limit(limited, key="key", limit=1, window_seconds=60)  # type: ignore[arg-type]
    assert rate_limited.value.status_code == 429
    assert rate_limited.value.headers == {"Retry-After": "1"}

    with pytest.raises(AppException) as lock_unavailable:
        await acquire_refresh_lock(None, key="key", owner="owner")
    assert lock_unavailable.value.status_code == 503
    lock = SimpleNamespace(set=AsyncMock(return_value="OK"))
    assert await acquire_refresh_lock(lock, key="key", owner="owner")  # type: ignore[arg-type]
    lock.set.side_effect = RedisError("offline")
    with pytest.raises(AppException) as lock_failure:
        await acquire_refresh_lock(lock, key="key", owner="owner")  # type: ignore[arg-type]
    assert lock_failure.value.status_code == 503

    await release_refresh_lock(None, key="key", owner="owner")
    release = SimpleNamespace(eval=AsyncMock(side_effect=RedisError("offline")))
    await release_refresh_lock(release, key="key", owner="owner")  # type: ignore[arg-type]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "redis",
    [None, SimpleNamespace(delete=AsyncMock(side_effect=RedisError("offline")))],
)
async def test_login_limit_cleanup_is_best_effort_after_authentication(redis: object | None) -> None:
    service = WebAuthService(
        session=MagicMock(),
        session_factory=MagicMock(),
        redis=redis,  # type: ignore[arg-type]
        settings=_settings(),
        password_manager=MagicMock(),
        metadata=RequestMetadata(
            request_id="cleanup-request",
            trace_id="cleanup-trace",
            ip_address="127.0.0.1",
            user_agent_summary="pytest",
            release_version="test",
        ),
    )

    await service.clear_login_limit("browser-user")

    if redis is not None:
        redis.delete.assert_awaited_once()  # type: ignore[attr-defined]


class _Connection:
    def __init__(self, *, heads: tuple[str, ...] = (), error: Exception | None = None, delay: float = 0) -> None:
        self.heads = heads
        self.error = error
        self.delay = delay

    async def execute(self, _statement: object) -> None:
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error:
            raise self.error

    async def run_sync(self, _callable: object) -> tuple[str, ...]:
        return self.heads


class _ConnectContext:
    def __init__(self, connection: _Connection) -> None:
        self.connection = connection

    async def __aenter__(self) -> _Connection:
        return self.connection

    async def __aexit__(self, *_args: object) -> None:
        return None


class _Engine:
    def __init__(self, connection: _Connection) -> None:
        self.connection = connection

    def connect(self) -> _ConnectContext:
        return _ConnectContext(self.connection)


@pytest.mark.asyncio
async def test_database_and_readiness_failure_states() -> None:
    with patch("app.core.health.alembic_heads", return_value=("head",)):
        assert await check_database(_Engine(_Connection(heads=("old",))), 0.1) == (  # type: ignore[arg-type]
            False,
            "migration_revision_mismatch",
        )
        assert await check_database(_Engine(_Connection(heads=("head",))), 0.1) == (True, "ok")  # type: ignore[arg-type]
    assert await check_database(_Engine(_Connection(error=RuntimeError("offline"))), 0.1) == (  # type: ignore[arg-type]
        False,
        "unavailable",
    )
    assert await check_database(_Engine(_Connection(delay=0.02)), 0.001) == (False, "timeout")  # type: ignore[arg-type]

    resources = SimpleNamespace(engine=object(), redis=object(), settings_media_ready=True)
    with (
        patch("app.core.health.check_database", new=AsyncMock(return_value=(True, "ok"))),
        patch("app.core.health.check_redis", new=AsyncMock(return_value=False)),
    ):
        result = await check_readiness(resources, _settings())  # type: ignore[arg-type]
    assert not result.ready
    assert result.checks == {"database": "ok", "settings_media": "ok", "redis": "unavailable"}

    with patch("app.core.health.check_database", new=AsyncMock(return_value=(True, "ok"))):
        result = await check_readiness(resources, _settings(REDIS_MODE="disabled"))  # type: ignore[arg-type]
    assert result.ready


@pytest.mark.asyncio
async def test_readiness_endpoint_and_unknown_errors_are_fail_closed() -> None:
    test_app = create_app(_settings())

    @test_app.get("/coverage-error")
    async def coverage_error() -> None:
        raise RuntimeError("must not leak")

    async with AsyncClient(
        transport=ASGITransport(app=test_app, raise_app_exceptions=False),
        base_url="http://testserver",
    ) as client:
        test_app.state.resources = None
        unavailable = await client.get("/health/ready")
        assert unavailable.status_code == 503
        assert unavailable.json() == {"status": "unavailable", "checks": {"application": "unavailable"}}

        test_app.state.resources = SimpleNamespace()
        with patch(
            "app.main.check_readiness",
            new=AsyncMock(return_value=ReadinessResult(ready=True, checks={"database": "ok", "redis": "ok"})),
        ):
            ready = await client.get("/health/ready")
        assert ready.status_code == 200
        assert ready.json()["status"] == "ready"

        failure = await client.get("/coverage-error")
        assert failure.status_code == 500
        assert failure.json()["code"] == "INTERNAL_ERROR"
        assert "must not leak" not in failure.text


def _request(
    *,
    settings: Settings,
    peer: str | None = "127.0.0.1",
    forwarded: str | None = None,
    user_agent: str | None = None,
    resources: object | None = None,
) -> Request:
    app = FastAPI()
    app.state.settings = settings
    if resources is not None:
        app.state.resources = resources
    headers: list[tuple[bytes, bytes]] = []
    if forwarded is not None:
        headers.append((b"x-forwarded-for", forwarded.encode("ascii")))
    if user_agent is not None:
        headers.append((b"user-agent", user_agent.encode("ascii")))
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/",
            "raw_path": b"/",
            "query_string": b"",
            "headers": headers,
            "client": (peer, 12345) if peer is not None else None,
            "server": ("testserver", 80),
            "app": app,
        }
    )


def test_request_metadata_handles_proxy_edges_and_user_agent() -> None:
    settings = _settings(TRUSTED_PROXY_CIDRS=["127.0.0.1/32", "10.0.0.0/8"], RELEASE_VERSION="test")
    assert trusted_client_ip(_request(settings=settings, peer=None)) is None
    assert trusted_client_ip(_request(settings=settings, peer="not-an-ip")) == "not-an-ip"
    assert trusted_client_ip(_request(settings=settings)) == "127.0.0.1"
    too_many = ",".join(["10.0.0.1"] * 21)
    assert trusted_client_ip(_request(settings=settings, forwarded=too_many)) == "127.0.0.1"
    assert trusted_client_ip(_request(settings=settings, forwarded="10.0.0.1,10.0.0.2")) == "10.0.0.1"
    metadata = request_metadata(_request(settings=settings, user_agent=" Agent\x00Name "))
    assert metadata.user_agent_summary == "AgentName"
    assert metadata.release_version == "test"


@pytest.mark.asyncio
async def test_request_log_disabled_missing_redis_and_publish_failure() -> None:
    await publish_request_log(
        _request(settings=_settings(REQUEST_LOG_MODE="disabled")),
        status_code=200,
        duration_ms=1,
        route_template="/test",
    )
    await publish_request_log(
        _request(settings=_settings(REQUEST_LOG_MODE="metadata")),
        status_code=200,
        duration_ms=1,
        route_template="/test",
    )
    redis = SimpleNamespace(xadd=AsyncMock(side_effect=RedisError("offline")))
    request = _request(
        settings=_settings(REQUEST_LOG_MODE="metadata"),
        resources=SimpleNamespace(redis=redis),
    )
    request.state.current_admin_id = new_uuid7()
    await publish_request_log(request, status_code=503, duration_ms=-1, route_template="/" + "x" * 300)
    redis.xadd.assert_awaited_once()


@pytest.mark.asyncio
async def test_request_log_includes_sanitized_body_only_when_provided() -> None:
    redis = SimpleNamespace(xadd=AsyncMock())
    request = _request(
        settings=_settings(REQUEST_LOG_MODE="metadata"),
        resources=SimpleNamespace(redis=redis),
    )

    await publish_request_log(
        request,
        status_code=422,
        duration_ms=3,
        route_template="/api/v1/users",
        request_body='{"password":"***"}',
    )

    fields = redis.xadd.await_args.args[1]
    assert fields["request_body"] == '{"password":"***"}'


@pytest.mark.asyncio
async def test_resources_close_and_creation_guards() -> None:
    engine = SimpleNamespace(dispose=AsyncMock())
    redis = SimpleNamespace(aclose=AsyncMock())
    resources = AppResources(
        engine=engine,  # type: ignore[arg-type]
        session_factory=MagicMock(),
        redis=redis,  # type: ignore[arg-type]
        password_manager=PasswordManager(1),
    )
    await resources.close()
    redis.aclose.assert_awaited_once()
    engine.dispose.assert_awaited_once()

    without_redis = AppResources(
        engine=engine,  # type: ignore[arg-type]
        session_factory=MagicMock(),
        redis=None,
        password_manager=PasswordManager(1),
    )
    await without_redis.close()
    with pytest.raises(ValueError, match="DATABASE_URL"):
        create_resources(Settings(DATABASE_URL=None, **TEST_SECRETS))


@pytest.mark.asyncio
async def test_password_upgrade_and_invalid_access_token_claims() -> None:
    manager = PasswordManager(1)
    password_hash = await manager.hash("coverage-password")
    valid, replacement = await manager.verify_and_update("coverage-password", password_hash)
    assert valid
    assert replacement is None
    await manager.verify_unknown_user("unknown-password")

    now_token, _ = create_access_token(
        subject_id=new_uuid7(),
        session_id=new_uuid7(),
        credential_version=1,
        audience="pinjie-web",
        issuer="issuer",
        secret="s" * 32,
        ttl_seconds=900,
    )
    assert decode_access_token(now_token, audience="pinjie-web", issuer="issuer", secret="s" * 32)

    base = {
        "iss": "issuer",
        "aud": "pinjie-web",
        "sub": str(new_uuid7()),
        "sid": str(new_uuid7()),
        "jti": str(new_uuid7()),
        "iat": 2_000_000_000,
        "nbf": 1,
        "exp": 2_000_000_900,
        "token_type": "access",
        "credential_version": 1,
    }
    for update in (
        {"token_type": "refresh"},
        {"credential_version": True},
        {"credential_version": "1"},
        {"sub": "invalid-uuid"},
    ):
        payload = {**base, **update}
        token = jwt.encode(payload, "s" * 32, algorithm="HS256")
        with pytest.raises(InvalidTokenError):
            decode_access_token(token, audience="pinjie-web", issuer="issuer", secret="s" * 32)
