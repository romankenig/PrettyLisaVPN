"""Independent daily method checks; fixed protocol, random unused exit/relay routes."""

import asyncio
import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import delete, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert

from prettylisavpn.client_vpn.methods import METHODS, base_method
from prettylisavpn.client_vpn.model import ClientLeaseRecord
from prettylisavpn.connections import Postgres
from prettylisavpn.fleet.daily_checks import finish_attempt
from prettylisavpn.fleet.domain import Node, Observation, proxy_address_supported
from prettylisavpn.fleet.managed import ManagedVpnMethod
from prettylisavpn.fleet.method_check_model import MethodCheckRecord
from prettylisavpn.fleet.method_checks import Route, choose_route
from prettylisavpn.fleet.model import FleetMethodRecord, FleetNodeRecord
from prettylisavpn.fleet.service import node_value
from prettylisavpn.fleet.service_checks import daily_slot
from prettylisavpn.fleet.ubuntu.service_probe import discover
from prettylisavpn.fleet.wireguard import WireGuardMethod
from prettylisavpn.product_analytics.domain import day
from prettylisavpn.traffic.model import TrafficServiceRecord

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MethodClaim:
    method: str
    day: date
    token: UUID
    source: Node
    target: Node
    relay: Node | None
    relay_port: int | None
    domains: list[str]
    at: datetime
    deadline: datetime


