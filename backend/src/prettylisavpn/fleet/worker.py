"""Separate control-plane process. PostgreSQL owns schedules, leases and results."""

import asyncio
import logging
import signal
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid4, uuid5

from sqlalchemy import delete, or_, select, update

from prettylisavpn.client_vpn.model import ClientLeaseRecord
from prettylisavpn.config import Settings
from prettylisavpn.connections import Postgres
from prettylisavpn.fleet.domain import (
    FleetError,
    Node,
    Observation,
    VpnMethod,
    monitoring_slot,
    server_quality,
    source_order,
)
from prettylisavpn.fleet.model import (
    FleetMethodRecord,
    FleetNodeRecord,
    FleetObservationRecord,
    FleetOperationRecord,
)
from prettylisavpn.fleet.service import node_value
from prettylisavpn.logging import configure_logging

logger = logging.getLogger(__name__)
LEASE_SECONDS = 1200
OPERATION_TIMEOUT = 900


@dataclass(frozen=True)
class Claim:
    id: UUID
    token: UUID
    target: Node
    source: Node | None
    method: str
    kind: str
    parameters: dict[str, object]


def unknown(code: str) -> Observation:
    return Observation(status="UNKNOWN", mode="CONTROL", code=code, observed_at=datetime.now(UTC))


