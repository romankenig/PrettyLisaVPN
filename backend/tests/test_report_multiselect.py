"""Tariff unions are filtered before account deduplication and aggregation."""

from datetime import UTC, datetime, timedelta
from itertools import combinations
from uuid import uuid4

import pytest

from prettylisavpn.product_analytics.app_versions import app_version_report
from prettylisavpn.product_analytics.domain import (
    PLANS,
    Activity,
    Attempt,
    Registration,
    boundary,
    day,
    matches_plan,
    parse_plan_filter,
    plan_key,
    selected_plans,
    snapshot,
)
from prettylisavpn.product_analytics.durations import duration_history
from prettylisavpn.product_analytics.model import AppActivityRecord

NOW = datetime(2026, 11, 17, 12, tzinfo=UTC)


def test_every_tariff_subset_has_one_canonical_key_and_an_explicit_empty_set():
    for size in range(len(PLANS) + 1):
        for subset in combinations(PLANS, size):
            value = ",".join(reversed(subset)) or "NONE"
            parsed = parse_plan_filter(value)
            assert selected_plans(parsed) == subset
            assert plan_key(parsed) == ("ALL" if subset == PLANS else ",".join(subset) or "NONE")
            for tariff in PLANS:
                assert matches_plan(tariff, parsed) is (tariff in subset)
    assert parse_plan_filter("PREMIUM,FREE,FREE") == ("FREE", "PREMIUM")
    assert parse_plan_filter("FREE,FREE") == "FREE"
    assert parse_plan_filter(None) is None


@pytest.mark.parametrize("value", ["", "FREE,", "free", "ALL", "NONE,FREE", "FREE,invalid"])
def test_invalid_or_ambiguous_tariffs_are_rejected(value):
    with pytest.raises(ValueError):
        parse_plan_filter(value)


def test_union_deduplicates_activity_and_devices_across_selected_tariffs():
    user, excluded = uuid4(), uuid4()
    start = boundary(day(NOW))
    activity = [
        Activity(user, start, "FREE"),
        Activity(user, NOW, "PREMIUM"),
        Activity(excluded, NOW, "PLATINUM"),
    ]
    attempts = [
        Attempt(start, start, None, "wireguard", "WINDOWS", user_id=user, plan=plan)
        for plan in ("FREE", "PREMIUM")
    ]

    def report(plan):
        return snapshot(
            NOW,
            activity,
            [Registration(user, start)],
            attempts,
            start,
            start,
            start,
            live=True,
            plan=plan,
        )["points"][0]

    combined = report(("FREE", "PREMIUM"))
    for metric in ("dau", "wau", "mau"):
        assert combined[metric]["total"] == 1
        assert combined[metric]["plans"]["FREE"] == 0
        assert combined[metric]["plans"]["PREMIUM"] == 1
    assert combined["new_accounts"] == 1
    assert combined["device_platforms"] == {
        "connections": {"WINDOWS": 2},
        "users": {"WINDOWS": 1},
    }
    assert report("FREE")["dau"]["total"] == 0
    empty = report(())
    assert empty["dau"]["total"] == empty["verified_sessions"] == empty["new_accounts"] == 0
    assert empty["device_platforms"] == {"connections": {}, "users": {}}


def test_daily_duration_union_uses_one_denominator_and_keeps_unknown_coverage():
    start = NOW - timedelta(minutes=10)
    attempts = [
        Attempt(
            start,
            start,
            None,
            "wireguard",
            disconnected_at=start + timedelta(seconds=n),
            first_silence_at=start + timedelta(seconds=n),
            silence_complete=True,
            plan=plan,
        )
        for plan, n in (("FREE", 5), ("PREMIUM", 30), ("PLATINUM", 300))
    ]
    report = duration_history(NOW, attempts, start, ("FREE", "PREMIUM"))
    assert report["plan"] == "FREE,PREMIUM"
    for key in ("session_duration", "time_to_silence"):
        assert report["points"][-1][key]["counts"] == [1, 1, 0, 0, 0, 0]
        assert report["points"][-1][key]["shares"] == [50, 50, 0, 0, 0, 0]
        assert report["points"][-2][key] is None
    assert duration_history(NOW, attempts, start, ())["points"][-1]["sessions"] == 0


def test_versions_union_deduplicates_accounts_across_devices():
    user = uuid4()
    rows = [
        AppActivityRecord(
            device_id=uuid4(),
            user_id=user,
            day=day(NOW),
            observed_at=NOW,
            platform="WINDOWS",
            app_version="1.0.0",
            plan=plan,
        )
        for plan in ("FREE", "PREMIUM", "PLATINUM")
    ]
    data = app_version_report(NOW, NOW, rows, ("FREE", "PREMIUM"))
    assert data["plan"] == "FREE,PREMIUM"
    platform = data["points"][-1]["platforms"]["WINDOWS"]
    assert platform == {"users": {"1.0.0": 1}, "devices": {"1.0.0": 2}, "active_users": 1}
    assert app_version_report(NOW, NOW, rows, ())["points"][-1]["platforms"] == {}
