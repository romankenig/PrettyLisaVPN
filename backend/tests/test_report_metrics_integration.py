"""Real migrations, configured selections, counter evidence and durable retry state."""

import os
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select, update
from test_client_vpn_integration import connect, vpn_state  # noqa: F401
from test_fleet import settings
from test_fleet_integration import configured, fleet_state  # noqa: F401

from prettylisavpn.client_vpn.model import ClientLeaseRecord
from prettylisavpn.devices.domain import DevicePlatform
from prettylisavpn.devices.model import DeviceRecord
from prettylisavpn.fleet.model import FleetNodeRecord
from prettylisavpn.fleet.service_check_model import ServiceCheckRecord
from prettylisavpn.fleet.service_check_worker import ServiceCheckWorker
from prettylisavpn.fleet.service_checks import ServiceAnalytics
from prettylisavpn.fleet.traffic import Snapshot
from prettylisavpn.fleet.traffic_service import TrafficService
from prettylisavpn.product_analytics.activity import DatabaseActivitySink
from prettylisavpn.product_analytics.domain import boundary, day
from prettylisavpn.product_analytics.model import (
    ActivityRecord,
    AnalyticsSnapshotRecord,
    SessionSilenceRecord,
)
from prettylisavpn.product_analytics.service import ProductAnalyticsService
from prettylisavpn.traffic.model import TrafficServiceRecord
from prettylisavpn.users.model import UserRecord

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1", reason="Requires disposable PostgreSQL"
    ),
]


async def test_daily_device_report_uses_accounts_without_exposing_identity(vpn_state):  # noqa: F811
    postgres, service, worker, _, identity = vpn_state
    lease_id = UUID((await connect(service))["id"])
    await worker.tick()
    at = datetime(2098, 6, 1, 12, tzinfo=UTC)
    email = f"daily-platforms-{uuid4()}@gmail.com"
    async with postgres.session() as session, session.begin():
        await session.execute(
            update(UserRecord).where(UserRecord.id == identity.user_id).values(email=email)
        )
        await session.execute(
            update(DeviceRecord)
            .where(DeviceRecord.id == identity.device_id)
            .values(platform=DevicePlatform.ANDROID)
        )
        lease = await session.get(ClientLeaseRecord, lease_id)
        lease.created_at, lease.verified_at = at, at + timedelta(seconds=5)
        lease.removed_at = lease.disconnected_at = at + timedelta(minutes=1)
        lease.expires_at, lease.heartbeat_at = at + timedelta(hours=1), lease.removed_at
        lease.status = "CLOSED"
        await session.flush()
        fields = {
            column.key: getattr(lease, column.key) for column in ClientLeaseRecord.__table__.columns
        }
        fields.update(
            id=uuid4(),
            request_id=uuid4(),
            created_at=at + timedelta(minutes=2),
            verified_at=at + timedelta(minutes=2, seconds=5),
            removed_at=at + timedelta(minutes=3),
            disconnected_at=at + timedelta(minutes=3),
            heartbeat_at=at + timedelta(minutes=3),
        )
        session.add(ClientLeaseRecord(**fields))
    analytics = ProductAnalyticsService(postgres)
    async with postgres.session() as session:
        report = await analytics.build(session, at + timedelta(days=1))
    assert report["points"][-1]["device_platforms"] == {
        "connections": {"ANDROID": 2},
        "users": {"ANDROID": 1},
    }
    assert str(identity.user_id) not in str(report) and email not in str(report)
    async with postgres.session() as session, session.begin():
        await session.execute(
            update(UserRecord)
            .where(UserRecord.id == identity.user_id)
            .values(email=f"excluded-{uuid4()}@example.com")
        )
    async with postgres.session() as session:
        excluded = await analytics.build(session, at + timedelta(days=1))
    assert excluded["points"][-1]["device_platforms"] == {"connections": {}, "users": {}}


