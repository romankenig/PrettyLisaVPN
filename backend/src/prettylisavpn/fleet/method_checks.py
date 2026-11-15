"""Route selection and aggregate reports for fixed connection methods."""

import secrets
from collections import Counter
from datetime import UTC, datetime, timedelta
from statistics import mean
from typing import Any
from uuid import UUID

from sqlalchemy import select

from prettylisavpn.client_vpn.methods import METHODS
from prettylisavpn.client_vpn.model import ClientLeaseRecord
from prettylisavpn.connections import Postgres
from prettylisavpn.fleet.method_check_model import MethodCheckRecord
from prettylisavpn.fleet.service_checks import daily_slot
from prettylisavpn.product_analytics.activity import is_test_account
from prettylisavpn.product_analytics.domain import day
from prettylisavpn.users.model import UserRecord

Route = tuple[UUID, UUID | None]


def choose_route(roster: list[Route], attempts: list[dict[str, Any]]) -> Route | None:
    used = {(a["node"], a.get("relay")) for a in attempts}
    remaining = [r for r in roster if (str(r[0]), str(r[1]) if r[1] else None) not in used]
    if not remaining:
        return None
    if attempts:
        remaining = [r for r in remaining if str(r[0]) != attempts[-1]["node"]] or remaining
    return secrets.choice(remaining)


class MethodAnalytics:
    def __init__(self, postgres: Postgres):
        self.postgres = postgres

    async def report(self, now: datetime | None = None) -> dict[str, Any]:
        now = now or datetime.now(UTC)
        today = day(now)
        dates = [today - timedelta(days=offset) for offset in range(7, 0, -1)]
        async with self.postgres.session() as session:
            checks = {
                (r.method, r.day): r
                for r in await session.scalars(
                    select(MethodCheckRecord).where(MethodCheckRecord.day >= dates[0])
                )
            }
            counts: Counter[str] = Counter()
            for method, email in await session.execute(
                select(ClientLeaseRecord.method, UserRecord.email)
                .join(UserRecord, UserRecord.id == ClientLeaseRecord.user_id)
                .where(
                    ClientLeaseRecord.status == "READY",
                    ClientLeaseRecord.removed_at.is_(None),
                    ClientLeaseRecord.verified_at.is_not(None),
                    ClientLeaseRecord.expires_at > now,
                )
            ):
                if not is_test_account(email):
                    counts[method if method in METHODS else "UNKNOWN"] += 1
            items = []
            for method in sorted(METHODS):
                points: list[dict[str, Any]] = [
                    {
                        "date": on.isoformat(),
                        "score": checks[(method, on)].score if (method, on) in checks else None,
                    }
                    for on in dates
                ]
                values = [p["score"] for p in points if p["score"] is not None]
                current = checks.get((method, today))
                items.append(
                    {
                        "id": method,
                        "points": points,
                        "week_score": round(mean(values), 1) if values else None,
                        "observed_days": len(values),
                        "today_score": current.score if current else None,
                        "today_code": current.code if current else "PENDING",
                        "next_check_at": (
                            current.next_attempt_at
                            if current and not current.finished_at
                            else daily_slot("method:" + method, today + timedelta(days=1))
                        ).isoformat(),
                    }
                )
            total = sum(counts.values())
            return {
                "generated_at": now.isoformat(),
                "timezone": "GMT+3",
                "methods": items,
                "selection": {
                    "active_sessions": total,
                    "items": [
                        {"method": method, "count": count, "share": 100 * count / total}
                        for method, count in counts.most_common()
                    ],
                },
            }
