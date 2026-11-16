"""Version identity, daily user deduplication and request-local capture."""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from test_fleet import ADMIN, MONITOR, settings

from prettylisavpn.main import create_app
from prettylisavpn.product_analytics.app_versions import (
    AppVersionContextMiddleware,
    app_version_report,
    client_version,
    normalized_version,
    record_app_activity,
)
from prettylisavpn.product_analytics.domain import day
from prettylisavpn.product_analytics.model import AppActivityRecord

NOW = datetime(2026, 11, 16, 12, tzinfo=UTC)


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, None),
        ("", None),
        ("0.28.2+build.57", "0.28.2"),
        ("1.2.0-beta.2+sha", "1.2.0-beta.2"),
        ("01.2.0", None),
        ("1.0.0-01", None),
        ("https://private.invalid/path", None),
        ("1" * 101, None),
    ],
)
def test_only_bounded_semver_is_accepted(value, expected):
    assert normalized_version(value) == expected


def test_users_deduplicated_per_platform_version_and_missing_days_stay_null():
    user, other = uuid4(), uuid4()

    def row(owner, version, platform="ANDROID", at=NOW):
        return AppActivityRecord(
            user_id=owner,
            device_id=uuid4(),
            day=day(at),
            observed_at=at,
            platform=platform,
            app_version=version,
        )

    rows = [
        row(user, "0.28.2"),
        row(user, "0.28.2"),
        row(user, "0.28.1"),
        row(other, None),
        row(user, "0.4.1", "CHROME_EXTENSION"),
        row(user, "0.4.1", "WINDOWS", NOW + timedelta(days=1)),
    ]
    report = app_version_report(NOW, NOW - timedelta(days=1), rows)
    assert len(report["points"]) == 31
    assert report["points"][-3]["platforms"] is None
    assert report["points"][-2]["platforms"] == {}
    today = report["points"][-1]
    assert today["partial"] is True
    assert today["platforms"]["ANDROID"] == {
        "users": {"0.28.1": 1, "0.28.2": 1, "UNKNOWN": 1},
        "devices": {"0.28.1": 1, "0.28.2": 2, "UNKNOWN": 1},
        "active_users": 2,
    }
    assert today["platforms"]["CHROME_EXTENSION"]["users"] == {"0.4.1": 1}
    assert "WINDOWS" not in today["platforms"]
    assert str(user) not in str(report) and "device_id" not in str(report)


def test_midnight_starts_new_partial_day_without_backfill():
    at = datetime(2026, 11, 16, 21, tzinfo=UTC)
    report = app_version_report(at, at, [])
    assert report["through_date"] == "2026-11-17"
    assert report["points"][-2]["platforms"] is None
    assert report["points"][-1]["platforms"] == {}
    assert all(p["platforms"] is None for p in app_version_report(at, None, [])["points"])


async def test_capture_failures_never_break_authorized_requests(caplog):
    sink = AsyncMock()
    sink.record.side_effect = RuntimeError("private-value")
    await record_app_activity(sink, uuid4(), uuid4(), "1.0.0")
    assert "app_activity_recording_failed" in caplog.text
    assert "private-value" not in caplog.text
    await record_app_activity(None, uuid4(), uuid4())


async def test_request_context_is_isolated_and_restored_after_errors():
    observed = []

    async def application(scope, receive, send):
        await asyncio.sleep(0)
        observed.append(client_version.get())
        if client_version.get() == "1.0.0":
            raise RuntimeError()

    middleware = AppVersionContextMiddleware(application)

    async def request(version):
        try:
            await middleware(
                {"type": "http", "headers": [(b"x-prettylisavpn-app-version", version)]},
                AsyncMock(),
                AsyncMock(),
            )
        except RuntimeError:
            pass
        assert client_version.get() is None

    await asyncio.gather(request(b"1.0.0"), request(b"2.0.0+build"), request(b"invalid"))
    assert set(observed) == {"1.0.0", "2.0.0", None}


@pytest.mark.parametrize(
    "token,status", [(None, 401), ("wrong", 401), (MONITOR, 200), (ADMIN, 200)]
)
async def test_versions_endpoint_requires_monitor_authentication(token, status):
    app = create_app(settings(), postgres=AsyncMock(), valkey=AsyncMock())
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client,
    ):
        service = AsyncMock()
        service.latest.return_value = app_version_report(NOW, NOW, [])
        app.state.app_versions = service
        response = await client.get(
            "/admin/monitoring/app-versions",
            headers={"Authorization": f"Bearer {token}"} if token else {},
        )
        assert response.status_code == status
        if status == 200:
            assert response.json() == service.latest.return_value
            service.latest.assert_awaited_once()
        else:
            service.latest.assert_not_called()