async def test_live_device_day_is_fresh_separate_and_rolls_over_without_mutating_history(
    vpn_state,  # noqa: F811
):
    postgres, service, worker, _, identity = vpn_state
    lease_id = UUID((await connect(service))["id"])
    await worker.tick()
    now = datetime(2099, 8, 3, 12, tzinfo=UTC)
    midnight = boundary(day(now))
    yesterday = day(now) - timedelta(days=1)
    analytics = ProductAnalyticsService(postgres)
    email = f"today-platforms-{uuid4()}@gmail.com"
    async with postgres.session() as session, session.begin():
        await session.execute(
            update(UserRecord).where(UserRecord.id == identity.user_id).values(email=email)
        )
        await session.execute(
            update(DeviceRecord)
            .where(DeviceRecord.id == identity.device_id)
            .values(platform=DevicePlatform.WINDOWS)
        )
        chrome_ids = [uuid4(), uuid4()]
        session.add_all(
            DeviceRecord(
                id=device_id,
                user_id=identity.user_id,
                installation_id=uuid4(),
                platform=DevicePlatform.CHROME_EXTENSION,
                device_name="Chrome",
            )
            for device_id in chrome_ids
        )
        lease = await session.get(ClientLeaseRecord, lease_id)
        lease.created_at = midnight - timedelta(hours=1)
        lease.verified_at = midnight - timedelta(seconds=1)
        lease.removed_at = lease.disconnected_at = now + timedelta(hours=1)
        lease.expires_at, lease.heartbeat_at = now + timedelta(hours=2), now
        lease.status = "CLOSED"
        await session.flush()
        fields = {
            column.key: getattr(lease, column.key) for column in ClientLeaseRecord.__table__.columns
        }
        for device_id, verified in [
            (identity.device_id, midnight),
            (identity.device_id, now),
            (chrome_ids[0], midnight + timedelta(seconds=1)),
            (chrome_ids[0], midnight + timedelta(seconds=5)),
            (chrome_ids[1], midnight + timedelta(seconds=8)),
            (chrome_ids[0], None),
            (chrome_ids[0], now + timedelta(seconds=1)),
        ]:
            session.add(
                ClientLeaseRecord(
                    **{
                        **fields,
                        "id": uuid4(),
                        "request_id": uuid4(),
                        "device_id": device_id,
                        "method": "https_proxy" if device_id in chrome_ids else "wireguard",
                        "address": None if device_id in chrome_ids else fields["address"],
                        "engine_port": 41000 if device_id in chrome_ids else None,
                        "verified_at": verified,
                    }
                )
            )
    try:
        assert await analytics.refresh(now)
        async with postgres.session() as session, session.begin():
            await session.execute(
                update(UserRecord).where(UserRecord.id == identity.user_id).values(created_at=now)
            )
            session.add(
                ActivityRecord(
                    user_id=identity.user_id, day=day(now), observed_at=now, plan="PREMIUM"
                )
            )
            lease = await session.get(ClientLeaseRecord, lease_id)
            lease.disconnected_at = now - timedelta(seconds=20)
            session.add(
                SessionSilenceRecord(
                    lease_id=lease_id,
                    observed_until=now,
                    first_silence_at=midnight + timedelta(seconds=9),
                    complete=True,
                )
            )
        first = await analytics.latest(now)
        assert first["through_date"] == yesterday.isoformat()
        assert first["points"][-1]["device_platforms"]["connections"] == {"WINDOWS": 1}
        assert first["device_today"] == {
            "date": day(now).isoformat(),
            "partial": True,
            "updated_at": now.isoformat(),
            "device_platforms": {
                "connections": {"CHROME_EXTENSION": 3, "WINDOWS": 2},
                "users": {"CHROME_EXTENSION": 1, "WINDOWS": 1},
            },
        }
        later = await analytics.latest(now + timedelta(minutes=1))
        current = first["live"]["point"]
        assert first["live"]["partial"] and first["live"]["updated_at"] == now.isoformat()
        assert current["dau"]["total"] == current["dau"]["plans"]["PREMIUM"] == 1
        assert current["new_accounts"] == 1 and current["verified_sessions"] == 5
        assert current["completed_sessions"] == 1
        assert (
            current["mean_session_seconds"]
            == (now - timedelta(seconds=20) - (midnight - timedelta(seconds=1))).total_seconds()
        )
        assert first["live"]["summary"]["session_duration"]["samples"] == 1
        assert first["live"]["summary"]["time_to_silence"]["counts"] == [1, 0, 0, 0, 0, 0]
        assert later["live"]["point"]["verified_sessions"] == 6
        assert later["device_today"]["device_platforms"]["connections"]["CHROME_EXTENSION"] == 4
        assert later["device_today"]["device_platforms"]["users"]["CHROME_EXTENSION"] == 1
        assert later["points"] == first["points"]
        async with postgres.session() as session:
            saved = (await session.get(AnalyticsSnapshotRecord, yesterday)).data
            assert not {"device_today", "live", "duration_history", "plan"}.intersection(saved)
            assert saved == {
                key: value
                for key, value in first.items()
                if key not in {"device_today", "live", "duration_history", "plan"}
            }
        assert first["plan"] == first["duration_history"]["plan"] == "ALL"
        assert first["duration_history"]["points"][-1]["sessions"] == 5
        assert later["duration_history"]["points"][-1]["sessions"] == 6
        assert email not in str(later) and str(identity.user_id) not in str(later)
        next_midnight = midnight + timedelta(days=1)
        rolled = await analytics.latest(next_midnight)
        assert rolled["device_today"]["date"] == day(next_midnight).isoformat()
        assert rolled["device_today"]["device_platforms"] == {"connections": {}, "users": {}}
        assert rolled["live"]["point"]["dau"]["total"] == 0
        assert rolled["live"]["point"]["wau"]["plans"]["PREMIUM"] == 1
        assert rolled["live"]["point"]["new_accounts"] == 0
        assert await analytics.refresh(next_midnight)
        finalized = await analytics.latest(next_midnight)
        assert (
            finalized["points"][-1]["device_platforms"] == later["device_today"]["device_platforms"]
        )
        async with postgres.session() as session, session.begin():
            await session.execute(
                update(UserRecord)
                .where(UserRecord.id == identity.user_id)
                .values(email=f"excluded-{uuid4()}@example.com")
            )
        # A midnight publication racing a read cannot turn its current day into history.
        before_midnight = await analytics.latest(now)
        assert before_midnight["through_date"] == yesterday.isoformat()
        assert before_midnight["device_today"]["device_platforms"] == {
            "connections": {},
            "users": {},
        }
        assert before_midnight["live"]["point"]["dau"]["total"] == 0
        assert before_midnight["live"]["point"]["new_accounts"] == 0
        assert before_midnight["live"]["summary"]["session_duration"]["samples"] == 0
    finally:
        async with postgres.session() as session, session.begin():
            await session.execute(
                delete(AnalyticsSnapshotRecord).where(
                    AnalyticsSnapshotRecord.through_date.in_([yesterday, day(now)])
                )
            )


