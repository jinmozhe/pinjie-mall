from dataclasses import dataclass

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from .config import Settings
from .redis import create_redis_client
from .security import PasswordManager


@dataclass(slots=True)
class AppResources:
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    redis: Redis | None
    password_manager: PasswordManager
    settings_media_ready: bool = False

    async def close(self) -> None:
        if self.redis is not None:
            await self.redis.aclose()
        await self.engine.dispose()


def create_resources(settings: Settings) -> AppResources:
    if not settings.database_url:
        raise ValueError("DATABASE_URL is required before resources can be created")
    engine = create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout,
        pool_recycle=1800,
        echo=settings.debug,
        hide_parameters=True,
        native_inet_types=False,
        connect_args={"server_settings": {"lock_timeout": f"{max(1, int(settings.db_lock_timeout * 1000))}ms"}},
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    return AppResources(
        engine=engine,
        session_factory=session_factory,
        redis=create_redis_client(settings),
        password_manager=PasswordManager(settings.password_hash_concurrency),
    )
