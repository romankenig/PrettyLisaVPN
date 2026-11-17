"""Daily assessments and private aggregate projections, independent of dashboard refresh."""

import secrets
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from statistics import mean
from typing import Any
from uuid import UUID

from sqlalchemy import select, true

from prettylisavpn.client_vpn.model import ClientLeaseRecord
from prettylisavpn.connections import Postgres
from prettylisavpn.fleet.selection_history import load_selection_history
from prettylisavpn.fleet.service_check_model import ServiceCheckRecord
from prettylisavpn.product_analytics.activity import is_test_account
from prettylisavpn.product_analytics.domain import (
    PlanFilter,
    boundary,
    day,
    plan_key,
    selected_plans,
)
from prettylisavpn.product_analytics.plans import lease_plan_expression
from prettylisavpn.traffic.model import TrafficServiceRecord
from prettylisavpn.users.model import UserRecord

Candidate = tuple[UUID, str]


def choose_candidate(roster: list[Candidate], attempts: list[dict[str, Any]]) -> Candidate | None:
    used = {(row["node"], row["method"]) for row in attempts}
    remaining = [item for item in roster if (str(item[0]), item[1]) not in used]
    if not remaining:
        return None
    if attempts:
        previous = attempts[-1]
        different = [
            item
            for item in remaining
            if str(item[0]) != previous["node"] and item[1] != previous["method"]
        ]
        # If a fleet only has one node/type, still exhaust its unique combinations.
        remaining = different or remaining
    return secrets.choice(remaining)


def assessment_score(started: datetime, attempt_at: datetime, success: bool) -> float:
    return (
        round(max(0, 100 * (1 - (attempt_at - started).total_seconds() / 1800)), 1)
        if success
        else 0
    )


def daily_slot(service_id: UUID | str, on: date) -> datetime:
    import hashlib

    value = int.from_bytes(hashlib.sha256(f"{service_id}:{on}".encode()).digest()[:8])
    return boundary(on) + timedelta(seconds=value % (23 * 3600))


class ServiceAnalytics:
    def __init__(self, postgres: Postgres):
        self.postgres = postgres

    async def report(
        self, now: datetime | None = None, *, plan: PlanFilter = None
    ) -> dict[str, Any]:
        now = now or datetime.now(UTC)
        today = day(now)
        dates = [today - timedelta(days=offset) for offset in range(7, 0, -1)]
        async with self.postgres.session() as session:
            services = (
                await session.scalars(
                    select(TrafficServiceRecord)
                    .where(TrafficServiceRecord.enabled)
                    .order_by(TrafficServiceRecord.name)
                )
            ).all()
            checks = {
                (row.service_id, row.day): row
                for row in await session.scalars(
                    select(ServiceCheckRecord).where(ServiceCheckRecord.day >= dates[0])
                )
            }
            counts: Counter[str] = Counter()
            ids = {str(row.id): row.slug for row in services}
            leases = (
                await session.execute(
                    select(ClientLeaseRecord, UserRecord.email)
                    .join(UserRecord, UserRecord.id == ClientLeaseRecord.user_id)
                    .where(
                        true()
                        if plan is None
                        else lease_plan_expression().in_(selected_plans(plan)),
                        ClientLeaseRecord.status == "READY",
                        ClientLeaseRecord.removed_at.is_(None),
                        ClientLeaseRecord.verified_at.is_not(None),
                        ClientLeaseRecord.expires_at > now,
                    )
                )
            ).all()
            selected_sessions, observed_sessions, unknown_mode = 0, 0, 0
            for lease, email in leases:
                if is_test_account(email):
                    continue
                if lease.traffic_mode is None:
                    unknown_mode += 1
                if lease.traffic_mode != "include":
                    continue
                selected_sessions += 1
                if lease.service_ids is None or lease.custom_rules is None:
                    continue
                observed_sessions += 1
                selections = {ids.get(value, "UNKNOWN") for value in lease.service_ids}
                if lease.custom_rules:
                    selections.add("UNKNOWN")
                counts.update(selections)
            total = sum(counts.values())
            result = []
            for service in services:
                points: list[dict[str, Any]] = []
                for on in dates:
                    row = checks.get((service.id, on))
                    points.append(
                        {
                            "date": on.isoformat(),
                            "score": row.score if row else None,
                            "code": row.code if row else "NOT_OBSERVED",
                        }
                    )
                values = [point["score"] for point in points if point["score"] is not None]
                current = checks.get((service.id, today))
                result.append(
                    {
                        "id": str(service.id),
                        "slug": service.slug,
                        "name": service.name,
                        "points": points,
                        "week_score": round(mean(values), 1) if values else None,
                        "observed_days": len(values),
                        "today_score": current.score if current else None,
                        "today_code": current.code if current else "PENDING",
                        "next_check_at": (
                            current.next_attempt_at
                            if current and not current.finished_at
                            else daily_slot(service.id, today + timedelta(days=1))
                        ).isoformat(),
                    }
                )
            names = {row.slug: row.name for row in services}
            return {
                "generated_at": now.isoformat(),
                "timezone": "GMT+3",
                "plan": plan_key(plan),
                "services": result,
                "selection_history": await load_selection_history(session, now, "services", plan),
                "selection": {
                    "active_sessions": selected_sessions,
                    "observed_sessions": observed_sessions,
                    "unknown_mode_sessions": unknown_mode,
                    "total_selections": total,
                    "items": [
                        {
                            "service": name,
                            "name": names.get(name, "UNKNOWN"),
                            "count": count,
                            "share": 100 * count / total,
                        }
                        for name, count in counts.most_common()
                    ],
                },
            }
