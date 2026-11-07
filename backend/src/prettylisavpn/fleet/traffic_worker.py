"""Five-second sampling via the existing pinned SSH inventory, independent of probes."""

import asyncio
import logging
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select, text

from prettylisavpn.client_vpn.model import ClientLeaseRecord
from prettylisavpn.config import Settings
from prettylisavpn.connections import Postgres
from prettylisavpn.fleet.domain import Node
from prettylisavpn.fleet.model import FleetNodeRecord
from prettylisavpn.fleet.service import node_value
from prettylisavpn.fleet.ssh import NodeTransport
from prettylisavpn.fleet.traffic import Snapshot
from prettylisavpn.fleet.traffic_service import TrafficService

logger = logging.getLogger(__name__)


class TrafficWorker:
    def __init__(self, postgres: Postgres, transport: NodeTransport, settings: Settings):
        self.postgres, self.transport = postgres, transport
        self.service = TrafficService(postgres, settings)
        self.next_prune = 0.0

    async def sample(self, node: Node) -> None:
        try:
            async with asyncio.timeout(4.5):
                raw = await self.transport.call(node, "traffic", command_timeout=4)
                snapshot = Snapshot.model_validate(raw)
                async with self.postgres.session() as session:
                    leases = (
                        await session.scalars(
                            select(ClientLeaseRecord).where(
                                ClientLeaseRecord.node_id == node.id,
                                or_(
                                    ClientLeaseRecord.removed_at.is_(None),
                                    ClientLeaseRecord.removed_at
                                    > datetime.now(UTC) - timedelta(seconds=30),
                                ),
                            )
                        )
                    ).all()
                owners = {lease.id: lease.user_id for lease in leases}
                present = {row.lease_id for row in snapshot.counters}
                expected = {
                    lease.id
                    for lease in leases
                    if lease.status == "READY" and lease.removed_at is None
                }
                if expected - present or present - owners.keys():
                    snapshot.complete = False
                await self.service.ingest(node.id, snapshot, owners, datetime.now(UTC))
        except Exception:
            # Transport exception strings may contain credentials. No counter payloads.
            logger.warning("traffic_sample_unavailable", extra={"node_id": str(node.id)})

    async def tick(self) -> None:
        async with self.postgres.session() as session, session.begin():
            if not await session.scalar(text("SELECT pg_try_advisory_xact_lock(860120047)")):
                return
            nodes = (
                await session.scalars(
                    select(FleetNodeRecord).where(
                        FleetNodeRecord.enabled,
                        FleetNodeRecord.group != "INTERMEDIATE",
                    )
                )
            ).all()
            await asyncio.gather(*(self.sample(node_value(node)) for node in nodes))
        if time.monotonic() >= self.next_prune:
            await self.service.prune(datetime.now(UTC))
            self.next_prune = time.monotonic() + 3600

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            started = time.monotonic()
            try:
                await self.tick()
            except Exception:
                logger.error("traffic_collection_failed")
            try:
                await asyncio.wait_for(
                    stop.wait(), timeout=max(0.05, 5 - (time.monotonic() - started))
                )
            except TimeoutError:
                pass
