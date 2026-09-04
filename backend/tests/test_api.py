import asyncio
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from prettylisavpn.config import Settings
from prettylisavpn.main import create_app


def settings(**overrides):
    return Settings(_env_file=None, **overrides)


def provider(fails=False):
    result = AsyncMock()
    if fails:
        result.ping.side_effect = RuntimeError("secret-password redis://private-host")
    return result


def test_liveness_and_version_never_ping_dependencies():
    pg, cache = provider(True), provider(True)
    config = settings(
        application_name="PrettyLisaVPN", application_version="1.2.3", environment="test"
    )
    with TestClient(create_app(config, postgres=pg, valkey=cache)) as client:
        assert client.get("/health").json() == {"status": "ok"}
        response = client.get("/version")
        assert response.status_code == 200
        assert response.json() == {
            "application_name": "PrettyLisaVPN",
            "application_version": "1.2.3",
            "environment": "test",
        }
    pg.ping.assert_not_awaited()
    cache.ping.assert_not_awaited()
    pg.close.assert_awaited_once()
    cache.close.assert_awaited_once()


@pytest.mark.parametrize(
    "pg_fails,cache_fails", [(False, False), (True, False), (False, True), (True, True)]
)
def test_readiness_checks_both_dependencies(pg_fails, cache_fails, caplog):
    pg, cache = provider(pg_fails), provider(cache_fails)
    with TestClient(create_app(settings(), postgres=pg, valkey=cache)) as client:
        response = client.get("/ready")
    assert response.status_code == (503 if pg_fails or cache_fails else 200)
    assert response.json()["dependencies"] == {
        "postgresql": not pg_fails,
        "valkey": not cache_fails,
    }
    if pg_fails or cache_fails:
        assert response.json()["error"]["code"] == "dependencies_unavailable"
    pg.ping.assert_awaited_once()
    cache.ping.assert_awaited_once()
    assert "secret-password" not in response.text + caplog.text
    assert "private-host" not in response.text + caplog.text


def test_timeout_returns_unavailable_and_liveness_still_works():
    async def hang():
        await asyncio.Event().wait()

    pg, cache = provider(), provider()
    pg.ping.side_effect = hang
    with TestClient(
        create_app(settings(dependency_timeout_seconds=0.01), postgres=pg, valkey=cache)
    ) as client:
        assert client.get("/ready").status_code == 503
        assert client.get("/health").status_code == 200
    cache.ping.assert_awaited_once()


def test_safe_errors(caplog):
    app = create_app(settings(), postgres=provider(), valkey=provider())

    @app.get("/explode")
    async def explode():
        raise RuntimeError("secret-password https://private-host")

    @app.get("/validate")
    async def validate(count: int):
        return count

    with TestClient(app) as client:
        response = client.get("/explode")
        assert response.status_code == 500
        assert response.json() == {"error": {"code": "internal_error"}}
        assert client.get("/missing").json() == {"error": {"code": "not_found"}}
        assert client.post("/health").json() == {"error": {"code": "method_not_allowed"}}
        validation = client.get("/validate?count=secret-password")
        assert validation.status_code == 422
        assert validation.json() == {"error": {"code": "validation_error"}}
    assert "secret-password" not in response.text + caplog.text
    assert "private-host" not in response.text + caplog.text


def test_health_with_real_clients_does_not_connect(monkeypatch):
    pg_connect = AsyncMock(side_effect=AssertionError("Unexpected PostgreSQL access"))
    cache_connect = AsyncMock(side_effect=AssertionError("Unexpected Valkey access"))
    monkeypatch.setattr("asyncpg.connect", pg_connect)
    monkeypatch.setattr("redis.asyncio.connection.Connection.connect", cache_connect)
    with TestClient(create_app(settings())) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/version").status_code == 200
    pg_connect.assert_not_awaited()
    cache_connect.assert_not_awaited()
