"""Build daily aggregates from durable first-party evidence; serve stored snapshots."""

from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from prettylisavpn.client_vpn.model import ClientLeaseRecord
from prettylisavpn.connections import Postgres
from prettylisavpn.fleet.domain import FleetError
from prettylisavpn.legacy_vpn.sessions import VpnSessionRecord
from prettylisavpn.product_analytics.activity import is_test_account
from prettylisavpn.product_analytics.domain import (
    Activity,
    Attempt,
    Plan,
    boundary,
    day,
    snapshot,
    two_months_before,
)
from prettylisavpn.product_analytics.model import (
    ActivityRecord,
    AnalyticsCollectionRecord,
    AnalyticsSnapshotRecord,
)
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

    async def latest(self) -> dict[str, Any]:
        async with self.postgres.session() as session:
            row = await session.scalar(
                select(AnalyticsSnapshotRecord)
                .order_by(AnalyticsSnapshotRecord.through_date.desc())
                .limit(1)
            )
            if row is None:
                raise FleetError("product_analytics_pending", 503)
            return row.data

    async def refresh(self, now: datetime | None = None) -> bool:
        now = now or datetime.now(UTC)
        through = day(now) - timedelta(days=1)
        async with self.postgres.session() as session, session.begin():
            await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
            if not await session.scalar(text("SELECT pg_try_advisory_xact_lock(860120041)")):
                return False
            if await session.get(AnalyticsSnapshotRecord, through) is not None:
                return False
            payload = await self.build(session, now)
            session.add(
                AnalyticsSnapshotRecord(through_date=through, generated_at=now, data=payload)
            )
            # 180 days exceeds two calendar months plus the MAU lookback.
            await session.execute(
                delete(ActivityRecord).where(ActivityRecord.day < day(now) - timedelta(days=180))
            )
            await session.execute(
                delete(AnalyticsSnapshotRecord).where(
                    AnalyticsSnapshotRecord.through_date < day(now) - timedelta(days=180)
                )
            )
        return True

    async def build(self, session: AsyncSession, now: datetime) -> dict[str, Any]:
        lower = boundary(two_months_before(day(now)) - timedelta(days=29))
        cutoff = boundary(day(now))
        collection = await session.get(AnalyticsCollectionRecord, 1)
        if collection is None:
            raise FleetError("product_analytics_not_initialized", 503)
        # Emails stay inside the database service, used only to exclude reserved test domains.
        users = (await session.scalars(select(UserRecord))).all()
        ids = {user.id for user in users if not is_test_account(user.email)}
        registrations = [user.created_at for user in users if user.id in ids]
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
            Activity(row.user_id, row.occurred_at) for row in events if row.user_id is not None
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
                    | (ClientLeaseRecord.heartbeat_at >= lower),
                )
            )
        ).all()
        for lease in leases:
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
                end = min(lease.heartbeat_at, lease.expires_at, lease.removed_at or cutoff)
                if lease.verified_at <= end < min(cutoff, collection.started_at):
                    activity.append(Activity(lease.user_id, end))
        attempts = [
            Attempt(row.created_at, row.verified_at, row.removed_at, row.method) for row in leases
        ]
        observed = await session.scalar(
            select(func.min(ProductEventRecord.occurred_at)).where(
                ProductEventRecord.event_name.in_(ACTIVITY_EVENTS)
            )
        )
        attempts_from = await session.scalar(select(func.min(ClientLeaseRecord.created_at)))
        observed_from = min(observed, collection.started_at) if observed else collection.started_at
        return snapshot(
            now,
            activity,
            registrations,
            attempts,
            observed_from,
            collection.started_at,
            attempts_from,
        )
