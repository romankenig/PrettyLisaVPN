"""Persisted attribution and filtered report projections against disposable PostgreSQL."""

import os
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select, update
from test_active_user_speed import BASE, sample
from test_app_versions_integration import version_state  # noqa: F401
from test_client_vpn_integration import connect, vpn_state  # noqa: F401
from test_fleet import settings
from test_fleet_integration import fleet_state  # noqa: F401

from prettylisavpn.client_vpn.model import ClientLeaseRecord
from prettylisavpn.fleet.method_checks import MethodAnalytics
from prettylisavpn.fleet.service_checks import ServiceAnalytics
from prettylisavpn.fleet.traffic_model import TrafficIntervalRecord
from prettylisavpn.fleet.traffic_service import TrafficService
from prettylisavpn.product_analytics.app_versions import AppVersionAnalytics
from prettylisavpn.product_analytics.domain import boundary, day
from prettylisavpn.product_analytics.model import (
    AnalyticsCollectionRecord,
    AnalyticsSnapshotRecord,
    AppActivityRecord,
)
from prettylisavpn.product_analytics.service import ProductAnalyticsService
from prettylisavpn.subscriptions.domain import SubscriptionPlan
from prettylisavpn.subscriptions.model import SubscriptionRecord
from prettylisavpn.users.model import UserRecord

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1", reason="Needs disposable PostgreSQL"
    ),
]


async def test_lease_plan_is_immutable_and_all_usage_outcomes_are_filtered(vpn_state):  # noqa: F811
    pg, service, worker, _, identity = vpn_state
    identifier = UUID((await connect(service))["id"])
    await worker.tick()
    now = datetime(2099, 11, 17, 12, tzinfo=UTC)
    start = boundary(day(now)) - timedelta(days=1)
    async with pg.session() as session, session.begin():
        await session.execute(
            update(UserRecord)
            .where(UserRecord.id == identity.user_id)
            .values(email=f"plan-{uuid4()}@gmail.com")
        )
        row = await session.get(ClientLeaseRecord, identifier)
        assert row.plan_snapshot == "FREE"
        row.created_at = row.verified_at = start
        row.disconnected_at = now + timedelta(minutes=1)
        row.expires_at = now + timedelta(hours=1)
        row.status, row.heartbeat_at, row.traffic_mode = "READY", now, "include"
        row.service_ids, row.custom_rules = [], ["*.custom.invalid"]
        await session.flush()
        fields = {c.key: getattr(row, c.key) for c in ClientLeaseRecord.__table__.columns}
        failed = ClientLeaseRecord(
            **{
                **fields,
                "id": uuid4(),
                "request_id": uuid4(),
                "plan_snapshot": "PREMIUM",
                "is_free": False,
                "status": "CLOSED",
                "verified_at": None,
                "removed_at": start + timedelta(seconds=10),
                "disconnected_at": None,
            }
        )
        session.add(failed)
        await session.execute(
            update(SubscriptionRecord)
            .where(SubscriptionRecord.user_id == identity.user_id)
            .values(
                plan=SubscriptionPlan.PLATINUM,
                current_period_start=start,
                current_period_end=now + timedelta(days=5),
            )
        )
    for reader in (MethodAnalytics(pg), ServiceAnalytics(pg)):
        all_data = await reader.report(now)
        free = await reader.report(now, plan="FREE")
        paid = await reader.report(now, plan="PREMIUM")
        platinum = await reader.report(now, plan="PLATINUM")
        synthetic = "methods" if isinstance(reader, MethodAnalytics) else "services"
        assert all_data[synthetic] == free[synthetic] == paid[synthetic]
        assert free["selection_history"]["outcomes"]["successful"]["points"][-1]["total"] == 1
        assert paid["selection_history"]["outcomes"]["unsuccessful"]["points"][-2]["total"] == 1
        assert paid["selection_history"]["points"][-1]["total"] == 0
        assert platinum["selection_history"]["outcomes"]["all"]["points"][-1]["total"] == 0
        assert free["selection"]["active_sessions"] == 1
        assert paid["selection"]["active_sessions"] == 0
    analytics = ProductAnalyticsService(pg)
    async with pg.session() as session, session.begin():
        collection = await session.get(AnalyticsCollectionRecord, 1)
        old_start = collection.started_at
        collection.started_at = start
    try:
        await analytics.refresh(now)
        before = await analytics.latest(now, plan="FREE")
        async with pg.session() as session, session.begin():
            saved = (await session.get(AnalyticsSnapshotRecord, day(now) - timedelta(days=1))).data
            await session.execute(
                update(ClientLeaseRecord)
                .where(ClientLeaseRecord.id == identifier)
                .values(disconnected_at=now)
            )
        after = await analytics.latest(now, plan="FREE")
        assert before["duration_history"]["points"][-2]["session_duration"]["samples"] == 0
        assert after["duration_history"]["points"][-2]["session_duration"]["samples"] == 1
        assert after["duration_history"]["points"][-1]["sessions"] == 0
        assert after["points"][-1]["device_platforms"]["connections"] == {"WINDOWS": 1}
        async with pg.session() as session:
            assert (
                await session.get(AnalyticsSnapshotRecord, day(now) - timedelta(days=1))
            ).data == saved
            assert (await session.get(ClientLeaseRecord, identifier)).plan_snapshot == "FREE"
    finally:
        async with pg.session() as session, session.begin():
            await session.execute(
                update(AnalyticsCollectionRecord)
                .where(AnalyticsCollectionRecord.id == 1)
                .values(started_at=old_start)
            )
            await session.execute(
                delete(AnalyticsSnapshotRecord).where(
                    AnalyticsSnapshotRecord.through_date == day(now) - timedelta(days=1)
                )
            )


