"""Read-only owner observations; never replicate business data or runnable jobs."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from ipaddress import IPv4Interface
from typing import Any
from uuid import UUID

from pydantic import Field
from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert

from prettylisavpn.connections import Postgres
from prettylisavpn.fleet.domain import FleetError, Node, Observation, Value
from prettylisavpn.fleet.model import (
    FleetMethodRecord,
    FleetNodeRecord,
    FleetObservationRecord,
    FleetOperationRecord,
)
from prettylisavpn.fleet.shared_policy import OWNER_CAPACITY_LIMIT, SNAPSHOT_TTL
from prettylisavpn.fleet.ssh import SshTransport

logger = logging.getLogger(__name__)


class SharedNode(Node):
    created_at: datetime


class SharedMethod(Value):
    node_id: UUID
    method: str = Field(pattern=r"^(wireguard|managed)$")
    configuration: dict[str, Any]
    state: str
    public_key: str | None
    configured_at: datetime | None


class SharedObservation(Value):
    id: UUID
    operation_id: UUID
    node_id: UUID
    source_id: UUID | None
    method: str = Field(pattern=r"^(wireguard|managed)$")
    observed_at: datetime
    data: Observation
    quality: int | None = Field(ge=0, le=100)


class SharedSnapshot(Value):
    generated_at: datetime
    safe_resources: bool
    nodes: list[SharedNode] = Field(min_length=1, max_length=100)
    methods: list[SharedMethod] = Field(max_length=200)
    observations: list[SharedObservation] = Field(max_length=5000)

    def validate_resources(self, now: datetime) -> None:
        if (
            self.generated_at.tzinfo is None
            or not timedelta(0) <= now - self.generated_at < SNAPSHOT_TTL
            or not self.safe_resources
            or any(not 1 <= n.capacity <= OWNER_CAPACITY_LIMIT for n in self.nodes)
        ):
            raise FleetError("FLEET_SHARED_SNAPSHOT_INVALID", 503)
        identifiers = {n.id for n in self.nodes}
        if len(identifiers) != len(self.nodes):
            raise FleetError("FLEET_SHARED_SNAPSHOT_INVALID", 503)
        for method in self.methods:
            if method.node_id not in identifiers or (
                method.method == "wireguard"
                and IPv4Interface(str(method.configuration["address"])).network.prefixlen != 24
            ):
                raise FleetError("FLEET_SHARED_SNAPSHOT_INVALID", 503)
        for item in self.observations:
            if (
                item.node_id not in identifiers
                or (item.source_id is not None and item.source_id not in identifiers)
                or item.observed_at.tzinfo is None
                or item.observed_at > self.generated_at
                or item.observed_at != item.data.observed_at
            ):
                raise FleetError("FLEET_SHARED_SNAPSHOT_INVALID", 503)


async def import_snapshot(postgres: Postgres, snapshot: SharedSnapshot) -> None:
    now = datetime.now(UTC)
    snapshot.validate_resources(now)
    async with postgres.session() as session, session.begin():
        ids = {n.id for n in snapshot.nodes}
        await session.execute(
            update(FleetNodeRecord).where(FleetNodeRecord.id.not_in(ids)).values(enabled=False)
        )
        for node in sorted(snapshot.nodes, key=lambda item: item.id):
            values = node.model_dump()
            statement = insert(FleetNodeRecord).values(**values)
            await session.execute(
                statement.on_conflict_do_update(
                    index_elements=[FleetNodeRecord.id],
                    set_={key: value for key, value in values.items() if key != "id"},
                )
            )
        # Missing configurations must become unavailable, even if older rows exist.
        await session.execute(update(FleetMethodRecord).values(state="REGISTERED"))
        for method in snapshot.methods:
            values = method.model_dump()
            values["configuration"] = {
                **method.configuration,
                "shared_snapshot_at": snapshot.generated_at.isoformat(),
            }
            values["next_check_at"] = None
            statement = insert(FleetMethodRecord).values(**values)
            await session.execute(
                statement.on_conflict_do_update(
                    index_elements=[FleetMethodRecord.node_id, FleetMethodRecord.method],
                    set_={k: v for k, v in values.items() if k not in ("node_id", "method")},
                )
            )
        if snapshot.observations:
            # A terminal IMPORTED record satisfies the FK without claiming a local check.
            jobs = [
                {
                    "id": item.operation_id,
                    "node_id": item.node_id,
                    "source_id": item.source_id,
                    "method": item.method,
                    "kind": "CHECK",
                    "request_key": f"shared:{item.operation_id}",
                    "status": "IMPORTED",
                    "created_at": item.observed_at,
                    "finished_at": item.observed_at,
                    "parameters": {},
                    "result": {"source": "owner-monitoring"},
                }
                for item in snapshot.observations
            ]
            for offset in range(0, len(jobs), 500):
                await session.execute(
                    insert(FleetOperationRecord)
                    .values(jobs[offset : offset + 500])
                    .on_conflict_do_nothing()
                )
            rows = [
                {**item.model_dump(), "data": item.data.model_dump(mode="json")}
                for item in snapshot.observations
            ]
            for offset in range(0, len(rows), 500):
                await session.execute(
                    insert(FleetObservationRecord)
                    .values(rows[offset : offset + 500])
                    .on_conflict_do_nothing()
                )
        await session.execute(
            delete(FleetObservationRecord).where(
                FleetObservationRecord.observed_at < now - timedelta(days=8)
            )
        )


class SharedFleetSync:
    def __init__(self, postgres: Postgres, transport: SshTransport) -> None:
        self.postgres, self.transport = postgres, transport

    async def tick(self) -> None:
        credential = self.transport.inventory["snapshot"]
        source = Node(
            id=UUID(int=0),
            name="owner-snapshot",
            country_code="RU",
            host=credential.host,
            credential_ref="snapshot",
            expected_egress_ips=[credential.host],
            capacity=1,
            is_available_for_free=False,
            enabled=True,
        )
        payload = await self.transport.call(source, "snapshot", command_timeout=25)
        snapshot = SharedSnapshot.model_validate(payload)
        snapshot.validate_resources(datetime.now(UTC))
        for node in snapshot.nodes:
            if node.enabled:
                self.transport.credential(node)
        await import_snapshot(self.postgres, snapshot)

    async def run(self, stop: asyncio.Event) -> None:
        async with self.postgres.session() as session:
            # Refuse a cloned database until copied customer grants have been detached.
            from prettylisavpn.client_vpn.model import ClientLeaseRecord
            from prettylisavpn.fleet.shared_policy import owns_lease

            ids = await session.scalars(
                select(ClientLeaseRecord.id).where(ClientLeaseRecord.removed_at.is_(None))
            )
            if any(not owns_lease(identifier) for identifier in ids):
                raise FleetError("FLEET_IMPORTED_LEASES_NOT_DETACHED", 503)
        while not stop.is_set():
            try:
                await self.tick()
            except Exception:
                logger.warning("shared_fleet_snapshot_unavailable")
            try:
                await asyncio.wait_for(stop.wait(), timeout=30)
            except TimeoutError:
                pass
