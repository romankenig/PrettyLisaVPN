"""Daily session overlap, using durable lifecycle evidence without browsing data."""

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal

from sqlalchemy import func, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from prettylisavpn.client_vpn.methods import METHODS
from prettylisavpn.client_vpn.model import ClientLeaseRecord
from prettylisavpn.product_analytics.activity import is_test_account
from prettylisavpn.product_analytics.domain import PlanFilter, boundary, day, selected_plans
from prettylisavpn.product_analytics.plans import lease_plan_expression
from prettylisavpn.traffic.model import TrafficServiceRecord
from prettylisavpn.users.model import UserRecord

Kind = Literal["methods", "services"]
Outcome = Literal["successful", "unsuccessful", "all"]
OUTCOMES: tuple[Outcome, ...] = ("successful", "unsuccessful", "all")


def connection_outcome(row: ClientLeaseRecord, now: datetime) -> Outcome | None:
    """A transient node error is pending; once verified, later cleanup is not failure."""
    if row.created_at > now:
        return None
    if row.verified_at is not None:
        return "successful" if row.created_at <= row.verified_at <= now else None
    terminal = row.status in ("REVOKING", "CLOSED") or any(
        at is not None and row.created_at <= at <= now
        for at in (row.disconnected_at, row.removed_at, row.expires_at)
    )
    return "unsuccessful" if terminal else None


@dataclass(frozen=True)
class SessionInterval:
    # Verification for successful sessions; creation for unsuccessful attempts.
    started_at: datetime
    expires_at: datetime
    ended_at: datetime | None
    method: str
    traffic_mode: str | None
    service_ids: tuple[str, ...] | None
    custom_rules: bool | None
    outcome: Outcome = "successful"


def selection_history(
    now: datetime,
    sessions: list[SessionInterval],
    observed_from: datetime | None,
    kind: Kind,
    services: dict[str, tuple[str, str]],
    outcome: Outcome = "successful",
) -> dict[str, Any]:
    today = day(now)
    dates = [today - timedelta(days=offset) for offset in range(7, -1, -1)]
    points = []
    categories: set[str] = set()
    for on in dates:
        start = boundary(on)
        until = min(boundary(on + timedelta(days=1)), now + timedelta(microseconds=1))
        active: list[SessionInterval] = []
        uncertain = 0
        for row in sessions:
            if outcome != "all" and row.outcome != outcome:
                continue
            if row.started_at >= until or row.expires_at <= row.started_at:
                continue
            end = min(row.expires_at, row.ended_at or row.expires_at)
            if end < row.started_at:
                continue
            # An instantaneous confirmed session still belongs to its verification day.
            end = max(end, row.started_at + timedelta(microseconds=1))
            if end <= start:
                continue
            if row.ended_at is None and row.started_at < start:
                # A terminal legacy row without an end cannot prove later open days.
                if kind == "methods" or row.traffic_mode in (None, "include"):
                    uncertain += 1
            else:
                active.append(row)
        covered = on == today or (observed_from is not None and on >= day(observed_from))
        counts: Counter[str] = Counter()
        selected = observed = unknown_mode = 0
        for row in active:
            if kind == "methods":
                selected += 1
                observed += 1
                counts[row.method if row.method in METHODS else "UNKNOWN"] += 1
            else:
                if row.traffic_mode is None:
                    unknown_mode += 1
                if row.traffic_mode != "include":
                    continue
                selected += 1
                if row.service_ids is None or row.custom_rules is None:
                    continue
                observed += 1
                choices = {
                    services[value][0] if value in services else "UNKNOWN"
                    for value in row.service_ids
                }
                if row.custom_rules:
                    choices.add("UNKNOWN")
                counts.update(choices)
        known = covered and (observed > 0 or (not selected and not unknown_mode and not uncertain))
        categories.update(counts)
        points.append(
            {
                "date": on.isoformat(),
                "partial": on == today,
                "counts": dict(sorted(counts.items())) if known else None,
                "total": sum(counts.values()) if known else None,
                "active_sessions": selected,
                "observed_sessions": observed,
                "unknown_mode_sessions": unknown_mode,
                "uncertain_sessions": uncertain,
                "complete": covered and observed == selected and not unknown_mode and not uncertain,
            }
        )
    names = {slug: name for slug, name in services.values()}
    return {
        "timezone": "GMT+3",
        "generated_at": now.isoformat(),
        "from_date": dates[0].isoformat(),
        "through_date": today.isoformat(),
        "observed_from": observed_from.isoformat() if observed_from else None,
        "categories": [{"id": key, "name": names.get(key, key)} for key in sorted(categories)],
        "points": points,
    }


