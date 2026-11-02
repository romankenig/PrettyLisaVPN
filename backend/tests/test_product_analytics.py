from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from test_fleet import ADMIN, MONITOR, settings

from prettylisavpn.fleet.domain import FleetError
from prettylisavpn.main import create_app
from prettylisavpn.product_analytics.activity import is_test_account, record_activity
from prettylisavpn.product_analytics.domain import (
    Activity,
    Attempt,
    boundary,
    day,
    latest_activity,
    snapshot,
    two_months_before,
)

NOW = datetime(2026, 11, 2, 9, tzinfo=UTC)
START = datetime(2026, 8, 1, tzinfo=UTC)


def data(activity=(), attempts=(), registrations=(), now=NOW, observed=START, collected=START):
    return snapshot(
        now, list(activity), list(registrations), list(attempts), observed, collected, START
    )


def test_calendar_dates_and_completed_days_only():
    assert day(datetime(2026, 11, 1, 21, tzinfo=UTC)) == date(2026, 11, 2)
    assert boundary(date(2026, 11, 2)) == datetime(2026, 11, 1, 21, tzinfo=UTC)
    assert two_months_before(date(2026, 4, 30)) == date(2026, 2, 28)
    assert two_months_before(date(2024, 4, 30)) == date(2024, 2, 29)
    assert two_months_before(date(2026, 1, 31)) == date(2025, 11, 30)
    with pytest.raises(ValueError):
        day(datetime(2026, 1, 1))
    result = data()
    assert result["from_date"] == "2026-09-02"
    assert result["through_date"] == "2026-11-01"
    assert len(result["points"]) == 61
    assert result["next_update_at"] == "2026-11-02T21:00:00+00:00"


def test_distinct_accounts_exact_windows_and_activity_time_plan():
    user, other, old, too_old = (uuid4() for _ in range(4))
    end = boundary(date(2026, 11, 2))
    values = [
        Activity(user, end - timedelta(days=10), "FREE"),
        Activity(user, end - timedelta(hours=2), "PREMIUM"),
        Activity(user, end - timedelta(hours=1), "PLATINUM"),
        Activity(other, end - timedelta(days=7), "UNKNOWN"),
        Activity(old, end - timedelta(days=30), "FREE"),
        Activity(too_old, end - timedelta(days=30, microseconds=1), "PREMIUM"),
        Activity(uuid4(), end, "FREE"),  # current day must never leak into yesterday
    ]
    point = data(values)["points"][-1]
    assert point["dau"]["total"] == 1
    assert point["wau"]["total"] == 2
    assert point["mau"]["total"] == 3
    assert point["dau"]["plans"]["PLATINUM"] == 1
    assert point["wau"]["plans"]["UNKNOWN"] == 1
    assert point["mau"]["plans"]["FREE"] == 1
    for metric in ("dau", "wau", "mau"):
        assert sum(point[metric]["plans"].values()) == point[metric]["total"]
    assert point["engagement_percent"] == 33.3
    # A currently Platinum user was still Free at the earlier point.
    earlier = next(p for p in data(values)["points"] if p["date"] == day(values[0].at).isoformat())
    assert earlier["dau"]["plans"]["FREE"] == 1


def test_missing_history_remains_missing_not_zero_and_partial_windows_are_marked():
    result = data(observed=datetime(2026, 9, 13, tzinfo=UTC), collected=NOW)
    assert result["points"][0]["mau"]["total"] is None
    assert all(value is None for value in result["points"][0]["mau"]["plans"].values())
    assert result["points"][-1]["dau"]["total"] == 0
    assert not result["points"][-1]["mau"]["complete"]
    assert result["history_partial"]


def test_late_old_observation_never_relabels_newer_activity():
    user = uuid4()
    newer = Activity(user, NOW, "PLATINUM")
    assert latest_activity(
        [newer, Activity(user, NOW - timedelta(seconds=1), "FREE"), Activity(user, NOW)]
    ) == [newer]


def test_confirmed_connections_pending_attempts_and_current_day_cutoff():
    started = boundary(date(2026, 11, 1)) + timedelta(hours=1)
    values = [
        Attempt(started, started + timedelta(seconds=20), None, "wireguard"),
        Attempt(started, None, started + timedelta(seconds=30), "vless"),
        Attempt(started, None, None, "wireguard"),
        Attempt(started, NOW, None, "wireguard"),  # not yet verified as of yesterday
    ]
    point = data(attempts=values, registrations=[started, NOW])["points"][-1]
    assert point["new_accounts"] == 1
    assert point["verified_sessions"] == 1
    assert point["connection_success_percent"] == 50
    assert point["settled_attempts"] == 2
    assert point["pending_attempts"] == 2
    assert point["median_connection_seconds"] == 20
    assert data(attempts=values)["methods"] == {"wireguard": 1}


@pytest.mark.parametrize(
    "email,excluded",
    [
        ("ci@example.com", True),
        ("ci@qa.example.test", True),
        ("ci@invalid.invalid", True),
        ("user@gmail.com", False),
        ("user@example.com.evil.org", False),
    ],
)
def test_only_reserved_test_domains_are_excluded(email, excluded):
    assert is_test_account(email) is excluded


async def test_failed_or_slow_analytics_cannot_break_authentication():
    sink = AsyncMock()
    sink.record.side_effect = RuntimeError("must never be logged")
    await record_activity(sink, uuid4())
    await record_activity(None, uuid4())


@pytest.mark.parametrize(
    "token,status", [(None, 401), ("wrong", 401), (MONITOR, 200), (ADMIN, 200)]
)
async def test_read_only_api_reuses_monitor_authorization(token, status):
    service = AsyncMock()
    service.latest.return_value = data()
    app = create_app(settings(), postgres=AsyncMock(), valkey=AsyncMock())
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client,
    ):
        app.state.product_analytics = service
        response = await client.get(
            "/admin/monitoring/product-analytics",
            headers={"Authorization": f"Bearer {token}"} if token else {},
        )
        assert response.status_code == status
        if status == 200:
            assert response.json()["through_date"] == "2026-11-01"
            service.latest.assert_awaited_once()
            service.latest.side_effect = FleetError("product_analytics_pending", 503)
            assert (
                await client.get(
                    "/admin/monitoring/product-analytics",
                    headers={"Authorization": f"Bearer {token}"},
                )
            ).status_code == 503
        else:
            service.latest.assert_not_called()
