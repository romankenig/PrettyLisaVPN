"""Historical tariff boundaries and daily duration cohorts, independent of storage."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from test_fleet import MONITOR, settings

from prettylisavpn.client_vpn.model import ClientLeaseRecord
from prettylisavpn.main import create_app
from prettylisavpn.product_analytics.app_versions import app_version_report
from prettylisavpn.product_analytics.domain import (
    Activity,
    Attempt,
    Registration,
    boundary,
    day,
    snapshot,
)
from prettylisavpn.product_analytics.durations import duration_history
from prettylisavpn.product_analytics.model import AppActivityRecord
from prettylisavpn.product_analytics.plans import lease_plan

NOW = datetime(2026, 11, 17, 12, tzinfo=UTC)
START = boundary(day(NOW))


def test_duration_bins_are_daily_start_cohorts_and_keep_missing_separate_from_zero():
    at = START - timedelta(seconds=5)
    attempts = [
        Attempt(
            at,
            at,
            None,
            "wireguard",
            disconnected_at=at + timedelta(seconds=n),
            first_silence_at=at + timedelta(seconds=n),
            silence_complete=True,
        )
        for n in (0, 10, 11, 60, 61, 180, 181, 300, 301, 900, 901)
    ]
    attempts += [Attempt(at, at, None, "wireguard"), Attempt(START, None, START, "wireguard")]
    result = duration_history(NOW, attempts, at)
    previous, today = result["points"][-2:]
    assert previous["sessions"] == 12
    for kind in ("session_duration", "time_to_silence"):
        assert previous[kind]["counts"] == [2, 2, 2, 2, 2, 1]
        assert sum(previous[kind]["shares"]) == pytest.approx(100)
        assert today[kind]["counts"] == [0] * 6
        assert today[kind]["shares"] == [None] * 6
    assert previous["duration_unobserved_sessions"] == previous["silence_unobserved_sessions"] == 1
    assert result["points"][-3]["session_duration"] is None
    assert today["partial"] and not previous["partial"]


def test_late_completion_updates_start_day_and_silence_requires_ten_seconds():
    at = START - timedelta(seconds=30)
    pending = Attempt(at, at, None, "wireguard", plan="PREMIUM")
    completed = replace(
        pending,
        disconnected_at=NOW,
        first_silence_at=NOW - timedelta(seconds=9),
        silence_complete=True,
    )
    first = duration_history(NOW, [pending], at)["points"][-2]
    second = duration_history(NOW, [completed], at)["points"][-2]
    third = duration_history(NOW + timedelta(seconds=1), [completed], at)["points"][-2]
    assert first["session_duration"]["samples"] == 0
    assert second["session_duration"]["samples"] == 1
    assert second["time_to_silence"]["samples"] == 0
    assert third["time_to_silence"]["samples"] == 1
    assert duration_history(NOW, [completed], at, "FREE")["points"][-2]["sessions"] == 0
    future = replace(pending, verified_at=NOW + timedelta(seconds=1))
    invalid = replace(pending, verified_at=at - timedelta(seconds=1))
    assert duration_history(NOW, [future, invalid], at)["points"][-1]["sessions"] == 0


def test_audience_filter_follows_latest_window_activity_before_filtering():
    user, absent = uuid4(), uuid4()
    old = START - timedelta(days=1)
    activity = [Activity(user, old, "FREE"), Activity(user, NOW, "PREMIUM")]
    attempts = [
        Attempt(old, old, None, "wireguard", plan="FREE", user_id=user, disconnected_at=NOW)
    ]

    def report(plan):
        return snapshot(
            NOW,
            activity,
            [Registration(user, old), Registration(absent, old)],
            attempts,
            old,
            old,
            old,
            plan=plan,
        )

    free = report("FREE")["points"][-1]
    assert free["dau"]["total"] == free["new_accounts"] == 1
    assert report("UNKNOWN")["points"][-1]["new_accounts"] == 1
    for plan, count in [("FREE", 0), ("PREMIUM", 1)]:
        live = snapshot(NOW, activity, [], attempts, old, old, old, live=True, plan=plan)
        assert [live["points"][0][metric]["total"] for metric in ("dau", "wau", "mau")] == [
            count
        ] * 3
        assert live["session_duration"]["samples"] == (1 if plan == "FREE" else 0)


@pytest.mark.parametrize(
    "stored,free,email,expected",
    [
        (None, False, "user@gmail.com", "UNKNOWN"),
        (None, True, "user@gmail.com", "FREE"),
        (None, True, "guest@demo.prettylisavpn.com", "DEMO"),
        ("PLATINUM", False, "user@gmail.com", "PLATINUM"),
        ("PREMIUM", False, "user@gmail.com", "PREMIUM"),
    ],
)
def test_legacy_paid_plans_are_never_guessed(stored, free, email, expected):
    assert lease_plan(ClientLeaseRecord(plan_snapshot=stored, is_free=free), email) == expected


def test_version_plan_is_activity_snapshot_and_legacy_is_unknown():
    rows = [
        AppActivityRecord(
            device_id=uuid4(),
            user_id=uuid4(),
            day=day(NOW),
            observed_at=NOW,
            platform="WINDOWS",
            app_version="1.0.0",
            plan=plan,
        )
        for plan in (None, "FREE", "PREMIUM")
    ]
    for plan in ("FREE", "PREMIUM", "UNKNOWN"):
        result = app_version_report(NOW, NOW, rows, plan)
        assert result["plan"] == plan
        assert result["points"][-1]["platforms"]["WINDOWS"]["active_users"] == 1
    assert app_version_report(NOW, NOW, rows, "DEMO")["points"][-1]["platforms"] == {}


@pytest.mark.parametrize(
    "path,state,method,target",
    [
        ("product-analytics", "product_analytics", "latest", None),
        ("app-versions", "app_versions", "latest", None),
        ("connection-methods", None, "report", "prettylisavpn.fleet.method_checks.MethodAnalytics"),
        ("services", None, "report", "prettylisavpn.fleet.service_checks.ServiceAnalytics"),
        (
            "active-user-speed",
            None,
            "history",
            "prettylisavpn.fleet.traffic_service.TrafficService",
        ),
    ],
)
async def test_report_plan_contract_validates_and_keeps_auth(path, state, method, target):
    app = create_app(settings(), postgres=AsyncMock(), valkey=AsyncMock())
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client,
    ):
        service = AsyncMock()
        getattr(service, method).return_value = {"plan": "FREE"}
        if state:
            setattr(app.state, state, service)
        # Fleet routes construct readers locally; product readers live in app state.
        from contextlib import nullcontext

        with patch(target, return_value=service) if target else nullcontext():
            url = "/admin/monitoring/" + path
            auth = {"Authorization": f"Bearer {MONITOR}"}
            assert (await client.get(url, params={"plan": "FREE"}, headers=auth)).status_code == 200
            assert getattr(service, method).await_args.kwargs["plan"] == "FREE"
            for query, expected in [
                ("plan=PREMIUM,FREE,FREE", ("FREE", "PREMIUM")),
                ("plan=FREE&plan=PREMIUM", ("FREE", "PREMIUM")),
                ("plan=NONE", ()),
                ("plan=DEMO,FREE,PREMIUM,PLATINUM,UNKNOWN", None),
            ]:
                assert (await client.get(url + "?" + query, headers=auth)).status_code == 200
                assert getattr(service, method).await_args.kwargs["plan"] == expected
            for invalid in ("NONE,FREE", "FREE,invalid", "FREE,", ""):
                assert (
                    await client.get(url, params={"plan": invalid}, headers=auth)
                ).status_code == 422
            assert (await client.get(url, params={"plan": "ALL"}, headers=auth)).status_code == 422
            assert (await client.get(url, params={"plan": "FREE"})).status_code == 401
            assert (await client.get(url, params={"plan": "FREE,PREMIUM"})).status_code == 401
