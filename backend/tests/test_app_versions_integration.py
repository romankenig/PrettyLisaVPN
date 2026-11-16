"""Real authenticated usage, message compatibility, version updates and privacy."""

import asyncio
import os
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select, update
from test_device_management_integration import FakeDependency, create_state, headers
from test_fleet import MONITOR, settings

from prettylisavpn.auth.tokens import AccessTokenService
from prettylisavpn.connections import Postgres
from prettylisavpn.devices.domain import DevicePlatform, DeviceStatus
from prettylisavpn.devices.model import DeviceRecord
from prettylisavpn.main import create_app
from prettylisavpn.product_analytics.app_versions import AppVersionAnalytics
from prettylisavpn.product_analytics.domain import day
from prettylisavpn.product_analytics.model import AppActivityRecord
from prettylisavpn.users.model import UserRecord

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.getenv("RUN_INTEGRATION_TESTS") != "1", reason="Needs PostgreSQL"),
]


@pytest.fixture
async def version_state():
    config = settings()
    pg = Postgres(config)
    own = await create_state(pg, config, f"app-version-{uuid4()}@gmail.com", device_count=2)
    other = await create_state(pg, config, f"app-version-test-{uuid4()}@example.com")
    try:
        yield pg, config, own, other
    finally:
        async with pg.session() as session, session.begin():
            await session.execute(
                delete(UserRecord).where(UserRecord.id.in_([own.user.id, other.user.id]))
            )
        await pg.close()


async def test_concurrent_daily_capture_version_upgrades_old_writes_and_ownership(version_state):
    pg, _, own, other = version_state
    service = AppVersionAnalytics(pg)
    now = datetime(2097, 10, 16, 12, tzinfo=UTC)
    device = own.devices[0].id
    await asyncio.gather(
        *(service.record(own.user.id, device, "1.0.0+build", now=now) for _ in range(4))
    )
    await service.record(own.user.id, device, "1.1.0", now=now + timedelta(seconds=1))
    await service.record(own.user.id, device, "0.9.0", now=now - timedelta(seconds=1))
    await service.record(own.user.id, device, None, now=now + timedelta(seconds=2))
    await service.record(own.user.id, device, None, now=now + timedelta(days=1))
    await service.record(other.user.id, other.devices[0].id, "9.0.0", now=now)
    await service.record(own.user.id, other.devices[0].id, "9.0.0", now=now)
    async with pg.session() as session:
        rows = list(
            await session.scalars(
                select(AppActivityRecord).where(
                    AppActivityRecord.user_id.in_([own.user.id, other.user.id])
                )
            )
        )
        assert len(rows) == 2
        first = next(row for row in rows if row.day == day(now))
        assert first.app_version == "1.1.0" and first.observed_at == now + timedelta(seconds=2)
        assert first.version_observed_at == now + timedelta(seconds=1)
        assert next(row for row in rows if row.day != day(now)).app_version is None
    report = await service.latest(now + timedelta(days=1))
    assert report["points"][-2]["platforms"]["WINDOWS"]["users"] == {"1.1.0": 1}
    assert report["points"][-1]["platforms"]["WINDOWS"]["users"] == {"UNKNOWN": 1}


async def test_existing_messages_and_new_headers_capture_only_valid_authenticated_devices(
    version_state,
):
    pg, config, own, other = version_state
    async with pg.session() as session, session.begin():
        await session.execute(
            update(DeviceRecord)
            .where(DeviceRecord.id == own.devices[1].id)
            .values(platform=DevicePlatform.CHROME_EXTENSION)
        )
    chrome_token = (
        AccessTokenService(config)
        .issue(own.user.id, own.devices[1].id, own.sessions[1].session.id)
        .token
    )
    app = create_app(config, postgres=pg, valkey=FakeDependency(), product_events=AsyncMock())
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client,
    ):
        assert (
            await client.get("/me", headers={"X-PrettyLisaVPN-App-Version": "99.0.0"})
        ).status_code == 401
        assert (await client.get("/me", headers=headers(own.access_token))).status_code == 200
        params = {
            "platform": "WINDOWS",
            "app_version": "1.0.0+build.1",
            "locale": "en",
            "schema_version": "1",
        }
        assert (
            await client.get("/messages", params=params, headers=headers(own.access_token))
        ).status_code == 200
        assert (
            await client.get(
                "/messages",
                params={**params, "platform": "ANDROID", "app_version": "9.0.0"},
                headers=headers(own.access_token),
            )
        ).status_code == 200
        assert (
            await client.get(
                "/me", headers={**headers(chrome_token), "X-PrettyLisaVPN-App-Version": "0.4.1"}
            )
        ).status_code == 200
        # Missing/bad metadata cannot erase today's known version or fail a request.
        assert (
            await client.get(
                "/me",
                headers={**headers(chrome_token), "X-PrettyLisaVPN-App-Version": "not-a-version"},
            )
        ).status_code == 200
        assert (await client.get("/me", headers=headers(other.access_token))).status_code == 200
        report = (
            await client.get("/admin/monitoring/app-versions", headers=headers(MONITOR))
        ).json()
        today = report["points"][-1]["platforms"]
        assert today["WINDOWS"]["users"].get("1.0.0") == 1
        assert today["CHROME_EXTENSION"]["users"].get("0.4.1") == 1
        assert "9.0.0" not in str(report) and "99.0.0" not in str(report)
        assert own.user.email not in str(report) and str(own.user.id) not in str(report)
        async with pg.session() as session:
            rows = list(
                await session.scalars(
                    select(AppActivityRecord).where(
                        AppActivityRecord.user_id.in_([own.user.id, other.user.id])
                    )
                )
            )
            assert len(rows) == 2


async def test_pending_cabinet_with_version_metadata_records_usage_only_after_activation(
    version_state,
):
    pg, config, own, _ = version_state
    device_id = own.devices[0].id
    async with pg.session() as session, session.begin():
        await session.execute(
            update(DeviceRecord)
            .where(DeviceRecord.id == device_id)
            .values(status=DeviceStatus.PENDING)
        )
    app = create_app(config, postgres=pg, valkey=FakeDependency(), product_events=AsyncMock())
    version_headers = {**headers(own.access_token), "X-PrettyLisaVPN-App-Version": "0.5.0"}
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client,
    ):
        profile = await client.get("/me", headers=version_headers)
        assert profile.status_code == 200 and profile.json()["device_limit_reached"] is True
        assert (await client.get("/devices", headers=version_headers)).status_code == 200
        assert (await client.get("/billing/overview", headers=version_headers)).status_code == 403
        async with pg.session() as session:
            assert (
                await session.scalar(
                    select(AppActivityRecord).where(AppActivityRecord.device_id == device_id)
                )
                is None
            )
        assert (await client.post("/devices/activate", headers=version_headers)).status_code == 200
        profile = await client.get("/me", headers=version_headers)
        assert profile.status_code == 200 and profile.json()["device_limit_reached"] is False
        async with pg.session() as session:
            usage = await session.scalar(
                select(AppActivityRecord).where(AppActivityRecord.device_id == device_id)
            )
            assert usage is not None and usage.app_version == "0.5.0"
