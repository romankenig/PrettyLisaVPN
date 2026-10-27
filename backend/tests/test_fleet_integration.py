"""Actual PostgreSQL migration, idempotency, lease fencing, history and eligibility."""

import os
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select
from test_fleet import healthy, settings

from prettylisavpn.connections import Postgres
from prettylisavpn.fleet.domain import FleetError, NodeInput, Observation, WireGuardConfig
from prettylisavpn.fleet.model import (
    FleetMethodRecord,
    FleetNodeRecord,
    FleetObservationRecord,
    FleetOperationRecord,
)
from prettylisavpn.fleet.service import FleetService
from prettylisavpn.fleet.worker import FleetWorker

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1", reason="Requires disposable PostgreSQL"
    ),
]


@pytest.fixture
async def fleet_state():
    config = settings()
    postgres = Postgres(config)
    service = FleetService(postgres, config)
    identifiers = []
    try:
        for index, (host, country, free) in enumerate(
            (("1.1.1.1", "DE", True), ("8.8.8.8", "US", False), ("9.9.9.9", "DE", False))
        ):
            result = await service.register(
                NodeInput(
                    name=f"Fleet-{uuid4()}",
                    country_code=country,
                    host=host,
                    credential_ref=f"test{index}",
                    expected_egress_ips=[host],
                    is_available_for_free=free,
                )
            )
            identifiers.append(UUID(result["id"]))
        yield postgres, service, identifiers
    finally:
        async with postgres.session() as session, session.begin():
            await session.execute(
                delete(FleetObservationRecord).where(
                    FleetObservationRecord.node_id.in_(identifiers)
                )
            )
            await session.execute(
                delete(FleetOperationRecord).where(FleetOperationRecord.node_id.in_(identifiers))
            )
            await session.execute(
                delete(FleetMethodRecord).where(FleetMethodRecord.node_id.in_(identifiers))
            )
            await session.execute(
                delete(FleetNodeRecord).where(FleetNodeRecord.id.in_(identifiers))
            )
        await postgres.close()


async def configured(postgres, identifiers, *, ready=True):
    now = datetime.now(UTC)
    async with postgres.session() as session, session.begin():
        for index, identifier in enumerate(identifiers):
            session.add(
                FleetMethodRecord(
                    node_id=identifier,
                    method="wireguard",
                    configuration={
                        "address": f"10.88.{index}.1/24",
                        "listen_port": 51820,
                        "mtu": 1380,
                    },
                    state="READY" if ready else "AWAITING_VERIFICATION",
                    configured_at=now,
                )
            )


async def test_registration_and_configuration_requests_are_idempotent(fleet_state):
    postgres, service, identifiers = fleet_state
    listed = await service.nodes()
    existing = listed[0]
    data = {key: value for key, value in existing.items() if key not in ("id", "enabled")}
    assert (await service.register(NodeInput.model_validate(data)))["id"] == existing["id"]
    with pytest.raises(FleetError, match="fleet_node_conflict"):
        await service.register(NodeInput.model_validate({**data, "capacity": 200}))
    key = uuid4()
    config = WireGuardConfig(address="10.88.0.1/24")
    first = await service.enqueue(identifiers[0], "wireguard", "CONFIGURE", key, config)
    second = await service.enqueue(identifiers[0], "wireguard", "CONFIGURE", key, config)
    assert first["id"] == second["id"]
    with pytest.raises(FleetError, match="fleet_idempotency_conflict"):
        await service.enqueue(
            identifiers[0], "wireguard", "CONFIGURE", key, WireGuardConfig(address="10.99.0.1/24")
        )
    with pytest.raises(FleetError, match="fleet_method_not_configured"):
        await service.enqueue(identifiers[0], "wireguard", "CHECK", uuid4())


