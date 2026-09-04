"""Lazy connection pools, owned by the application lifespan."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from prettylisavpn.config import Settings


class Postgres:
    def __init__(self, settings: Settings) -> None:
        self.engine = create_async_engine(
            settings.postgres_url.get_secret_value(),
            pool_pre_ping=True,
            pool_size=settings.postgres_pool_size,
            max_overflow=settings.postgres_max_overflow,
            pool_timeout=settings.dependency_timeout_seconds,
            connect_args={
                "timeout": settings.dependency_timeout_seconds,
                "command_timeout": settings.dependency_timeout_seconds,
            },
            hide_parameters=True,
        )
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        # Callers explicitly commit; the context rolls back uncommitted work and closes.
        async with self.session_factory() as session:
            yield session

    async def ping(self) -> None:
        async with self.engine.connect() as connection:
            await connection.execute(text("SELECT 1"))

    async def close(self) -> None:
        await self.engine.dispose()


class Valkey:
    def __init__(self, settings: Settings) -> None:
        self.client: Redis = Redis.from_url(
            settings.valkey_url.get_secret_value(),
            socket_connect_timeout=settings.dependency_timeout_seconds,
            socket_timeout=settings.dependency_timeout_seconds,
            decode_responses=True,
        )

    async def ping(self) -> None:
        if not await self.client.ping():
            raise ConnectionError("Valkey ping failed")

    async def close(self) -> None:
        await self.client.aclose()
