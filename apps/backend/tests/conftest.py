import os
from collections.abc import AsyncIterator
from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings

_bootstrap_settings = Settings()
if _bootstrap_settings.test_database_url:
    os.environ.setdefault("TEST_DATABASE_URL", _bootstrap_settings.test_database_url)
if _bootstrap_settings.test_redis_url:
    os.environ.setdefault("TEST_REDIS_URL", _bootstrap_settings.test_redis_url)
if os.getenv("TEST_DATABASE_URL") and os.getenv("TEST_REDIS_URL"):
    os.environ["ENVIRONMENT"] = "test"
    os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
    os.environ["REDIS_URL"] = os.environ["TEST_REDIS_URL"]

from app.main import app  # noqa: E402

_test_redis_url = os.getenv("TEST_REDIS_URL", "redis://localhost:6379/15")
TEST_SECRETS = {
    "REDIS_MODE": "required",
    "REDIS_URL": _test_redis_url,
    "TEST_REDIS_URL": _test_redis_url,
    "WEB_JWT_SECRET": "test-web-jwt-secret-0000000000000001",
    "ADMIN_JWT_SECRET": "test-admin-jwt-secret-0000000000001",
    "WEB_TOKEN_HMAC_KEY": "test-web-hmac-secret-000000000000001",
    "ADMIN_TOKEN_HMAC_KEY": "test-admin-hmac-secret-0000000000001",
}


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def client_transport() -> ASGITransport:
    return ASGITransport(app=app)


@pytest.fixture
async def client(client_transport: ASGITransport) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=client_transport, base_url="http://testserver") as test_client:
        yield test_client


@pytest.fixture
def fake_resources() -> MagicMock:
    return MagicMock(engine=MagicMock(), session_factory=MagicMock(), redis=MagicMock(), password_manager=MagicMock())


@pytest.fixture(scope="session", autouse=True)
async def assert_test_database_migration_is_current() -> AsyncIterator[None]:
    """在整个测试会话启动前验证测试数据库迁移版本与当前代码一致。

    版本不匹配时立即失败，避免集成测试因表结构缺失产生难以排查的错误。
    未配置 TEST_DATABASE_URL 时静默跳过，不影响仅运行单元测试的场景。
    """
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        yield
        return

    from sqlalchemy.ext.asyncio import create_async_engine

    from app.core.health import alembic_heads, check_database

    engine = create_async_engine(database_url, pool_pre_ping=True)
    try:
        ready, state = await check_database(engine, timeout=5)
        if not ready:
            if state == "migration_revision_mismatch":
                expected = alembic_heads()
                pytest.fail(
                    f"\n"
                    f"测试数据库迁移版本与当前代码不一致。\n"
                    f"  代码 head : {expected}\n"
                    f"  数据库状态: {state}\n"
                    f"\n"
                    f"请在 apps/backend 目录下运行以下命令升级测试数据库：\n"
                    f"\n"
                    f"  将 DATABASE_URL 安全设置为隔离测试库连接配置（禁止输出连接串）。\n"
                    f"  uv run alembic upgrade head\n"
                )
            else:
                pytest.fail(
                    f"\n"
                    f"无法连接测试数据库（状态: {state}）。\n"
                    f"  请检查 TEST_DATABASE_URL 配置，禁止在日志中输出连接串。\n"
                    f"\n"
                    f"请确认 PostgreSQL 服务已启动且测试数据库存在。\n"
                )
    finally:
        await engine.dispose()

    yield