async def test_expired_worker_claim_is_fenced_and_nodes_are_exclusive(fleet_state):
    postgres, service, ids = fleet_state
    await configured(postgres, ids)
    worker = FleetWorker(postgres, {})
    await service.enqueue(ids[0], "wireguard", "CHECK", uuid4())
    now = datetime.now(UTC)
    first = await worker.claim(now)
    assert first is not None and first.source is not None
    assert await worker.claim(now) is None
    recovered = await worker.claim(now + timedelta(minutes=21))
    assert recovered.id == first.id and recovered.token != first.token
    assert await worker.finish(first, {}, healthy(datetime.now(UTC))) is False
    assert await worker.finish(recovered, {}, healthy(datetime.now(UTC))) is True
    assert await worker.finish(recovered, {}, healthy(datetime.now(UTC))) is False
    async with postgres.session() as session:
        rows = (await session.scalars(select(FleetObservationRecord))).all()
        assert len([row for row in rows if row.operation_id == first.id]) == 1
        assert (await session.get(FleetNodeRecord, first.target.id)).lock_owner is None


async def test_hourly_schedule_does_not_replay_outage_and_enrolls_new_nodes(fleet_state):
    postgres, _, ids = fleet_state
    await configured(postgres, ids)
    worker = FleetWorker(postgres, {})
    now = datetime.now(UTC)
    await worker.schedule(now)
    async with postgres.session() as session, session.begin():
        methods = (
            await session.scalars(
                select(FleetMethodRecord).where(FleetMethodRecord.node_id.in_(ids))
            )
        ).all()
        assert len({row.next_check_at for row in methods}) == 3
        for row in methods:
            row.next_check_at = now - timedelta(days=1)
    await worker.schedule(now)
    async with postgres.session() as session:
        assert not (
            await session.scalars(
                select(FleetOperationRecord).where(FleetOperationRecord.node_id.in_(ids))
            )
        ).all()
        methods = (
            await session.scalars(
                select(FleetMethodRecord).where(FleetMethodRecord.node_id.in_(ids))
            )
        ).all()
        assert all(row.next_check_at > now for row in methods)


async def test_passive_observation_has_no_fictitious_source(fleet_state):
    postgres, service, ids = fleet_state
    await configured(postgres, ids)
    await service.enqueue(ids[0], "wireguard", "CHECK", uuid4())
    worker = FleetWorker(postgres, {})
    claim = await worker.claim(datetime.now(UTC))
    assert claim is not None and claim.source is not None
    passive = Observation(
        status="UNKNOWN",
        mode="PASSIVE",
        code="PASSIVE_EVIDENCE_INSUFFICIENT",
        observed_at=datetime.now(UTC),
    )
    await worker.finish(claim, {}, passive)
    async with postgres.session() as session:
        observation = await session.scalar(
            select(FleetObservationRecord).where(FleetObservationRecord.operation_id == claim.id)
        )
        assert observation.source_id is None
        assert (await session.get(FleetOperationRecord, claim.id)).source_id is None


async def test_history_is_honest_and_country_rating_uses_eligible_nodes(fleet_state):
    postgres, service, ids = fleet_state
    await configured(postgres, ids)
    worker = FleetWorker(postgres, {})
    now = datetime.now(UTC)
    await service.enqueue(ids[0], "wireguard", "CHECK", uuid4())
    claim = await worker.claim(datetime.now(UTC))
    assert claim is not None
    await worker.finish(
        claim, {}, healthy(now, connection_ms=100, download_mbps=100, upload_mbps=100)
    )
    all_nodes = await service.monitoring()
    assert len(all_nodes["nodes"]) == 3
    assert all_nodes["overall"]["available_servers"] == 1
    history = next(item for item in all_nodes["nodes"] if item["id"] == str(ids[0]))["history"]
    assert len(history) == 168
    assert history[0]["status"] == "NOT_REGISTERED"
    assert history[-1]["status"] == "HEALTHY"
    free = await service.countries(free_only=True)
    paid = await service.countries(free_only=False)
    assert free["countries"] == [{"country_code": "DE", "quality": 100, "available": True}]
    assert paid["countries"][0] == {"country_code": "DE", "quality": 50, "available": True}
    assert paid["countries"][1]["available"] is False
    with pytest.raises(FleetError, match="fleet_check_rate_limited"):
        await service.enqueue(ids[0], "wireguard", "CHECK", uuid4())