async def load_selection_history(
    session: AsyncSession, now: datetime, kind: Kind, plan: PlanFilter = None
) -> dict[str, Any]:
    start = boundary(day(now) - timedelta(days=7))
    ids = [
        user_id
        for user_id, email in await session.execute(select(UserRecord.id, UserRecord.email))
        if not is_test_account(email)
    ]
    first = select(
        func.min(ClientLeaseRecord.verified_at).filter(ClientLeaseRecord.verified_at <= now),
        func.min(ClientLeaseRecord.created_at),
    ).where(
        ClientLeaseRecord.user_id.in_(ids),
        ClientLeaseRecord.created_at <= now,
    )
    if kind == "services":
        first = first.where(
            ClientLeaseRecord.traffic_mode.is_not(None),
            func.jsonb_typeof(ClientLeaseRecord.service_ids) == "array",
            func.jsonb_typeof(ClientLeaseRecord.custom_rules) == "array",
        )
    verified_from, attempts_from = (await session.execute(first)).one()
    catalog = (
        {
            str(row.id): (row.slug, row.name)
            for row in await session.scalars(select(TrafficServiceRecord))
        }
        if kind == "services"
        else {}
    )
    intervals = []
    for row in await session.scalars(
        select(ClientLeaseRecord)
        .join(UserRecord, UserRecord.id == ClientLeaseRecord.user_id)
        .where(
            ClientLeaseRecord.user_id.in_(ids),
            true() if plan is None else lease_plan_expression().in_(selected_plans(plan)),
            ClientLeaseRecord.created_at <= now,
            (
                (ClientLeaseRecord.verified_at <= now)
                & (ClientLeaseRecord.expires_at >= start)
                & (
                    ClientLeaseRecord.disconnected_at.is_(None)
                    | (ClientLeaseRecord.disconnected_at >= start)
                )
                & (ClientLeaseRecord.removed_at.is_(None) | (ClientLeaseRecord.removed_at >= start))
            )
            | (ClientLeaseRecord.verified_at.is_(None) & (ClientLeaseRecord.created_at >= start)),
        )
    ):
        outcome = connection_outcome(row, now)
        if outcome is None:
            continue
        if outcome == "unsuccessful":
            # Provisioning/READY without Internet confirmation is still pending.
            # A recorded stop, removal or expiry settles it without success. A
            # transient worker error alone must never turn a retry into failure.
            started = row.created_at
            expires = started + timedelta(microseconds=1)
            ended: datetime | None = started
        else:
            assert row.verified_at is not None
            started, expires = row.verified_at, row.expires_at
            ends = [at for at in (row.disconnected_at, row.removed_at) if at is not None]
            if row.status == "READY":
                ends.append(row.expires_at)
            ended = min(ends) if ends else None
        intervals.append(
            SessionInterval(
                started,
                expires,
                ended,
                row.method,
                row.traffic_mode,
                tuple(row.service_ids) if row.service_ids is not None else None,
                bool(row.custom_rules) if row.custom_rules is not None else None,
                outcome,
            )
        )
    outcomes = {
        outcome: selection_history(
            now,
            intervals,
            verified_from if outcome == "successful" else attempts_from,
            kind,
            catalog,
            outcome,
        )
        for outcome in OUTCOMES
    }
    # Shared categories keep colors fixed when changing outcome. The legacy
    # selection_history contract still contains only successful sessions.
    for history in outcomes.values():
        history["categories"] = outcomes["all"]["categories"]
    return {**outcomes["successful"], "outcomes": outcomes}
