"""Run against local Compose services or the services provided in CI."""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from prettylisavpn.config import Settings
from prettylisavpn.connections import Postgres
from prettylisavpn.main import create_app

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1",
        reason="Set RUN_INTEGRATION_TESTS=1 with PostgreSQL and Valkey running",
    ),
]


def test_real_readiness():
    with TestClient(create_app()) as client:
        response = client.get("/ready")
        assert response.status_code == 200
        assert response.json()["dependencies"] == {"postgresql": True, "valkey": True}


@pytest.mark.parametrize("failed", ["postgresql", "valkey"])
def test_real_connection_failure(failed):
    overrides = (
        {"postgres_url": "postgresql+asyncpg://unused:unused@127.0.0.1:1/unused"}
        if failed == "postgresql"
        else {"valkey_url": "redis://127.0.0.1:1/0"}
    )
    with TestClient(create_app(Settings(**overrides))) as client:
        assert client.get("/health").status_code == 200
        response = client.get("/ready")
        assert response.status_code == 503
        assert response.json()["dependencies"][failed] is False
        other = "valkey" if failed == "postgresql" else "postgresql"
        assert response.json()["dependencies"][other] is True


async def test_real_session_rolls_back_on_exception():
    pg = Postgres(Settings())
    try:
        with pytest.raises(RuntimeError):
            async with pg.session() as session:
                await session.execute(text("SELECT 1"))
                raise RuntimeError("abort transaction")
        async with pg.session() as session:
            assert (await session.execute(text("SELECT 1"))).scalar_one() == 1
    finally:
        await pg.close()
