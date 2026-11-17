"""Build daily aggregates from durable first-party evidence; serve stored snapshots."""

from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from prettylisavpn.client_vpn.model import ClientLeaseRecord
from prettylisavpn.connections import Postgres
from prettylisavpn.demo.domain import is_demo_email
from prettylisavpn.devices.model import DeviceRecord
from prettylisavpn.fleet.domain import FleetError
from prettylisavpn.legacy_vpn.sessions import VpnSessionRecord
from prettylisavpn.product_analytics.activity import is_test_account
from prettylisavpn.product_analytics.domain import (
    METRICS_REVISION,
    Activity,
    Attempt,
    Plan,
    PlanFilter,
    Registration,
    boundary,
    day,
    plan_key,
    snapshot,
    two_months_before,
)
from prettylisavpn.product_analytics.durations import duration_history
from prettylisavpn.product_analytics.model import (
    ActivityRecord,
    AnalyticsCollectionRecord,
    AnalyticsSnapshotRecord,
    AppActivityRecord,
    SessionSilenceRecord,
)
from prettylisavpn.product_analytics.plans import lease_plan
from prettylisavpn.product_events.domain import ProductEventName
from prettylisavpn.product_events.model import ProductEventRecord
from prettylisavpn.users.model import UserRecord

ACTIVITY_EVENTS = (
    ProductEventName.LOGIN_SUCCEEDED,
    ProductEventName.TOKEN_REFRESHED,
    ProductEventName.LOGOUT,
)