async def test_version_plan_follows_newest_activity_and_not_current_subscription(version_state):  # noqa: F811
    pg, _, own, _ = version_state
    service = AppVersionAnalytics(pg)
    now = datetime(2097, 10, 16, 12, tzinfo=UTC)
    device = own.devices[0].id
    await service.record(own.user.id, device, "1.0.0", now=now)
    async with pg.session() as session, session.begin():
        await session.execute(
            update(SubscriptionRecord)
            .where(SubscriptionRecord.user_id == own.user.id)
            .values(
                plan=SubscriptionPlan.PREMIUM,
                current_period_start=now,
                current_period_end=now + timedelta(days=5),
            )
        )
    await service.record(own.user.id, device, "1.1.0", now=now + timedelta(seconds=1))
    await service.record(own.user.id, device, "0.9.0", now=now - timedelta(seconds=1))
    async with pg.session() as session, session.begin():
        row = await session.get(AppActivityRecord, (device, day(now)))
        assert row.plan == "PREMIUM" and row.app_version == "1.1.0"
        await session.execute(
            update(SubscriptionRecord)
            .where(SubscriptionRecord.user_id == own.user.id)
            .values(current_period_end=now + timedelta(seconds=2))
        )
    assert (await service.latest(now + timedelta(seconds=3), plan="PREMIUM"))["points"][-1][
        "platforms"
    ]["WINDOWS"]["active_users"] == 1
    assert (await service.latest(now + timedelta(seconds=3), plan="FREE"))["points"][-1][
        "platforms"
    ] == {}


async def test_speed_filters_before_account_threshold_and_legacy_is_unknown(fleet_state):  # noqa: F811
    pg, _, nodes = fleet_state
    service = TrafficService(pg, settings())
    user, a, b = uuid4(), uuid4(), uuid4()
    now = datetime.fromtimestamp(BASE + 76, UTC)
    for node, lease in ((nodes[0], a), (nodes[1], b)):
        for seconds, size in ((0, 100000), (5, 103750)):
            value = sample(seconds, lease, size)
            await service.ingest(node, value, {lease: user}, datetime.fromtimestamp(value.at, UTC))
    async with pg.session() as session, session.begin():
        rows = list(
            await session.scalars(
                select(TrafficIntervalRecord).where(TrafficIntervalRecord.node_id.in_(nodes[:2]))
            )
        )
        for row in rows:
            row.data = [
                {**v, "plan": "FREE" if row.node_id == nodes[0] else "PREMIUM"} for v in row.data
            ]
    assert (await service.history("1h", nodes[:2], now))["points"][-1]["download"][
        "active_users"
    ] == 1
    for plan in ("FREE", "PREMIUM"):
        assert (await service.history("1h", nodes[:2], now, plan=plan))["points"][-1]["download"][
            "mean_mbps"
        ] is None
    async with pg.session() as session, session.begin():
        for row in await session.scalars(
            select(TrafficIntervalRecord).where(TrafficIntervalRecord.node_id.in_(nodes[:2]))
        ):
            row.data = [{k: v for k, v in item.items() if k != "plan"} for item in row.data]
    legacy = await service.history("1h", nodes[:2], now, plan="UNKNOWN")
    assert legacy["points"][-1]["download"]["active_users"] == 1