async def test_legacy_client_mode_is_unknown_and_service_checks_allow_renewal(vpn_state):  # noqa: F811
    postgres, service, worker, _, _ = vpn_state
    lease_id = UUID((await connect(service))["id"])
    await worker.tick()
    now, token = datetime.now(UTC), uuid4()
    async with postgres.session() as session, session.begin():
        lease = await session.get(ClientLeaseRecord, lease_id)
        assert lease.traffic_mode is None and lease.service_ids is None
        lease.next_attempt_at = now
        node = await session.get(FleetNodeRecord, lease.node_id)
        node.lock_owner, node.lock_until = token, now + timedelta(seconds=150)
        service_id = await session.scalar(select(TrafficServiceRecord.id).limit(1))
        session.add(
            ServiceCheckRecord(
                service_id=service_id,
                day=day(now),
                scheduled_at=now,
                next_attempt_at=now,
                claim_token=token,
                claim_until=node.lock_until,
                attempts=[],
            )
        )
    try:
        claim = await worker.claim(now)
        assert claim is not None and claim.id == lease_id
        async with postgres.session() as session:
            node = await session.get(FleetNodeRecord, claim.node.id)
            assert node.lock_owner == token
    finally:
        async with postgres.session() as session, session.begin():
            await session.execute(
                delete(ServiceCheckRecord).where(ServiceCheckRecord.claim_token == token)
            )


