from dataclasses import replace
from datetime import UTC, datetime, timedelta

from prettylisavpn.fleet.selection_history import SessionInterval, selection_history
from prettylisavpn.product_analytics.domain import boundary, day

NOW = datetime(2026, 11, 16, 12, tzinfo=UTC)
START = boundary(day(NOW))
CATALOG = {"one": ("youtube", "YouTube"), "two": ("telegram", "Telegram")}


def interval(**changes):
    row = SessionInterval(
        START,
        NOW + timedelta(days=1),
        NOW + timedelta(days=1),
        "wireguard",
        "include",
        ("one",),
        False,
    )
    return replace(row, **changes)


def history(rows, kind="methods", observed=START - timedelta(days=7), now=NOW):
    return selection_history(now, rows, observed, kind, CATALOG)


def test_long_sessions_count_once_on_every_overlapping_day_and_midnight_is_exclusive():
    long = interval(
        verified_at=START - timedelta(days=2, hours=-1), ended_at=START + timedelta(seconds=1)
    )
    midnight = interval(
        verified_at=START - timedelta(hours=1), ended_at=START, method="wireguard_relay"
    )
    points = history([long, midnight])["points"]
    assert len(points) == 8
    assert [p["date"] for p in points[-3:]] == ["2026-11-14", "2026-11-15", "2026-11-16"]
    assert points[-3]["counts"] == {"wireguard": 1}
    assert points[-2]["counts"] == {"wireguard": 1, "wireguard_relay": 1}
    assert points[-1]["counts"] == {"wireguard": 1}
    assert [p["partial"] for p in points] == [False] * 7 + [True]


def test_expiry_caps_overlap_future_verifications_are_excluded_and_zero_length_is_observed():
    rows = [
        interval(verified_at=START - timedelta(hours=1), expires_at=START),
        interval(verified_at=NOW + timedelta(microseconds=1)),
        interval(verified_at=NOW, ended_at=NOW),
        interval(verified_at=NOW, expires_at=START),
        interval(verified_at=NOW, ended_at=START),
    ]
    points = history(rows)["points"]
    assert points[-2]["total"] == 1
    assert points[-1]["total"] == 1


def test_service_marks_deduplicate_per_session_and_unknown_rules_without_counting_all_traffic():
    rows = [
        interval(service_ids=("one", "one", "not-in-catalog"), custom_rules=True),
        interval(service_ids=("one", "two")),
        interval(traffic_mode="all"),
    ]
    point = history(rows, "services")["points"][-1]
    assert point["counts"] == {"UNKNOWN": 1, "telegram": 1, "youtube": 2}
    assert point["total"] == 4 and point["active_sessions"] == point["observed_sessions"] == 2
    assert point["complete"]
    assert "not-in-catalog" not in str(history(rows, "services"))


def test_missing_service_metadata_and_modes_remain_missing_or_partial_not_zero():
    missing = interval(service_ids=None, custom_rules=None)
    legacy = interval(traffic_mode=None, service_ids=None, custom_rules=None)
    empty = history([missing, legacy], "services")["points"][-1]
    assert empty["counts"] is empty["total"] is None
    assert empty["active_sessions"] == empty["unknown_mode_sessions"] == 1
    assert not empty["complete"]
    partial = history([missing, legacy, interval()], "services")["points"][-1]
    assert partial["counts"] == {"youtube": 1}
    assert partial["observed_sessions"] == 1 and partial["active_sessions"] == 2
    assert not partial["complete"]
    assert history([interval(traffic_mode="all")], "services")["points"][-1]["counts"] == {}


def test_terminal_legacy_rows_without_end_never_invent_later_open_days():
    old = interval(verified_at=START - timedelta(days=2), ended_at=None)
    points = history([old])["points"]
    assert points[-3]["total"] == 1
    assert points[-2]["total"] is None and points[-2]["uncertain_sessions"] == 1
    assert points[-1]["total"] is None
    partial = history([old, interval()])["points"][-1]
    assert partial["total"] == 1 and not partial["complete"]
    # Unknown lifecycle of a known all-traffic session cannot hide known zero service selections.
    assert history([replace(old, traffic_mode="all")], "services")["points"][-1]["counts"] == {}


def test_coverage_empty_day_unknown_method_and_midnight_rollover():
    points = history([], observed=None)["points"]
    assert points[0]["total"] is None and points[-1]["total"] == 0
    assert history([interval(method="future-method")])["points"][-1]["counts"] == {"UNKNOWN": 1}
    result = history([interval(ended_at=NOW)], now=START + timedelta(days=1))
    assert result["through_date"] == "2026-11-17"
    assert result["points"][-1]["total"] == 0 and result["points"][-2]["total"] == 1
