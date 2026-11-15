from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

from prettylisavpn.product_analytics.domain import Attempt, boundary, device_platforms, snapshot


def test_daily_platforms_deduplicate_accounts_per_platform_and_verification_day():
    first, second = uuid4(), uuid4()
    midnight = boundary(date(2026, 11, 14))
    before, after = midnight - timedelta(seconds=1), midnight + timedelta(seconds=1)
    now = datetime(2026, 11, 15, 10, tzinfo=UTC)

    def attempt(at, platform, user):
        return Attempt(before - timedelta(minutes=1), at, None, "wireguard", platform, user_id=user)

    attempts = [
        attempt(before, "ANDROID", first),
        attempt(before, "ANDROID", first),
        attempt(before, "ANDROID", second),
        attempt(before, "WINDOWS", first),
        attempt(after, "ANDROID", first),
        attempt(after, "UNKNOWN", second),
        attempt(None, "IOS", first),
        attempt(now, "IOS", first),
    ]
    result = snapshot(now, [], [], attempts, before, before, before)
    points = {p["date"]: p for p in result["points"]}
    assert points["2026-11-12"]["device_platforms"] == {"connections": None, "users": None}
    assert points["2026-11-13"]["device_platforms"] == {
        "connections": {"ANDROID": 3, "WINDOWS": 1},
        "users": {"ANDROID": 2, "WINDOWS": 1},
    }
    assert points["2026-11-14"]["device_platforms"] == {
        "connections": {"ANDROID": 1, "UNKNOWN": 1},
        "users": {"ANDROID": 1, "UNKNOWN": 1},
    }
    assert result["devices"] == {"ANDROID": 4, "UNKNOWN": 1, "WINDOWS": 1}
    assert result["metrics_revision"] == 3
    assert str(first) not in str(result) and str(second) not in str(result)


def test_daily_platforms_distinguish_empty_day_missing_history_and_missing_identity():
    assert device_platforms([], True) == {"connections": {}, "users": {}}
    assert device_platforms([], False) == {"connections": None, "users": None}
    now = datetime(2026, 11, 14, tzinfo=UTC)
    old = Attempt(now, now, None, "wireguard", "WINDOWS")
    assert device_platforms([old], True) == {"connections": {"WINDOWS": 1}, "users": None}
