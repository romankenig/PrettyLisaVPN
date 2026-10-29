"""Actual PostgreSQL migration, idempotency, lease fencing, history and eligibility."""

import os
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select
from test_fleet import healthy, settings

from prettylisavpn.connections import Postgres
from prettylisavpn.fleet.domain import (
    FleetError,
    NodeInput,
    NodeUpdate,
    Observation,
    WireGuardConfig,
    hourly_slot,
)
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
    worker = FleetWorker(postgres, {"wireguard": None})
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


async def test_zero_rating_reschedules_fast_and_recovery_returns_to_hourly(fleet_state):
    postgres, service, ids = fleet_state
    await configured(postgres, ids)
    worker = FleetWorker(postgres, {"wireguard": None})
    now = datetime.now(UTC)
    async with postgres.session() as session, session.begin():
        for identifier in ids:
            method = await session.get(FleetMethodRecord, (identifier, "wireguard"))
            method.next_check_at = now + timedelta(minutes=50)
    # No history means the same zero/STALE rating the dashboard displays.
    await worker.schedule(now)
    async with postgres.session() as session:
        rows = (
            await session.scalars(
                select(FleetMethodRecord).where(FleetMethodRecord.node_id.in_(ids))
            )
        ).all()
        due = {row.node_id: row.next_check_at for row in rows}
    assert len(set(due.values())) == 3
    assert all(now < value <= now + timedelta(minutes=3) for value in due.values())
    target = min(due, key=due.get)
    # An outstanding operation prevents another scheduled job for this target.
    await service.enqueue(target, "wireguard", "CHECK", uuid4())
    await worker.schedule(due[target] + timedelta(milliseconds=1))
    async with postgres.session() as session:
        jobs = (
            await session.scalars(
                select(FleetOperationRecord).where(FleetOperationRecord.node_id == target)
            )
        ).all()
        assert len(jobs) == 1
    claim = await worker.claim(datetime.now(UTC))
    assert claim is not None and claim.target.id == target
    observed = datetime.now(UTC)
    assert await worker.finish(claim, {}, healthy(observed, active_connections=2))
    await worker.schedule(observed + timedelta(milliseconds=1))
    async with postgres.session() as session:
        method = await session.get(FleetMethodRecord, (target, "wireguard"))
        assert method.next_check_at == hourly_slot(
            target, observed + timedelta(milliseconds=1), ids
        )
    # Aging past 75 minutes must accelerate checks even when the stored result
    # was healthy. Active users by themselves never create a zero rating.
    await worker.schedule(observed + timedelta(minutes=76))
    async with postgres.session() as session:
        method = await session.get(FleetMethodRecord, (target, "wireguard"))
        assert (
            observed + timedelta(minutes=76)
            < method.next_check_at
            <= observed + timedelta(minutes=79)
        )


async def test_failed_probe_retries_once_per_three_minute_slot(fleet_state):
    postgres, service, ids = fleet_state
    await configured(postgres, ids)
    worker = FleetWorker(postgres, {"wireguard": None})
    await service.enqueue(ids[0], "wireguard", "CHECK", uuid4())
    claim = await worker.claim(datetime.now(UTC))
    assert claim is not None
    failed = Observation(
        status="FAILED", mode="SYNTHETIC", code="HTTPS_FAILED", observed_at=datetime.now(UTC)
    )
    assert await worker.finish(claim, {}, failed)
    now = datetime.now(UTC)
    await worker.schedule(now)
    async with postgres.session() as session:
        method = await session.get(FleetMethodRecord, (ids[0], "wireguard"))
        due = method.next_check_at
    assert now < due <= now + timedelta(minutes=3)
    for _ in range(2):
        await worker.schedule(due + timedelta(milliseconds=1))
    async with postgres.session() as session:
        jobs = (
            await session.scalars(
                select(FleetOperationRecord).where(
                    FleetOperationRecord.node_id == ids[0], FleetOperationRecord.status == "QUEUED"
                )
            )
        ).all()
        assert len(jobs) == 1 and jobs[0].request_key.startswith("retry:")
        method = await session.get(FleetMethodRecord, (ids[0], "wireguard"))
        assert abs((method.next_check_at - due).total_seconds() - 180) < 0.001


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
    assert history[-1]["measurements"][0]["download_mbps"] == 100
    assert history[-1]["measurements"][0]["upload_mbps"] == 100
    assert history[-1]["measurements"][0]["quality"] == 100
    assert history[0]["measurements"] == []
    free = await service.countries(free_only=True)
    paid = await service.countries(free_only=False)
    assert free["countries"] == [{"country_code": "DE", "quality": 100, "available": True}]
    assert paid["countries"][0] == {"country_code": "DE", "quality": 50, "available": True}
    assert paid["countries"][1]["available"] is False
    with pytest.raises(FleetError, match="fleet_check_rate_limited"):
        await service.enqueue(ids[0], "wireguard", "CHECK", uuid4())