class ProductAnalyticsService:
    def __init__(self, postgres: Postgres) -> None:
        self.postgres = postgres

    async def latest(
        self, now: datetime | None = None, *, plan: PlanFilter = None
    ) -> dict[str, Any]:
        now = now or datetime.now(UTC)
        async with self.postgres.session() as session, session.begin():
            await session.execute(
                text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            )
            row = await session.scalar(
                select(AnalyticsSnapshotRecord)
                .where(AnalyticsSnapshotRecord.through_date < day(now))
                .order_by(AnalyticsSnapshotRecord.through_date.desc())
                .limit(1)
            )
            if row is None:
                raise FleetError("product_analytics_pending", 503)
            current = await self.build(session, now, live=True, plan=plan)
            point = current["points"][0]
            live = {
                "partial": True,
                "updated_at": now.isoformat(),
                "point": point,
                "from_date": current["from_date"],
                "summary": {
                    key: current[key]
                    for key in (
                        "session_duration",
                        "time_to_silence",
                        "mean_session_seconds",
                        "duration_unobserved_sessions",
                        "silence_unobserved_sessions",
                    )
                },
            }
            return {
                **current.get("filtered_history", row.data),
                "plan": plan_key(plan),
                "duration_history": current["duration_history"],
                "live": live,
                # Keep the additive 0.45 contract for dashboards during rollout.
                "device_today": {
                    "date": point["date"],
                    "partial": True,
                    "updated_at": now.isoformat(),
                    "device_platforms": point["device_platforms"],
                },
            }

    async def refresh(self, now: datetime | None = None) -> bool:
        now = now or datetime.now(UTC)
        through = day(now) - timedelta(days=1)
        async with self.postgres.session() as session, session.begin():
            await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
            if not await session.scalar(text("SELECT pg_try_advisory_xact_lock(860120041)")):
                return False
            existing = await session.get(AnalyticsSnapshotRecord, through)
            if existing is not None and existing.data.get("metrics_revision") == METRICS_REVISION:
                return False
            payload = await self.build(session, now)
            if existing is not None:
                existing.generated_at, existing.data = now, payload
            else:
                session.add(
                    AnalyticsSnapshotRecord(through_date=through, generated_at=now, data=payload)
                )
            # 180 days exceeds two calendar months plus the MAU lookback.
            await session.execute(
                delete(ActivityRecord).where(ActivityRecord.day < day(now) - timedelta(days=180))
            )
            await session.execute(
                delete(AppActivityRecord).where(
                    AppActivityRecord.day < day(now) - timedelta(days=180)
                )
            )
            await session.execute(
                delete(AnalyticsSnapshotRecord).where(
                    AnalyticsSnapshotRecord.through_date < day(now) - timedelta(days=180)
                )
            )
            await session.execute(
                delete(SessionSilenceRecord).where(
                    SessionSilenceRecord.observed_until < now - timedelta(days=180)
                )
            )
            await session.execute(
                update(ClientLeaseRecord)
                .where(
                    ClientLeaseRecord.removed_at < now - timedelta(days=180),
                    ClientLeaseRecord.custom_rules.is_not(None),
                )
                .values(custom_rules=None)
            )
        return True

    async def build(
        self, session: AsyncSession, now: datetime, *, live: bool = False, plan: PlanFilter = None
    ) -> dict[str, Any]:
        lower = boundary(two_months_before(day(now)) - timedelta(days=29))
        cutoff = now + timedelta(microseconds=1) if live else boundary(day(now))
        collection = await session.get(AnalyticsCollectionRecord, 1)
        if collection is None:
            raise FleetError("product_analytics_not_initialized", 503)
        # Emails stay inside the database service, used only to exclude reserved test domains.
        users = (await session.scalars(select(UserRecord))).all()
        ids = {user.id for user in users if not is_test_account(user.email)}
        registrations = [
            Registration(user.id, user.created_at)
            for user in users
            if user.id in ids and not is_demo_email(user.email)
        ]
        demo_ids = {user.id for user in users if is_demo_email(user.email)}
        emails = {user.id: user.email for user in users}
        events = (
            await session.scalars(
                select(ProductEventRecord).where(
                    ProductEventRecord.user_id.in_(ids),
                    ProductEventRecord.event_name.in_(ACTIVITY_EVENTS),
                    ProductEventRecord.occurred_at >= lower,
                    ProductEventRecord.occurred_at < min(cutoff, collection.started_at),
                )
            )
        ).all()
        activity = [
            Activity(row.user_id, row.occurred_at, "DEMO" if row.user_id in demo_ids else "UNKNOWN")
            for row in events
            if row.user_id is not None
        ]
        daily = (
            await session.scalars(
                select(ActivityRecord).where(
                    ActivityRecord.user_id.in_(ids),
                    ActivityRecord.day >= day(lower),
                    ActivityRecord.observed_at < cutoff,
                )
            )
        ).all()
        activity.extend(
            Activity(row.user_id, row.observed_at, cast(Plan, row.plan)) for row in daily
        )
        legacy = (
            await session.scalars(
                select(VpnSessionRecord).where(
                    VpnSessionRecord.user_id.in_(ids),
                    VpnSessionRecord.created_at >= lower,
                    VpnSessionRecord.created_at < min(cutoff, collection.started_at),
                )
            )
        ).all()
        # A session request is authenticated activity; its old ACTIVE status is
        # not evidence of Internet verification. Only its creation-time plan is known.
        activity.extend(
            Activity(row.user_id, row.created_at, row.plan_snapshot.value) for row in legacy
        )
        leases = (
            await session.scalars(
                select(ClientLeaseRecord).where(
                    ClientLeaseRecord.user_id.in_(ids),
                    ClientLeaseRecord.created_at < cutoff,
                    (ClientLeaseRecord.created_at >= lower)
                    | (ClientLeaseRecord.heartbeat_at >= lower)
                    | (ClientLeaseRecord.disconnected_at >= lower),
                )
            )
        ).all()
        for lease in leases:
            if lease.user_id in demo_ids:
                # Guest activity was excluded before report revision 2. Recover
                # only actual durable observations, never the time between them.
                for at in (lease.created_at, lease.verified_at, lease.heartbeat_at):
                    if at is not None and at < min(
                        cutoff, lease.expires_at, lease.removed_at or cutoff
                    ):
                        activity.append(Activity(lease.user_id, at, "DEMO"))
                continue
            # Once collection starts, only the activity-time ledger owns cohorts.
            # Later UNKNOWN legacy evidence must not erase an observed plan.
            if lease.created_at < collection.started_at:
                activity.append(
                    Activity(
                        lease.user_id, lease.created_at, "FREE" if lease.is_free else "UNKNOWN"
                    )
                )
            if lease.verified_at is not None and lease.verified_at < cutoff:
                if lease.verified_at < collection.started_at:
                    activity.append(Activity(lease.user_id, lease.verified_at))
                # Evidence only at recorded heartbeat time, never stretch through delayed cleanup.
                end = lease.heartbeat_at
                if (
                    lease.verified_at
                    <= end
                    < min(
                        cutoff, collection.started_at, lease.expires_at, lease.removed_at or cutoff
                    )
                ):
                    activity.append(Activity(lease.user_id, end))
        devices = {
            row.id: row.platform.value
            for row in await session.scalars(
                select(DeviceRecord).where(DeviceRecord.user_id.in_(ids))
            )
        }
        silence = {
            row.lease_id: row
            for row in await session.scalars(
                select(SessionSilenceRecord).where(
                    SessionSilenceRecord.lease_id.in_([v.id for v in leases])
                )
            )
        }
        attempts = []
        for row in leases:
            quiet = silence.get(row.id)
            attempts.append(
                Attempt(
                    row.created_at,
                    row.verified_at,
                    row.removed_at,
                    row.method,
                    devices.get(row.device_id, "UNKNOWN"),
                    row.disconnected_at,
                    quiet.first_silence_at if quiet else None,
                    quiet.complete if quiet else False,
                    user_id=row.user_id,
                    plan=lease_plan(row, emails[row.user_id]),
                )
            )
        observed = await session.scalar(
            select(func.min(ProductEventRecord.occurred_at)).where(
                ProductEventRecord.event_name.in_(ACTIVITY_EVENTS)
            )
        )
        attempts_from = await session.scalar(select(func.min(ClientLeaseRecord.created_at)))
        observed_from = min(observed, collection.started_at) if observed else collection.started_at
        payload = snapshot(
            now,
            activity,
            registrations,
            attempts,
            observed_from,
            collection.started_at,
            attempts_from,
            live=live,
            plan=plan,
        )
        if live:
            first = await session.scalar(
                select(func.min(ClientLeaseRecord.created_at)).where(
                    ClientLeaseRecord.user_id.in_(ids), ClientLeaseRecord.created_at < cutoff
                )
            )
            payload["duration_history"] = duration_history(
                now,
                attempts,
                min(first, collection.started_at) if first else collection.started_at,
                plan,
            )
            if plan is not None:
                # Filter evidence, never the already aggregated ALL snapshot. Reuse
                # this transaction's data; reads do not publish or rewrite history.
                payload["filtered_history"] = snapshot(
                    now,
                    activity,
                    registrations,
                    attempts,
                    observed_from,
                    collection.started_at,
                    attempts_from,
                    plan=plan,
                )
        return payload
