"""Migration seeds and live database catalog filtering."""

import os
from uuid import uuid4

import pytest
from sqlalchemy import delete

from prettylisavpn.config import Settings
from prettylisavpn.connections import Postgres
from prettylisavpn.traffic.model import TrafficServiceRecord
from prettylisavpn.traffic.service import DatabaseCatalog

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1", reason="Requires disposable PostgreSQL"
    ),
]


async def test_seeded_catalog_and_disabled_service():
    postgres = Postgres(Settings(_env_file=None))
    identifier = uuid4()
    try:
        async with postgres.session() as session, session.begin():
            session.add(
                TrafficServiceRecord(
                    id=identifier,
                    slug="test-disabled",
                    name="Disabled",
                    icon="generic",
                    domains=["example.com"],
                    enabled=False,
                )
            )
        rows = await DatabaseCatalog(postgres).list_enabled()
        by_slug = {row.slug: row for row in rows}
        assert len(rows) == 20
        assert sum(row.category == "popular" for row in rows) == 10
        assert sum(row.category == "whitelist" for row in rows) == 10
        assert len({mask for row in rows for mask in row.domains}) <= 256
        assert "youtube" in by_slug and "instagram" in by_slug
        assert identifier not in {row.id for row in rows}
        assert {"youtube.com", "*.youtube.com", "*.googlevideo.com"} <= set(
            by_slug["youtube"].domains
        )
        assert {"instagram.com", "*.instagram.com", "*.cdninstagram.com"} <= set(
            by_slug["instagram"].domains
        )
    finally:
        async with postgres.session() as session, session.begin():
            await session.execute(
                delete(TrafficServiceRecord).where(TrafficServiceRecord.id == identifier)
            )
        await postgres.close()