async def test_rating_snapshot_survives_settings_changes_and_legacy_remains_unknown(fleet_state):
    postgres, service, ids = fleet_state
    await configured(postgres, ids, ready=False)
    config = settings().model_copy(
        update={
            "fleet_quality_weights": (0.0, 0.0, 0.0, 1.0),
            "fleet_speed_target_mbps": 100,
        }
    )
    worker = FleetWorker(postgres, {}, config)
    await service.enqueue(ids[0], "wireguard", "CHECK", uuid4())
    claim = await worker.claim(datetime.now(UTC))
    assert claim is not None
    observed = healthy(datetime.now(UTC), download_mbps=50, upload_mbps=25, active_connections=3)
    assert await worker.finish(claim, {}, observed)
    async with postgres.session() as session:
        record = await session.scalar(
            select(FleetObservationRecord).where(FleetObservationRecord.operation_id == claim.id)
        )
        assert record.quality == 25
        assert record.data["download_mbps"] == 50
        assert record.data["upload_mbps"] == 25
    # Current score may change with capacity/weights; historical scores must not.
    service.settings = config.model_copy(update={"fleet_quality_weights": (1.0, 0.0, 0.0, 0.0)})
    snapshot = await service.monitoring(ids[0])
    node = snapshot["nodes"][0]
    assert node["quality"] == 100
    measurement = next(value for hour in node["history"] for value in hour["measurements"])
    assert measurement["quality"] == 25
    assert measurement["active_connections"] == 3
    assert measurement["download_mbps"] == 50
    # Pre-upgrade observations have speed but no rating snapshot. Never backfill
    # using today's settings or confuse a missing rating with a genuine zero.
    async with postgres.session() as session, session.begin():
        record = await session.scalar(
            select(FleetObservationRecord).where(FleetObservationRecord.operation_id == claim.id)
        )
        record.quality = None
    legacy = await service.monitoring(ids[0])
    measurement = next(
        value for hour in legacy["nodes"][0]["history"] for value in hour["measurements"]
    )
    assert measurement["quality"] is None
    assert measurement["download_mbps"] == 50
    assert len(legacy["nodes"]) == 1


async def test_capacity_can_change_without_changing_group_or_old_patch_behavior(fleet_state):
    postgres, service, ids = fleet_state
    nodes = await service.nodes()
    node = next(item for item in nodes if item["id"] == str(ids[0]))
    assert node["capacity"] == 20
    updated = await service.update_node(
        ids[0], NodeUpdate(name=node["name"], group="FREE", capacity=10)
    )
    assert updated["capacity"] == 10
    unchanged = await service.update_node(ids[0], NodeUpdate(name=node["name"], group="FREE"))
    assert unchanged["capacity"] == 10
    await service.update_node(ids[0], NodeUpdate(name=node["name"], group="FREE", capacity=20))
    async with postgres.session() as session:
        assert (await session.get(FleetNodeRecord, ids[0])).capacity == 20
