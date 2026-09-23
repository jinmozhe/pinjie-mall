import asyncio
import functools
from dataclasses import dataclass
from pathlib import Path

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from .config import Settings
from .redis import check_redis
from .resources import AppResources


@dataclass(frozen=True, slots=True)
class ReadinessResult:
    ready: bool
    checks: dict[str, str]


@functools.lru_cache(maxsize=1)
def alembic_heads() -> tuple[str, ...]:
    backend_root = Path(__file__).resolve().parents[2]
    config = Config(str(backend_root / "alembic.ini"))
    config.set_main_option("script_location", str(backend_root / "alembic"))
    return tuple(ScriptDirectory.from_config(config).get_heads())


async def check_database(engine: AsyncEngine, timeout: float) -> tuple[bool, str]:
    try:
        async with asyncio.timeout(timeout):
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
                current_heads = await connection.run_sync(
                    lambda sync_connection: tuple(MigrationContext.configure(sync_connection).get_current_heads())
                )
                expected_heads = alembic_heads()
                if tuple(current_heads) != expected_heads:
                    return False, "migration_revision_mismatch"
                return True, "ok"
    except TimeoutError:
        return False, "timeout"
    except Exception as exc:
        # 记录异常供运维诊断，避免静默丢弃错误信息
        logger.opt(exception=exc).warning("database health check failed")
        return False, "unavailable"


async def check_readiness(resources: AppResources, settings: Settings) -> ReadinessResult:
    database_ok, database_state = await check_database(resources.engine, settings.dependency_timeout)
    checks = {"database": database_state}
    checks["settings_media"] = "ok" if resources.settings_media_ready else "unavailable"
    if settings.redis_mode == "required":
        redis_ok = await check_redis(resources.redis, settings.dependency_timeout)
        checks["redis"] = "ok" if redis_ok else "unavailable"
    ready = database_ok and all(value == "ok" for value in checks.values())
    return ReadinessResult(ready=ready, checks=checks)
