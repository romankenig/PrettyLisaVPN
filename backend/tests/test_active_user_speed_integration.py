"""Durable deduplication, recovery, filtering and history against PostgreSQL."""

import asyncio
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update
from test_active_user_speed import BASE, sample
from test_fleet import settings
from test_fleet_integration import fleet_state as _fleet_state

from prettylisavpn.fleet.domain import FleetError
from prettylisavpn.fleet.model import FleetNodeRecord
from prettylisavpn.fleet.traffic_model import TrafficCursorRecord, TrafficIntervalRecord
from prettylisavpn.fleet.traffic_service import TrafficService

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1", reason="Requires disposable PostgreSQL"
    ),
]

fleet_state = _fleet_state


async def test_idempotent_ingest_account_filtering_recovery_and_retention(fleet_state):
    postgres, _, ids = fleet_state
    service = TrafficService(postgres, settings())
    user, lease_a, lease_b = uuid4(), uuid4(), uuid4()
    now = datetime.fromtimestamp(BASE + 68, UTC)
    for node, lease in ((ids[0], lease_a), (ids[1], lease_b)):
        before, after = sample(0, lease, 100000), sample(5, lease, 103750)
        await service.ingest(node, before, {lease: user}, datetime.fromtimestamp(before.at, UTC))
        results = await asyncio.gather(
            *(
                service.ingest(node, after, {lease: user}, datetime.fromtimestamp(after.at, UTC))
                for _ in range(3)
            )
        )
        assert sum(results) == 1
        assert not await service.ingest(
            node, before, {lease: user}, datetime.fromtimestamp(before.at, UTC)
        )
    async with postgres.session() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(TrafficIntervalRecord)
                .where(TrafficIntervalRecord.node_id.in_(ids))
            )
            == 4
        )
    combined = await service.history("1h", ids[:2], now)
    point = combined["points"][-1]
    assert point["download"]["mean_mbps"] == 0.012
    assert point["download"]["active_users"] == 1
    assert point["download"]["active_seconds"] == 5
    assert point["coverage"]["fraction"] == pytest.approx(5 / 60)
    assert point["download"]["reference_percent"] is None
    assert str(user) not in str(combined)  # No per-account data leaves the aggregate API.
    selected = await service.history("1h", [ids[0]], now)
    assert selected["points"][-1]["download"]["mean_mbps"] is None
    # A new service instance uses the durable baseline, not process memory.
    after = sample(10, lease_a, 107500)
    recovered = TrafficService(postgres, settings())
    assert await recovered.ingest(
        ids[0], after, {lease_a: user}, datetime.fromtimestamp(after.at, UTC)
    )
    reset = sample(15, lease_a, 0)
    await recovered.ingest(ids[0], reset, {lease_a: user}, datetime.fromtimestamp(reset.at, UTC))
    async with postgres.session() as session:
        row = await session.get(
            TrafficIntervalRecord, (ids[0], datetime.fromtimestamp(reset.at, UTC))
        )
        assert row.data == [] and row.complete is False
    await recovered.prune(now + timedelta(days=9))
    async with postgres.session() as session:
        assert not (
            await session.scalars(
                select(TrafficIntervalRecord).where(TrafficIntervalRecord.node_id.in_(ids))
            )
        ).all()
        assert await session.get(TrafficCursorRecord, ids[0]) is None


async def test_filters_reject_unknown_nodes_and_exclude_transit_without_zero(fleet_state):
    postgres, _, ids = fleet_state
    service = TrafficService(postgres, settings())
    async with postgres.session() as session, session.begin():
        await session.execute(
            update(FleetNodeRecord)
            .where(FleetNodeRecord.id == ids[2])
            .values(group="INTERMEDIATE", is_available_for_free=False)
        )
    response = await service.history("7d", [ids[2]])
    assert response["nodes"] == []
    assert response["excluded_transit_nodes"] == [str(ids[2])]
    assert all(point["download"]["mean_mbps"] is None for point in response["points"])
    assert len(response["points"]) == 168
    with pytest.raises(FleetError, match="traffic_node_not_found"):
        await service.history("1h", [uuid4()])


async def test_clock_skew_is_rejected_without_poisoning_cursor(fleet_state):
    postgres, _, ids = fleet_state
    service = TrafficService(postgres, settings())
    with pytest.raises(FleetError, match="traffic_clock_skew"):
        await service.ingest(
            ids[0], sample(0, uuid4()), {}, datetime.fromtimestamp(BASE + 100, UTC)
        )
    async with postgres.session() as session:
        assert await session.get(TrafficCursorRecord, ids[0]) is None
