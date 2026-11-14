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
from prettylisavpn.fleet.service_check_model import ServiceCheckRecord
from prettylisavpn.fleet.service_check_worker import ServiceCheckWorker
from prettylisavpn.fleet.service_checks import ServiceAnalytics
from prettylisavpn.fleet.traffic import Snapshot
from prettylisavpn.fleet.traffic_service import TrafficService
from prettylisavpn.product_analytics.activity import DatabaseActivitySink
from prettylisavpn.product_analytics.domain import day
from prettylisavpn.product_analytics.model import ActivityRecord, SessionSilenceRecord
from prettylisavpn.traffic.model import TrafficServiceRecord
from prettylisavpn.users.model import UserRecord

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1", reason="Requires disposable PostgreSQL"
    ),
]


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
