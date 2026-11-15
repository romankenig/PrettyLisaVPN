"""Current-day cutoff, rolling cohorts and already completed duration observations."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from prettylisavpn.product_analytics.domain import Activity, Attempt, boundary, day, snapshot

NOW = datetime(2026, 11, 15, 12, tzinfo=UTC)
MIDNIGHT = boundary(day(NOW))


def live(activity=(), registrations=(), attempts=(), now=NOW):
    start = MIDNIGHT - timedelta(days=90)
    return snapshot(
        now, list(activity), list(registrations), list(attempts), start, start, start, live=True
    )


def test_current_audience_uses_latest_observed_plan_and_exact_rolling_calendar_windows():
    user = uuid4()
    activity = [
        Activity(user, MIDNIGHT, "FREE"),
        Activity(user, NOW, "PREMIUM"),
        Activity(user, NOW + timedelta(seconds=1), "PLATINUM"),
        Activity(uuid4(), MIDNIGHT - timedelta(days=6), "DEMO"),
        Activity(uuid4(), MIDNIGHT - timedelta(days=6, microseconds=1), "FREE"),
        Activity(uuid4(), MIDNIGHT - timedelta(days=29), "PLATINUM"),
        Activity(uuid4(), MIDNIGHT - timedelta(days=29, microseconds=1), "UNKNOWN"),
    ]
    result = live(
        activity, [MIDNIGHT - timedelta(microseconds=1), MIDNIGHT, NOW, NOW + timedelta(seconds=1)]
    )
    assert len(result["points"]) == 1
    point = result["points"][0]
    assert point["date"] == "2026-11-15"
    assert [point[key]["total"] for key in ("dau", "wau", "mau")] == [1, 2, 4]
    assert point["dau"]["plans"]["PREMIUM"] == 1
    assert point["wau"]["plans"]["DEMO"] == 1
    assert point["new_accounts"] == 2
    assert point["engagement_percent"] == 25
    for key in ("dau", "wau", "mau"):
        assert sum(point[key]["plans"].values()) == point[key]["total"]


def test_current_attempts_exclude_pending_and_future_results_and_include_completed_observations():
    user = uuid4()
    started = MIDNIGHT + timedelta(seconds=1)
    attempts = [
        Attempt(
            MIDNIGHT,
            started,
            None,
            "https_proxy",
            "CHROME_EXTENSION",
            disconnected_at=started + timedelta(seconds=60),
            first_silence_at=started + timedelta(seconds=10),
            silence_complete=True,
            user_id=user,
        ),
        Attempt(MIDNIGHT, None, MIDNIGHT + timedelta(seconds=30), "wireguard", user_id=user),
        Attempt(MIDNIGHT, None, None, "wireguard", user_id=user),
        Attempt(MIDNIGHT, NOW + timedelta(seconds=1), None, "wireguard", user_id=user),
        Attempt(MIDNIGHT, NOW, None, "https_proxy", "CHROME_EXTENSION", user_id=user),
        Attempt(NOW + timedelta(seconds=1), None, None, "wireguard", user_id=user),
    ]
    result = live(attempts=attempts)
    point = result["points"][0]
    assert point["verified_sessions"] == 2
    assert point["settled_attempts"] == 3
    assert point["pending_attempts"] == 2
    assert point["connection_success_percent"] == 66.7
    assert point["device_platforms"] == {
        "connections": {"CHROME_EXTENSION": 2},
        "users": {"CHROME_EXTENSION": 1},
    }
    assert point["mean_session_seconds"] == result["mean_session_seconds"] == 60
    assert point["completed_sessions"] == 1
    assert result["session_duration"]["counts"] == [0, 1, 0, 0, 0, 0]
    assert result["time_to_silence"]["counts"] == [1, 0, 0, 0, 0, 0]
    assert result["duration_unobserved_sessions"] == result["silence_unobserved_sessions"] == 1


def test_cross_midnight_session_is_counted_on_disconnect_day_and_silence_requires_confirmation():
    verified = MIDNIGHT - timedelta(seconds=20)
    attempt = Attempt(
        verified,
        verified,
        None,
        "wireguard",
        disconnected_at=NOW,
        first_silence_at=NOW - timedelta(seconds=9),
        silence_complete=True,
    )
    result = live(attempts=[attempt])
    point = result["points"][0]
    assert point["verified_sessions"] == 0
    assert point["completed_sessions"] == 1
    assert result["session_duration"]["samples"] == 1
    assert result["time_to_silence"]["samples"] == 0
    assert (
        live(attempts=[attempt], now=NOW + timedelta(seconds=1))["time_to_silence"]["samples"] == 1
    )
    rollover = live(attempts=[attempt], now=MIDNIGHT + timedelta(days=1))
    assert rollover["points"][0]["date"] == "2026-11-16"
    assert rollover["points"][0]["completed_sessions"] == 0
    assert rollover["points"][0]["mean_session_seconds"] is None
    assert rollover["session_duration"]["samples"] == 1


def test_current_empty_day_is_observed_even_before_the_first_lease():
    result = snapshot(NOW, [], [], [], NOW, NOW, None, live=True)
    point = result["points"][0]
    assert point["device_platforms"] == {"connections": {}, "users": {}}
    assert point["verified_sessions"] == point["settled_attempts"] == 0
    assert point["connection_success_percent"] is None