class MethodCheckWorker:
    def __init__(self, postgres: Postgres, wireguard: WireGuardMethod, managed: ManagedVpnMethod):
        self.postgres, self.wireguard, self.managed = postgres, wireguard, managed

    async def schedule(self, now: datetime) -> None:
        async with self.postgres.session() as session, session.begin():
            if not await session.scalar(text("SELECT pg_try_advisory_xact_lock(860120050)")):
                return
            known = set(await session.scalars(select(MethodCheckRecord.method).distinct()))
            for index, method in enumerate(sorted(METHODS)):
                scheduled = (
                    now + timedelta(seconds=30 + index * 60)
                    if method not in known
                    else daily_slot("method:" + method, day(now))
                )
                await session.execute(
                    insert(MethodCheckRecord)
                    .values(
                        method=method,
                        day=day(now),
                        scheduled_at=scheduled,
                        next_attempt_at=scheduled,
                        attempts=[],
                    )
                    .on_conflict_do_nothing()
                )
            await session.execute(
                delete(MethodCheckRecord).where(
                    MethodCheckRecord.day < day(now) - timedelta(days=30)
                )
            )

    async def claim(self, now: datetime) -> MethodClaim | None:
        async with self.postgres.session() as session, session.begin():
            job = await session.scalar(
                select(MethodCheckRecord)
                .where(
                    MethodCheckRecord.finished_at.is_(None),
                    MethodCheckRecord.next_attempt_at <= now,
                    or_(
                        MethodCheckRecord.claim_until.is_(None), MethodCheckRecord.claim_until < now
                    ),
                )
                .order_by(MethodCheckRecord.next_attempt_at)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if job is None:
                return None
            if (
                job.method not in METHODS
                or job.day < day(now)
                or len(job.attempts) >= 30
                or (job.started_at and now - job.started_at >= timedelta(minutes=30))
            ):
                job.finished_at = now
                job.score = 0 if any(a.get("tested") for a in job.attempts) else None
                job.code = "UNAVAILABLE" if job.score == 0 else "NOT_OBSERVED"
                return None
            if job.reserved_until and job.reserved_until > now:
                # A crashed/uncertain relay attempt keeps its port until the node TTL expires.
                job.next_attempt_at = job.reserved_until
                return None
            nodes = list(
                await session.scalars(select(FleetNodeRecord).where(FleetNodeRecord.enabled))
            )
            configurations = list(
                await session.scalars(
                    select(FleetMethodRecord).where(
                        FleetMethodRecord.state == "READY",
                        FleetMethodRecord.configured_at.is_not(None),
                    )
                )
            )
            by_id = {n.id: n for n in nodes}
            configured = {(c.node_id, c.method): c for c in configurations}
            native = base_method(job.method)
            exits = []
            for node in nodes:
                config = configured.get(
                    (node.id, "wireguard" if native == "wireguard" else "managed")
                )
                if node.group == "INTERMEDIATE" or not config or not config.public_key:
                    continue
                if native != "wireguard" and not self.managed.key:
                    continue
                if native == "https_proxy" and not proxy_address_supported(
                    config.configuration.get("proxy_host"), allow_ip=True
                ):
                    continue
                exits.append(node)
            relays = [
                n for n in nodes if n.group == "INTERMEDIATE" and (n.id, "wireguard") in configured
            ]
            roster: list[Route] = (
                [(n.id, r.id) for n in exits for r in relays]
                if job.method.endswith("_relay")
                else [(n.id, None) for n in exits]
            )
            candidate = choose_route(roster, job.attempts)
            services = list(
                await session.scalars(
                    select(TrafficServiceRecord).where(TrafficServiceRecord.enabled)
                )
            )
            if candidate is None or not services:
                job.finished_at = now
                job.score = 0 if roster and any(a.get("tested") for a in job.attempts) else None
                job.code = (
                    "UNAVAILABLE"
                    if job.score == 0
                    else "NO_PROBE_ROUTE"
                    if not roster
                    else "NOT_OBSERVED"
                )
                return None
            target_id, relay_id = candidate
            route_ids = {target_id} | ({relay_id} if relay_id else set())
            busy = set(
                await session.scalars(
                    select(ClientLeaseRecord.node_id).where(ClientLeaseRecord.claim_until > now)
                )
            )
            busy.update(
                await session.scalars(
                    select(ClientLeaseRecord.relay_node_id).where(
                        ClientLeaseRecord.claim_until > now
                    )
                )
            )
            available = [
                n
                for n in nodes
                if n.id not in busy and (n.lock_until is None or n.lock_until < now)
            ]
            sources = [
                n
                for n in available
                if n.id not in route_ids and any(c.node_id == n.id for c in configurations)
            ]
            if not sources or not route_ids.issubset({n.id for n in available}):
                job.next_attempt_at = now + timedelta(seconds=10)
                return None
            source = secrets.choice(sources)
            identifiers = route_ids | {source.id}
            locked = list(
                await session.scalars(
                    select(FleetNodeRecord)
                    .where(FleetNodeRecord.id.in_(identifiers))
                    .order_by(FleetNodeRecord.id)
                    .with_for_update(skip_locked=True)
                    .execution_options(populate_existing=True)
                )
            )
            if len(locked) != len(identifiers) or any(
                n.lock_until and n.lock_until > now for n in locked
            ):
                job.next_attempt_at = now + timedelta(seconds=10)
                return None
            relay_port = None
            if relay_id:
                # Admission holds the same node row lock and excludes these reservations.
                ports = set(
                    await session.scalars(
                        select(ClientLeaseRecord.relay_port).where(
                            ClientLeaseRecord.relay_node_id == relay_id,
                            ClientLeaseRecord.removed_at.is_(None),
                        )
                    )
                )
                ports.update(
                    await session.scalars(
                        select(MethodCheckRecord.relay_port).where(
                            MethodCheckRecord.relay_node_id == relay_id,
                            MethodCheckRecord.reserved_until > now,
                        )
                    )
                )
                relay_port = next((p for p in range(29999, 19999, -1) if p not in ports), None)
                if relay_port is None:
                    job.next_attempt_at = now + timedelta(seconds=10)
                    return None
            token = uuid4()
            job.started_at = job.started_at or now
            job.claim_token, job.claim_until = token, now + timedelta(seconds=150)
            job.next_attempt_at = now + timedelta(minutes=1)
            job.relay_node_id, job.relay_port = relay_id, relay_port
            job.reserved_until = now + timedelta(minutes=5) if relay_id else None
            job.attempts = [
                *job.attempts,
                {
                    "node": str(target_id),
                    "relay": str(relay_id) if relay_id else None,
                    "at": now.isoformat(),
                    "code": "INTERRUPTED",
                    "tested": False,
                },
            ]
            for node in locked:
                node.lock_owner, node.lock_until = token, job.claim_until
            return MethodClaim(
                job.method,
                job.day,
                token,
                node_value(source),
                node_value(by_id[target_id]),
                node_value(by_id[relay_id]) if relay_id else None,
                relay_port,
                secrets.choice(services).domains,
                now,
                job.started_at + timedelta(minutes=30),
            )

    async def tick(self) -> None:
        now = datetime.now(UTC)
        await self.schedule(now)
        claim = await self.claim(now)
        if claim is None:
            return
        result: Observation | None = None
        code = "SERVICE_SAMPLE_UNAVAILABLE"
        try:
            async with asyncio.timeout(
                min(120, (claim.deadline - datetime.now(UTC)).total_seconds())
            ):
                url = await asyncio.to_thread(discover, claim.domains)
                if url:
                    if base_method(claim.method) == "wireguard":
                        result = await self.wireguard.probe(
                            claim.source,
                            claim.target,
                            claim.token,
                            url,
                            claim.domains,
                            relay=claim.relay,
                            relay_port=claim.relay_port,
                        )
                    else:
                        result = await self.managed.probe(
                            claim.source,
                            claim.target,
                            claim.token,
                            url,
                            claim.domains,
                            claim.method,
                            relay=claim.relay,
                            relay_port=claim.relay_port,
                        )
                    code = result.code
        except Exception:
            code = "METHOD_PROBE_INTERRUPTED"
        async with self.postgres.session() as session, session.begin():
            job = await session.get(
                MethodCheckRecord, (claim.method, claim.day), with_for_update=True
            )
            if job and job.claim_token == claim.token:
                finish_attempt(job, result, code, claim.at, datetime.now(UTC), claim.deadline)
                if result is not None and result.cleanup_confirmed:
                    job.reserved_until = None
            await session.execute(
                update(FleetNodeRecord)
                .where(FleetNodeRecord.lock_owner == claim.token)
                .values(lock_owner=None, lock_until=None)
            )

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                await self.tick()
            except Exception:
                logger.error("method_check_cycle_failed")
            try:
                await asyncio.wait_for(stop.wait(), timeout=5)
            except TimeoutError:
                pass
