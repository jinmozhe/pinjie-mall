from dataclasses import dataclass

import httpx
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
    wechat_http: httpx.AsyncClient | None = None

    async def close(self) -> None:
        try:
            if self.redis is not None:
                await self.redis.aclose()
        finally:
            try:
                if self.wechat_http is not None:
                    await self.wechat_http.aclose()
            finally:
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
        wechat_http=httpx.AsyncClient(
            timeout=httpx.Timeout(4.0, connect=2.0, pool=1.0),
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            trust_env=False,
            follow_redirects=False,
        )
        if settings.miniapp_login_enabled
        else None,
    )
