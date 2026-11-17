"""Daily start cohorts from existing duration evidence, including late completions."""

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

from prettylisavpn.product_analytics.domain import (
    Attempt,
    Plan,
    day,
    distribution,
    duration,
    silence_duration,
    two_months_before,
)


def duration_history(
    now: datetime, attempts: list[Attempt], observed_from: datetime, plan: Plan | None = None
) -> dict[str, Any]:
    today = day(now)
    start = two_months_before(today)
    cutoff = now + timedelta(microseconds=1)
    cohorts: dict[date, list[Attempt]] = defaultdict(list)
    for attempt in attempts:
        if (
            attempt.verified_at is not None
            and attempt.created_at <= attempt.verified_at < cutoff
            and (plan is None or attempt.plan == plan)
        ):
            cohorts[day(attempt.verified_at)].append(attempt)
    points = []
    current = start
    while current <= today:
        known = current >= day(observed_from)
        cohort = cohorts[current]
        lengths = [v for a in cohort if (v := duration(a, cutoff)) is not None]
        quiet = [v for a in cohort if (v := silence_duration(a, cutoff)) is not None]
        points.append(
            {
                "date": current.isoformat(),
                "partial": current == today,
                "sessions": len(cohort) if known else None,
                "session_duration": distribution(lengths) if known else None,
                "time_to_silence": distribution(quiet) if known else None,
                "duration_unobserved_sessions": len(cohort) - len(lengths) if known else None,
                "silence_unobserved_sessions": len(cohort) - len(quiet) if known else None,
            }
        )
        current += timedelta(days=1)
    return {
        "timezone": "GMT+3",
        "generated_at": now.isoformat(),
        "plan": plan or "ALL",
        "from_date": start.isoformat(),
        "through_date": today.isoformat(),
        "observed_from": observed_from.isoformat(),
        "points": points,
    }
