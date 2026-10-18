"""Upgrade historical rows in an isolated, disposable database, never the app DB."""

import asyncio
import os
import sys
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from prettylisavpn.config import Settings
from prettylisavpn.connections import Postgres
from prettylisavpn.subscriptions.repository import SubscriptionRepository
from prettylisavpn.vpn_sessions.domain import VpnSessionStatus
from prettylisavpn.vpn_sessions.repository import VpnSessionRepository
from test_vpn_sessions_integration import create_dependencies, make_session

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.getenv("RUN_INTEGRATION_TESTS") != "1", reason="Needs PostgreSQL"),
]


async def test_upgrade_preserves_canceled_paid_dates_and_backfills_utc_free_usage():
    config = Settings()
    original = make_url(config.postgres_url.get_secret_value())
    database_name = "subscription_upgrade_" + uuid4().hex
    target = original.set(database=database_name).render_as_string(hide_password=False)
    admin = create_async_engine(original, isolation_level="AUTOCOMMIT", hide_parameters=True)
    postgres = None

    async def migrate(revision):
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "alembic", "upgrade", revision,
            env={**os.environ, "POSTGRES_URL": target},
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(process.communicate(), timeout=60)
        assert process.returncode == 0, "Isolated Alembic upgrade failed"

    try:
        async with admin.connect() as connection:
            await connection.execute(text(f'CREATE DATABASE "{database_name}"'))
        await migrate("0020_support_requests")
        postgres = Postgres(Settings(_env_file=None, postgres_url=target))
        user_id, device_id, node_id = await create_dependencies(postgres)
        start = datetime(2026, 10, 16, 23, 30, tzinfo=UTC)
        end = start + timedelta(hours=1)
        legacy = make_session(user_id, device_id, node_id, 90)
        legacy = replace(
            legacy, started_at=start, created_at=start, updated_at=end,
            expires_at=end, status=VpnSessionStatus.EXPIRED, peer_removed_at=end,
        )
        paid_until = datetime.now(UTC) + timedelta(days=20)
        async with postgres.session() as session, session.begin():
            await VpnSessionRepository(session).add(legacy)
            await session.execute(text("""
                UPDATE subscriptions SET plan='PREMIUM', status='CANCELED',
                    auto_renew=true, current_period_end=:paid_until
                WHERE user_id=:user_id
            """), {"paid_until": paid_until, "user_id": user_id})
        await postgres.close()
        await migrate("head")
        async with postgres.session() as session:
            paid = await SubscriptionRepository(session).get_by_user_id(user_id)
            assert paid.current_period_end == paid_until
            assert not paid.auto_renew
            assert paid.is_active(datetime.now(UTC))
            repository = VpnSessionRepository(session)
            assert await repository.remaining_free_seconds(user_id, start) == 1800
            assert await repository.remaining_free_seconds(user_id, end) == 1800
    finally:
        if postgres is not None:
            await postgres.close()
        async with admin.connect() as connection:
            await connection.execute(text(f'DROP DATABASE IF EXISTS "{database_name}" WITH (FORCE)'))
        await admin.dispose()