async def test_selected_services_counter_silence_and_disconnect_survive_restart(vpn_state):  # noqa: F811
    postgres, service, worker, _, identity = vpn_state
    async with postgres.session() as session, session.begin():
        await session.execute(
            update(UserRecord)
            .where(UserRecord.id == identity.user_id)
            .values(email=f"metrics-{uuid4()}@gmail.com")
        )
        catalog = await session.scalar(
            select(TrafficServiceRecord).where(TrafficServiceRecord.enabled).limit(1)
        )
        service_id, slug = catalog.id, catalog.slug
    lease_id = UUID(
        (
            await connect(
                service,
                traffic_mode="include",
                service_ids=[service_id, service_id],
                custom_rules=["*.manual.example.org"],
            )
        )["id"]
    )
    await worker.tick()
    async with postgres.session() as session, session.begin():
        lease = await session.get(ClientLeaseRecord, lease_id)
        node_id = lease.node_id
        started = datetime.now(UTC)
        lease.verified_at = started
        assert lease.service_ids == [str(service_id)]
        assert lease.custom_rules == ["*.manual.example.org"]
    report = await ServiceAnalytics(postgres).report()
    assert report["selection"]["observed_sessions"] == 1
    assert {item["service"]: item["count"] for item in report["selection"]["items"]} == {
        slug: 1,
        "UNKNOWN": 1,
    }
    assert "manual.example.org" not in str(report) and str(lease_id) not in str(report)
    traffic = TrafficService(postgres, settings())
    for offset, amount in [(-2, 0), (3, 10), (8, 10), (13, 10)]:
        at = started + timedelta(seconds=offset)
        sample = Snapshot(
            at=at.timestamp(),
            monotonic=100 + offset,
            boot="metrics",
            complete=True,
            counters=[
                dict(
                    lease_id=lease_id,
                    epoch="one",
                    at=at.timestamp(),
                    monotonic=100 + offset,
                    download=amount,
                    upload=0,
                )
            ],
        )
        await traffic.ingest(node_id, sample, {lease_id: identity.user_id}, at)
    async with postgres.session() as session:
        evidence = await session.get(SessionSilenceRecord, lease_id)
        assert evidence.complete
        assert evidence.first_silence_at == started + timedelta(seconds=3)
    await service.get("token", lease_id, "revoke")
    async with postgres.session() as session:
        disconnected = (await session.get(ClientLeaseRecord, lease_id)).disconnected_at
        assert disconnected is not None
    await worker.tick()
    async with postgres.session() as session:
        assert (await session.get(ClientLeaseRecord, lease_id)).disconnected_at == disconnected
    assert (await ServiceAnalytics(postgres).report())["selection"]["active_sessions"] == 0


async def test_demo_is_a_real_analytics_cohort(vpn_state):  # noqa: F811
    postgres, _, _, _, identity = vpn_state
    async with postgres.session() as session, session.begin():
        await session.execute(
            update(UserRecord)
            .where(UserRecord.id == identity.user_id)
            .values(email=f"{uuid4()}@demo.prettylisavpn.com")
        )
    await DatabaseActivitySink(postgres).record(identity.user_id)
    async with postgres.session() as session:
        assert (
            await session.get(ActivityRecord, (identity.user_id, day(datetime.now(UTC))))
        ).plan == "DEMO"


async def test_daily_jobs_are_deduplicated_restart_safe_and_exhaust_distinct_routes(fleet_state):  # noqa: F811
    postgres, _, nodes = fleet_state
    await configured(postgres, nodes)
    now = datetime.now(UTC)
    worker = ServiceCheckWorker(postgres, AsyncMock(), SimpleNamespace(key=None))
    service_id = uuid4()
    async with postgres.session() as session, session.begin():
        session.add(
            TrafficServiceRecord(
                id=service_id,
                slug=f"test-{service_id.hex[:20]}",
                name="Synthetic test",
                icon="generic",
                domains=["example.com"],
                enabled=False,
            )
        )
        await session.flush()
        session.add(
            ServiceCheckRecord(
                service_id=service_id,
                day=day(now),
                scheduled_at=now,
                next_attempt_at=now,
                attempts=[],
            )
        )
    try:
        # Disabled services cannot generate probes.
        assert await worker.claim(now) is None
        async with postgres.session() as session, session.begin():
            await session.execute(
                update(TrafficServiceRecord)
                .where(TrafficServiceRecord.id == service_id)
                .values(enabled=True)
            )
            await session.execute(
                update(ServiceCheckRecord)
                .where(ServiceCheckRecord.service_id == service_id)
                .values(finished_at=None)
            )
        first = await worker.claim(now)
        assert first is not None
        assert (
            await ServiceCheckWorker(postgres, AsyncMock(), SimpleNamespace(key=None)).claim(
                now + timedelta(seconds=30)
            )
            is None
        )
        # Expired claimant resumes with a distinct pair, never the first server.
        second = await worker.claim(now + timedelta(seconds=151))
        assert second is not None and second[4].id != first[4].id
        async with postgres.session() as session, session.begin():
            row = await session.get(ServiceCheckRecord, (service_id, day(now)))
            row.claim_until = None
            row.next_attempt_at = now
            row.attempts = [
                {"node": str(node), "method": "wireguard", "tested": True} for node in nodes
            ]
        assert await worker.claim(now + timedelta(minutes=4)) is None
        async with postgres.session() as session:
            row = await session.get(ServiceCheckRecord, (service_id, day(now)))
            assert row.finished_at is not None and row.score == 0
    finally:
        async with postgres.session() as session, session.begin():
            await session.execute(
                delete(ServiceCheckRecord).where(ServiceCheckRecord.service_id == service_id)
            )
            await session.execute(
                delete(TrafficServiceRecord).where(TrafficServiceRecord.id == service_id)
            )
