"""Calendar windows and activity-time cohorts, independent of storage and HTTP."""

import calendar
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, timezone
from statistics import mean, median
from typing import Any, Literal
from uuid import UUID

MOSCOW = timezone(timedelta(hours=3))
Plan = Literal["DEMO", "FREE", "PREMIUM", "PLATINUM", "UNKNOWN"]
PLANS: tuple[Plan, ...] = ("DEMO", "FREE", "PREMIUM", "PLATINUM", "UNKNOWN")
PlanFilter = Plan | tuple[Plan, ...] | None
DURATION_BOUNDS = (10, 60, 180, 300, 900)
METRICS_REVISION = 3


def selected_plans(plan: PlanFilter) -> tuple[Plan, ...]:
    return PLANS if plan is None else (plan,) if isinstance(plan, str) else plan


def matches_plan(value: str, plan: PlanFilter) -> bool:
    return plan is None or value in selected_plans(plan)


def plan_key(plan: PlanFilter) -> str:
    selected = selected_plans(plan)
    ordered = tuple(value for value in PLANS if value in selected)
    return "ALL" if ordered == PLANS else ",".join(ordered) or "NONE"


def parse_plan_filter(value: str | None) -> PlanFilter:
    """One canonical union; an explicit empty set must never mean all tariffs."""
    if value is None:
        return None
    if value == "NONE":
        return ()
    values = value.split(",")
    if len(value) > 100 or any(item not in PLANS for item in values):
        raise ValueError("Invalid report tariffs")
    selected = tuple(item for item in PLANS if item in values)
    if selected == PLANS:
        return None
    return selected[0] if len(selected) == 1 else selected


def distribution(values: list[float]) -> dict[str, Any]:
    counts = [0] * 6
    for value in values:
        counts[next((i for i, bound in enumerate(DURATION_BOUNDS) if value <= bound), 5)] += 1
    return {
        "bounds_seconds": list(DURATION_BOUNDS),
        "counts": counts,
        "shares": [100 * value / len(values) if values else None for value in counts],
        "samples": len(values),
    }


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
    platform: str = "UNKNOWN"
    disconnected_at: datetime | None = None
    first_silence_at: datetime | None = None
    silence_complete: bool = False
    user_id: UUID | None = None
    plan: Plan = "UNKNOWN"


@dataclass(frozen=True)
class Registration:
    user_id: UUID
    at: datetime


def device_platforms(attempts: list[Attempt], covered: bool) -> dict[str, Any]:
    """One connection per verified lease; one account per platform and day."""
    if not covered:
        return {"connections": None, "users": None}
    connections = Counter(a.platform for a in attempts)
    users = Counter(platform for platform, _ in {(a.platform, a.user_id) for a in attempts})
    return {
        "connections": dict(sorted(connections.items())),
        "users": None if any(a.user_id is None for a in attempts) else dict(sorted(users.items())),
    }


def duration(a: Attempt, cutoff: datetime) -> float | None:
    if (
        a.verified_at is not None
        and a.disconnected_at is not None
        and (a.verified_at <= a.disconnected_at < cutoff)
    ):
        return (a.disconnected_at - a.verified_at).total_seconds()
    return None


def silence_duration(a: Attempt, cutoff: datetime) -> float | None:
    if (
        a.silence_complete
        and a.verified_at is not None
        and a.first_silence_at is not None
        and (
            a.verified_at <= a.first_silence_at
            and a.first_silence_at + timedelta(seconds=10) < cutoff
        )
    ):
        return (a.first_silence_at - a.verified_at).total_seconds()
    return None


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
    registrations: list[datetime] | list[Registration],
    attempts: list[Attempt],
    observed_from: datetime | None,
    collected_from: datetime,
    attempts_from: datetime | None,
    *,
    live: bool = False,
    plan: PlanFilter = None,
) -> dict[str, Any]:
    """Saved history, or just today's point and the period totals as of now."""
    today = day(now)
    start = two_months_before(today)
    through = today if live else today - timedelta(days=1)
    cutoff = now + timedelta(microseconds=1) if live else boundary(today)
    values = sorted(
        latest_activity([item for item in activity if item.at < cutoff]), key=lambda a: a.at
    )
    daily_plans = {(a.user_id, day(a.at)): a.plan for a in values}
    attempts = [a for a in attempts if matches_plan(a.plan, plan)]
    # The first full day after enabling collection is the reliable coverage boundary.
    complete_from = day(collected_from) + timedelta(days=1)
    points: list[dict[str, Any]] = []
    current = today if live else start
    while current <= through:
        point: dict[str, Any] = {"date": current.isoformat(), "complete": current >= complete_from}
        for metric, width in (("dau", 1), ("wau", 7), ("mau", 30)):
            first = current - timedelta(days=width - 1)
            last_by_user: dict[UUID, Activity] = {}
            for item in values:
                if first <= day(item.at) <= current:
                    last_by_user[item.user_id] = item
            if plan is not None:
                last_by_user = {
                    key: item for key, item in last_by_user.items() if matches_plan(item.plan, plan)
                }
            known = observed_from is not None and current >= day(observed_from)
            counts = Counter(item.plan for item in last_by_user.values())
            point[metric] = {
                "total": len(last_by_user) if known else None,
                "plans": {plan: counts[plan] if known else None for plan in PLANS},
                "complete": first >= complete_from,
            }
        point["new_accounts"] = sum(
            day(at := row.at if isinstance(row, Registration) else row) == current
            and at < cutoff
            and (
                matches_plan(
                    daily_plans.get((row.user_id, day(at)), "UNKNOWN")
                    if isinstance(row, Registration)
                    else "UNKNOWN",
                    plan,
                )
            )
            for row in registrations
        )
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
            a
            for a in attempts
            if a.verified_at is not None
            and a.verified_at < cutoff
            and day(a.verified_at) == current
        ]
        durations = [
            (a.verified_at - a.created_at).total_seconds()
            for a in verified
            if a.verified_at is not None and a.verified_at >= a.created_at
        ]
        covered = live or (attempts_from is not None and current >= day(attempts_from))
        closed_seconds = [
            seconds
            for a in attempts
            if a.disconnected_at is not None
            and day(a.disconnected_at) == current
            and (seconds := duration(a, cutoff)) is not None
        ]
        point.update(
            device_platforms=device_platforms(verified, covered),
            mean_session_seconds=round(mean(closed_seconds), 1) if closed_seconds else None,
            completed_sessions=len(closed_seconds),
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
        if a.verified_at is not None
        and a.verified_at < cutoff
        and start <= day(a.verified_at) <= through
    )
    cohort = [
        a
        for a in attempts
        if a.verified_at is not None
        and a.verified_at < cutoff
        and start <= day(a.verified_at) <= through
    ]
    session_lengths = [seconds for a in cohort if (seconds := duration(a, cutoff)) is not None]
    quiet = [seconds for a in cohort if (seconds := silence_duration(a, cutoff)) is not None]
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
        "devices": dict(sorted(Counter(a.platform for a in cohort).items())),
        "session_duration": distribution(session_lengths),
        "time_to_silence": distribution(quiet),
        "mean_session_seconds": round(mean(session_lengths), 1) if session_lengths else None,
        "duration_unobserved_sessions": len(cohort) - len(session_lengths),
        "silence_unobserved_sessions": len(cohort) - len(quiet),
        "metrics_revision": METRICS_REVISION,
    }
