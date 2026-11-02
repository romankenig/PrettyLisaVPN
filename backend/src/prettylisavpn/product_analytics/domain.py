"""Calendar windows and activity-time cohorts, independent of storage and HTTP."""

import calendar
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, timezone
from statistics import median
from typing import Any, Literal
from uuid import UUID

MOSCOW = timezone(timedelta(hours=3))
Plan = Literal["FREE", "PREMIUM", "PLATINUM", "UNKNOWN"]
PLANS: tuple[Plan, ...] = ("FREE", "PREMIUM", "PLATINUM", "UNKNOWN")


def day(at: datetime) -> date:
    if at.tzinfo is None:
        raise ValueError("Activity timestamps must be timezone-aware")
    return at.astimezone(MOSCOW).date()


def boundary(value: date) -> datetime:
    return datetime.combine(value, time.min, MOSCOW).astimezone(UTC)


def two_months_before(value: date) -> date:
    month = value.year * 12 + value.month - 1 - 2
    year, zero_month = divmod(month, 12)
    return date(year, zero_month + 1, min(value.day, calendar.monthrange(year, zero_month + 1)[1]))


@dataclass(frozen=True)
class Activity:
    user_id: UUID
    at: datetime
    plan: Plan = "UNKNOWN"


@dataclass(frozen=True)
class Attempt:
    created_at: datetime
    verified_at: datetime | None
    removed_at: datetime | None
    method: str


def latest_activity(values: list[Activity]) -> list[Activity]:
    """One row per user/day; late old writes never erase newer evidence."""
    rows: dict[tuple[UUID, date], Activity] = {}
    for value in values:
        key = (value.user_id, day(value.at))
        old = rows.get(key)
        if old is None or (value.at, value.plan != "UNKNOWN") > (old.at, old.plan != "UNKNOWN"):
            rows[key] = value
    return list(rows.values())


def snapshot(
    now: datetime,
    activity: list[Activity],
    registrations: list[datetime],
    attempts: list[Attempt],
    observed_from: datetime | None,
    collected_from: datetime,
    attempts_from: datetime | None,
) -> dict[str, Any]:
    today = day(now)
    start, through = two_months_before(today), today - timedelta(days=1)
    cutoff = boundary(today)
    values = sorted(
        (item for item in latest_activity(activity) if item.at < cutoff), key=lambda a: a.at
    )
    # The first full day after enabling collection is the reliable coverage boundary.
    complete_from = day(collected_from) + timedelta(days=1)
    points: list[dict[str, Any]] = []
    current = start
    while current <= through:
        point: dict[str, Any] = {"date": current.isoformat(), "complete": current >= complete_from}
        for metric, width in (("dau", 1), ("wau", 7), ("mau", 30)):
            first = current - timedelta(days=width - 1)
            last_by_user: dict[UUID, Activity] = {}
            for item in values:
                if first <= day(item.at) <= current:
                    last_by_user[item.user_id] = item
            known = observed_from is not None and current >= day(observed_from)
            counts = Counter(item.plan for item in last_by_user.values())
            point[metric] = {
                "total": len(last_by_user) if known else None,
                "plans": {plan: counts[plan] if known else None for plan in PLANS},
                "complete": first >= complete_from,
            }
        point["new_accounts"] = sum(day(at) == current for at in registrations)
        visible_attempts = [
            a for a in attempts if day(a.created_at) == current and a.created_at < cutoff
        ]
        closed = [
            a
            for a in visible_attempts
            if (a.verified_at is not None and a.verified_at < cutoff)
            or (a.removed_at is not None and a.removed_at < cutoff)
        ]
        passed = [a for a in closed if a.verified_at is not None and a.verified_at < cutoff]
        verified = [
            a for a in attempts if a.verified_at is not None and day(a.verified_at) == current
        ]
        durations = [
            (a.verified_at - a.created_at).total_seconds()
            for a in verified
            if a.verified_at is not None and a.verified_at >= a.created_at
        ]
        covered = attempts_from is not None and current >= day(attempts_from)
        point.update(
            verified_sessions=len(verified) if covered else None,
            connection_success_percent=round(100 * len(passed) / len(closed), 1)
            if closed
            else None,
            settled_attempts=len(closed) if covered else None,
            pending_attempts=len(visible_attempts) - len(closed) if covered else None,
            median_connection_seconds=round(median(durations), 1) if durations else None,
            engagement_percent=round(100 * point["dau"]["total"] / point["mau"]["total"], 1)
            if point["mau"]["total"]
            else None,
        )
        points.append(point)
        current += timedelta(days=1)
    methods = Counter(
        a.method
        for a in attempts
        if a.verified_at is not None and start <= day(a.verified_at) <= through
    )
    return {
        "schema": 1,
        "generated_at": now.isoformat(),
        "from_date": start.isoformat(),
        "through_date": through.isoformat(),
        "timezone": "GMT+3",
        "next_update_at": boundary(today + timedelta(days=1)).isoformat(),
        "observed_from": observed_from.isoformat() if observed_from else None,
        "full_collection_from": complete_from.isoformat(),
        "history_partial": start < complete_from,
        "attempts_from": attempts_from.isoformat() if attempts_from else None,
        "points": points,
        "methods": dict(sorted(methods.items())),
    }
