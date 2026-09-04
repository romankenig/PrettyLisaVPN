from unittest.mock import AsyncMock, MagicMock

import pytest

from prettylisavpn.config import Settings
from prettylisavpn.connections import Postgres, Valkey


async def test_postgres_executes_query_and_disposes_engine(monkeypatch):
    connection = AsyncMock()
    engine = MagicMock()
    engine.connect.return_value.__aenter__ = AsyncMock(return_value=connection)
    engine.dispose = AsyncMock()
    monkeypatch.setattr("prettylisavpn.connections.create_async_engine", lambda *a, **kw: engine)
    pg = Postgres(Settings(_env_file=None))
    await pg.ping()
    assert str(connection.execute.await_args.args[0]) == "SELECT 1"
    engine.connect.return_value.__aexit__.assert_awaited_once()
    await pg.close()
    engine.dispose.assert_awaited_once()


async def test_session_context_exits_on_failure():
    pg = Postgres(Settings(_env_file=None))
    factory = MagicMock()
    session = AsyncMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    pg.session_factory = factory
    try:
        with pytest.raises(RuntimeError):
            async with pg.session() as actual:
                assert actual is session
                raise RuntimeError("abort")
        factory.return_value.__aexit__.assert_awaited_once()
        session.commit.assert_not_awaited()
    finally:
        await pg.close()


async def test_valkey_pings_and_closes(monkeypatch):
    client = AsyncMock()
    monkeypatch.setattr("prettylisavpn.connections.Redis.from_url", lambda *a, **kw: client)
    cache = Valkey(Settings(_env_file=None))
    await cache.ping()
    client.ping.assert_awaited_once()
    client.ping.return_value = False
    with pytest.raises(ConnectionError):
        await cache.ping()
    await cache.close()
    client.aclose.assert_awaited_once()
