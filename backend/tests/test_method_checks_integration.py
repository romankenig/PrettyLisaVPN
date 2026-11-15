"""Real daily-job persistence, relay/admission locking and aggregate evidence."""

import os
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select, update
from test_client_vpn_integration import connect, vpn_state  # noqa: F401
from test_fleet_integration import fleet_state  # noqa: F401

from prettylisavpn.client_vpn.methods import METHODS
from prettylisavpn.client_vpn.model import ClientLeaseRecord
from prettylisavpn.fleet.method_check_model import MethodCheckRecord
from prettylisavpn.fleet.method_check_worker import MethodCheckWorker
from prettylisavpn.fleet.method_checks import MethodAnalytics
from prettylisavpn.fleet.model import FleetNodeRecord
from prettylisavpn.product_analytics.domain import day
from prettylisavpn.users.model import UserRecord

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1", reason="Requires disposable PostgreSQL"
    ),
]


async def test_daily_method_jobs_reserve_relay_ports_without_blocking_clients(vpn_state):  # noqa: F811
    postgres, client, client_worker, _, identity = vpn_state
    worker = MethodCheckWorker(postgres, AsyncMock(), SimpleNamespace(key=None))
    now = datetime.now(UTC)
    try:
        await worker.schedule(now)
        async with postgres.session() as session:
            rows = list(await session.scalars(select(MethodCheckRecord)))
            assert {r.method for r in rows} == METHODS
            slots = {r.method: r.scheduled_at for r in rows}
            assert len(set(slots.values())) == len(METHODS)
            assert min(slots.values()) == now + timedelta(seconds=30)
        await worker.schedule(now + timedelta(minutes=1))
        async with postgres.session() as session, session.begin():
            assert {
                r.method: r.scheduled_at for r in await session.scalars(select(MethodCheckRecord))
            } == slots
            relay = await session.scalar(
                select(FleetNodeRecord).where(FleetNodeRecord.host == "9.9.9.9")
            )
            relay.group, relay.is_available_for_free = "INTERMEDIATE", False
            relay_id = relay.id
            await session.execute(
                update(MethodCheckRecord).values(next_attempt_at=now + timedelta(days=1))
            )
            await session.execute(
                update(MethodCheckRecord)
                .where(MethodCheckRecord.method == "wireguard_relay")
                .values(next_attempt_at=now)
            )
        claim = await worker.claim(now)
        assert claim and claim.method == "wireguard_relay" and claim.relay.id == relay_id
        assert len({claim.source.id, claim.target.id, claim.relay.id}) == 3
        assert claim.relay_port == 29999
        async with postgres.session() as session, session.begin():
            row = await session.get(MethodCheckRecord, ("wireguard_relay", day(now)))
            # Reserve admission's first-choice port to prove exclusion, not just
            # different allocation order between the two callers.
            row.relay_port = 20000
        # A real client reserves a distinct port while synthetic node locks are held.
        lease_id = UUID((await connect(client, method="wireguard_relay"))["id"])
        async with postgres.session() as session, session.begin():
            lease = await session.get(ClientLeaseRecord, lease_id)
            assert lease.relay_port == 20001
            lease.status, lease.verified_at = "READY", now
            lease.next_attempt_at = now
            await session.execute(
                update(UserRecord)
                .where(UserRecord.id == identity.user_id)
                .values(email=f"methods-{uuid4()}@gmail.com")
            )
        renewal = await client_worker.claim(now)
        assert renewal and renewal.id == lease_id
        async with postgres.session() as session:
            assert (await session.get(FleetNodeRecord, relay_id)).lock_owner == claim.token
        # A crashed probe retains its reserved port beyond its claim lease.
        assert await worker.claim(now + timedelta(seconds=151)) is None
        next_claim = await worker.claim(now + timedelta(seconds=301))
        assert next_claim and next_claim.target.id != claim.target.id
        async with postgres.session() as session, session.begin():
            row = await session.get(MethodCheckRecord, ("wireguard_relay", day(now)))
            row.claim_until, row.reserved_until = None, None
            row.next_attempt_at = now
            row.attempts = [
                {"node": str(c.target.id), "relay": str(relay_id), "tested": True}
                for c in (claim, next_claim)
            ]
            session.add(
                MethodCheckRecord(
                    method="wireguard_relay",
                    day=day(now) - timedelta(days=1),
                    scheduled_at=now - timedelta(days=1),
                    next_attempt_at=now - timedelta(days=1),
                    finished_at=now - timedelta(days=1),
                    score=100,
                    code="SERVICE_CHECK_PASSED",
                    attempts=[],
                )
            )
        assert await worker.claim(now + timedelta(minutes=7)) is None
        report = await MethodAnalytics(postgres).report(now + timedelta(seconds=1))
        result = next(r for r in report["methods"] if r["id"] == "wireguard_relay")
        assert result["today_score"] == 0 and result["week_score"] == 100
        assert result["observed_days"] == 1 and len(result["points"]) == 7
        assert report["selection"] == {
            "active_sessions": 1,
            "items": [{"method": "wireguard_relay", "count": 1, "share": 100}],
        }
        assert str(lease_id) not in str(report) and "@gmail.com" not in str(report)
        async with postgres.session() as session, session.begin():
            await session.execute(
                update(UserRecord)
                .where(UserRecord.id == identity.user_id)
                .values(email="test@example.com")
            )
        assert (await MethodAnalytics(postgres).report())["selection"]["active_sessions"] == 0
    finally:
        async with postgres.session() as session, session.begin():
            await session.execute(delete(MethodCheckRecord))


async def test_no_configured_route_is_missing_evidence_and_restart_does_not_retry(vpn_state):  # noqa: F811
    postgres, *_ = vpn_state
    now = datetime.now(UTC)
    worker = MethodCheckWorker(postgres, AsyncMock(), SimpleNamespace(key=None))
    try:
        async with postgres.session() as session, session.begin():
            session.add(
                MethodCheckRecord(
                    method="https_proxy",
                    day=day(now),
                    scheduled_at=now,
                    next_attempt_at=now,
                    attempts=[],
                )
            )
        assert await worker.claim(now) is None
        async with postgres.session() as session:
            row = await session.get(MethodCheckRecord, ("https_proxy", day(now)))
            assert row.score is None and row.code == "NO_PROBE_ROUTE" and not row.attempts
        assert (
            await MethodCheckWorker(postgres, AsyncMock(), SimpleNamespace(key=None)).claim(
                now + timedelta(minutes=1)
            )
            is None
        )
    finally:
        async with postgres.session() as session, session.begin():
            await session.execute(delete(MethodCheckRecord))