class FleetWorker:
    def __init__(
        self, postgres: Postgres, methods: dict[str, VpnMethod], settings: Settings | None = None
    ) -> None:
        self.postgres, self.methods = postgres, methods
        self.settings = settings or Settings()

    async def schedule(self, now: datetime) -> None:
        async with self.postgres.session() as session, session.begin():
            nodes = (
                await session.scalars(
                    select(FleetNodeRecord).where(FleetNodeRecord.enabled.is_(True))
                )
            ).all()
            enabled = {node.id for node in nodes}
            configured = (
                await session.scalars(
                    select(FleetMethodRecord)
                    .where(
                        FleetMethodRecord.configured_at.is_not(None),
                        FleetMethodRecord.node_id.in_(enabled),
                        FleetMethodRecord.method.in_(self.methods),
                    )
                    .with_for_update(skip_locked=True)
                )
            ).all()
            slots = [
                row.node_id if row.method == "wireguard" else uuid5(row.node_id, row.method)
                for row in configured
            ]
            history: dict[tuple[UUID, str], list[Observation]] = defaultdict(list)
            for row in await session.scalars(
                select(FleetObservationRecord).where(
                    FleetObservationRecord.node_id.in_(enabled),
                    FleetObservationRecord.method.in_(self.methods),
                    FleetObservationRecord.observed_at >= now - timedelta(hours=24),
                    FleetObservationRecord.observed_at <= now,
                )
            ):
                history[row.node_id, row.method].append(Observation.model_validate(row.data))
            capacities = {node.id: node.capacity for node in nodes}
            for method in configured:
                slot_id = (
                    method.node_id
                    if method.method == "wireguard"
                    else uuid5(method.node_id, method.method)
                )
                rating = server_quality(
                    history[method.node_id, method.method],
                    capacities[method.node_id],
                    now,
                    speed_target_mbps=self.settings.fleet_speed_target_mbps,
                    connection_target_ms=self.settings.fleet_connection_target_ms,
                    quality_weights=self.settings.fleet_quality_weights,
                )
                rapid = method.state != "READY" or rating["quality"] == 0
                next_slot = monitoring_slot(slot_id, now, slots, rapid=rapid)
                if method.next_check_at is None or (
                    rapid and method.next_check_at > now + timedelta(minutes=3)
                ):
                    method.next_check_at = next_slot
                elif method.next_check_at <= now:
                    # A restart never replays missed slots. One current job per target.
                    outstanding = await session.scalar(
                        select(FleetOperationRecord.id)
                        .where(
                            FleetOperationRecord.node_id == method.node_id,
                            FleetOperationRecord.status.in_(("QUEUED", "RUNNING")),
                        )
                        .limit(1)
                    )
                    grace = timedelta(minutes=3 if rapid else 10)
                    if outstanding is None and now - method.next_check_at < grace:
                        session.add(
                            FleetOperationRecord(
                                node_id=method.node_id,
                                method=method.method,
                                kind="CHECK",
                                request_key=("retry:" if rapid else "hour:")
                                + method.next_check_at.isoformat(),
                            )
                        )
                    method.next_check_at = next_slot
            await session.execute(
                delete(FleetObservationRecord).where(
                    FleetObservationRecord.observed_at < now - timedelta(days=8)
                )
            )

    async def claim(self, now: datetime) -> Claim | None:
        async with self.postgres.session() as session, session.begin():
            job = await session.scalar(
                select(FleetOperationRecord)
                .where(
                    or_(
                        (FleetOperationRecord.status == "QUEUED")
                        & (FleetOperationRecord.next_attempt_at <= now),
                        (FleetOperationRecord.status == "RUNNING")
                        & (FleetOperationRecord.lease_until < now),
                    )
                )
                .order_by(FleetOperationRecord.next_attempt_at)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if job is None:
                return None
            if job.attempts >= 3:
                job.status, job.finished_at, job.result = (
                    "FAILED",
                    now,
                    {"code": "FLEET_RETRY_EXHAUSTED"},
                )
                return None
            nodes = (
                await session.scalars(
                    select(FleetNodeRecord)
                    .where(
                        FleetNodeRecord.enabled.is_(True),
                        or_(FleetNodeRecord.lock_until.is_(None), FleetNodeRecord.lock_until < now),
                        ~select(ClientLeaseRecord.id)
                        .where(
                            or_(
                                ClientLeaseRecord.node_id == FleetNodeRecord.id,
                                ClientLeaseRecord.relay_node_id == FleetNodeRecord.id,
                            ),
                            ClientLeaseRecord.claim_until > now,
                        )
                        .exists(),
                    )
                    .order_by(FleetNodeRecord.id)
                    .with_for_update(skip_locked=True)
                )
            ).all()
            by_id = {row.id: row for row in nodes}
            target = by_id.get(job.node_id)
            if target is None:
                job.next_attempt_at = now + timedelta(seconds=15)
                return None
            roster = list(
                (
                    await session.scalars(
                        select(FleetMethodRecord.node_id).where(
                            FleetMethodRecord.method == job.method,
                            FleetMethodRecord.configured_at.is_not(None),
                        )
                    )
                ).all()
            )
            source = (
                next(
                    (by_id[item] for item in source_order(target.id, now, roster) if item in by_id),
                    None,
                )
                if job.kind == "CHECK"
                else None
            )
            token = uuid4()
            for node in (target, source):
                if node is not None:
                    node.lock_owner, node.lock_until = token, now + timedelta(seconds=LEASE_SECONDS)
            job.status, job.claim_token = "RUNNING", token
            job.lease_until = now + timedelta(seconds=LEASE_SECONDS)
            job.started_at, job.attempts = now, job.attempts + 1
            job.source_id = source.id if source else None
            return Claim(
                job.id,
                token,
                node_value(target),
                node_value(source) if source else None,
                job.method,
                job.kind,
                job.parameters,
            )

    async def execute(self, claim: Claim) -> tuple[dict[str, object], Observation | None]:
        method = self.methods.get(claim.method)
        if method is None:
            raise FleetError("FLEET_METHOD_UNSUPPORTED")
        if claim.kind == "CONFIGURE":
            plan = await method.plan(claim.target, claim.parameters)
            state = await method.configure(claim.target, claim.parameters, claim.id)
            return {"state": state.model_dump(mode="json"), "plan": plan}, None
        state = await method.inspect(claim.target)
        if not state.installed:
            return {}, Observation(
                status="FAILED",
                mode="CONTROL",
                code="METHOD_NOT_INSTALLED",
                observed_at=datetime.now(UTC),
            )
        if claim.source is None:
            return {}, unknown("NO_AVAILABLE_PROBE_SOURCE")
        try:
            origin = await method.inspect(claim.source)
        except FleetError:
            return {}, unknown("PROBE_SOURCE_UNREACHABLE")
        if not origin.installed:
            return {}, unknown("PROBE_SOURCE_NOT_CONFIGURED")
        return {}, await method.probe(claim.source, claim.target, claim.id)

    async def finish(
        self,
        claim: Claim,
        result: dict[str, object],
        observation: Observation | None,
        error: str | None = None,
    ) -> bool:
        now = datetime.now(UTC)
        async with self.postgres.session() as session, session.begin():
            job = await session.get(FleetOperationRecord, claim.id, with_for_update=True)
            if (
                job is None
                or job.claim_token != claim.token
                or job.status != "RUNNING"
                or job.lease_until is None
                or job.lease_until <= now
            ):
                return False
            job.status = (
                "FAILED" if error or observation and observation.status == "FAILED" else "SUCCEEDED"
            )
            job.result = {"code": error} if error else result
            job.finished_at, job.lease_until = now, None
            method = await session.get(
                FleetMethodRecord, (claim.target.id, claim.method), with_for_update=True
            )
            if claim.kind == "CONFIGURE" and not error and method is not None:
                state = result["state"]
                assert isinstance(state, dict)
                method.configuration = (
                    cast(dict[str, object], state["configuration"])
                    if claim.method == "managed"
                    else claim.parameters
                )
                method.public_key = str(state["public_key"])
                method.configured_at = method.configured_at or now
                # Idempotent configure preserves prior validation, otherwise awaits a real probe.
                if method.state != "READY":
                    method.state = "AWAITING_VERIFICATION"
                method.next_check_at = None
            if observation is not None:
                previous = (
                    await session.scalars(
                        select(FleetObservationRecord).where(
                            FleetObservationRecord.node_id == job.node_id,
                            FleetObservationRecord.method == job.method,
                            FleetObservationRecord.observed_at
                            >= observation.observed_at - timedelta(hours=24),
                            FleetObservationRecord.observed_at <= observation.observed_at,
                        )
                    )
                ).all()
                rating = server_quality(
                    [Observation.model_validate(row.data) for row in previous] + [observation],
                    claim.target.capacity,
                    observation.observed_at,
                    speed_target_mbps=self.settings.fleet_speed_target_mbps,
                    connection_target_ms=self.settings.fleet_connection_target_ms,
                    quality_weights=self.settings.fleet_quality_weights,
                )
                if (
                    method is not None
                    and observation.mode == "SYNTHETIC"
                    and observation.status == "HEALTHY"
                ):
                    method.state = "READY"
                quality = (
                    cast(int, rating["quality"])
                    if method is not None and method.state == "READY"
                    else 0
                )
                if method is not None:
                    # The next scheduler tick uses this result: fast on zero,
                    # hourly after recovery, including operator-triggered checks.
                    method.next_check_at = None
                if observation.mode != "SYNTHETIC":
                    job.source_id = None
                job.result = {**job.result, "observation": observation.model_dump(mode="json")}
                session.add(
                    FleetObservationRecord(
                        operation_id=job.id,
                        node_id=job.node_id,
                        source_id=job.source_id,
                        method=job.method,
                        observed_at=observation.observed_at,
                        data=observation.model_dump(mode="json"),
                        quality=quality,
                    )
                )
            await session.execute(
                update(FleetNodeRecord)
                .where(FleetNodeRecord.lock_owner == claim.token)
                .values(lock_owner=None, lock_until=None)
            )
            return True

    async def tick(self) -> bool:
        await self.schedule(datetime.now(UTC))
        claim = await self.claim(datetime.now(UTC))
        if claim is None:
            return False
        try:
            async with asyncio.timeout(OPERATION_TIMEOUT):
                result, observation = await self.execute(claim)
            await self.finish(claim, result, observation)
        except Exception as exc:
            code = exc.code if isinstance(exc, FleetError) else "FLEET_OPERATION_FAILED"
            # Never emit exception text: transport errors can contain credentials.
            logger.warning(
                "fleet_operation_failed", extra={"operation_id": str(claim.id), "code": code}
            )
            await self.finish(
                claim, {}, unknown(code.upper()) if claim.kind == "CHECK" else None, code
            )
        return True

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                await self.tick()
            except Exception:
                logger.error("fleet_worker_cycle_failed")
            try:
                await asyncio.wait_for(stop.wait(), timeout=5)
            except TimeoutError:
                pass


async def main() -> None:
    from prettylisavpn.client_vpn.worker import ClientVpnWorker
    from prettylisavpn.fleet.managed import ManagedVpnMethod
    from prettylisavpn.fleet.ssh import SshTransport
    from prettylisavpn.fleet.wireguard import WireGuardMethod

    settings = Settings()
    if not settings.fleet_enabled:
        raise SystemExit("Fleet is disabled")
    configure_logging(settings.log_level)
    postgres = Postgres(settings)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(signum, stop.set)
    transport = None
    try:
        transport = SshTransport.from_file(settings.fleet_inventory_path)
        method = WireGuardMethod(transport)
        managed = ManagedVpnMethod(transport, settings.managed_vpn_secret)
        methods: dict[str, VpnMethod] = {"wireguard": method}
        if settings.managed_vpn_secret is not None:
            methods["managed"] = managed
        async with asyncio.TaskGroup() as group:
            group.create_task(FleetWorker(postgres, methods, settings).run(stop))
            group.create_task(
                ClientVpnWorker(
                    postgres,
                    method,
                    enabled=settings.client_vpn_enabled,
                    managed_method=managed,
                    managed_enabled=settings.managed_vpn_enabled,
                ).run(stop)
            )
    finally:
        if transport is not None:
            await transport.close()
        await postgres.close()


if __name__ == "__main__":
    asyncio.run(main())
