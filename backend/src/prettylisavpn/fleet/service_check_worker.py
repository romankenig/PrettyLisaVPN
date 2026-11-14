"""Durable once-daily per-service checks, jittered schedule and minute retries."""

import asyncio
import logging
import secrets
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import delete, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert

from prettylisavpn.client_vpn.methods import MANAGED_METHODS
from prettylisavpn.client_vpn.model import ClientLeaseRecord
from prettylisavpn.connections import Postgres
from prettylisavpn.fleet.domain import Node, Observation
from prettylisavpn.fleet.managed import ManagedVpnMethod
from prettylisavpn.fleet.model import FleetMethodRecord, FleetNodeRecord
from prettylisavpn.fleet.service import node_value
from prettylisavpn.fleet.service_check_model import ServiceCheckRecord
from prettylisavpn.fleet.service_checks import assessment_score, choose_candidate, daily_slot
from prettylisavpn.fleet.ubuntu.service_probe import discover
from prettylisavpn.fleet.wireguard import WireGuardMethod
from prettylisavpn.product_analytics.domain import day
from prettylisavpn.traffic.model import TrafficServiceRecord

logger = logging.getLogger(__name__)


class ServiceCheckWorker:
    def __init__(self, postgres: Postgres, wireguard: WireGuardMethod, managed: ManagedVpnMethod):
        self.postgres, self.wireguard, self.managed = postgres, wireguard, managed

    async def schedule(self, now: datetime) -> None:
        async with self.postgres.session() as session, session.begin():
            if not await session.scalar(text("SELECT pg_try_advisory_xact_lock(860120048)")):
                return
            services = (
                await session.scalars(
                    select(TrafficServiceRecord)
                    .where(TrafficServiceRecord.enabled)
                    .order_by(TrafficServiceRecord.id)
                )
            ).all()
            known = set(await session.scalars(select(ServiceCheckRecord.service_id).distinct()))
            for index, service in enumerate(services):
                # Bootstrap every newly enabled service once; spread initial load too.
                scheduled = (
                    now + timedelta(seconds=index * 60)
                    if service.id not in known
                    else daily_slot(service.id, day(now))
                )
                await session.execute(
                    insert(ServiceCheckRecord)
                    .values(
                        service_id=service.id,
                        day=day(now),
                        scheduled_at=scheduled,
                        next_attempt_at=scheduled,
                        attempts=[],
                    )
                    .on_conflict_do_nothing()
                )
            await session.execute(
                delete(ServiceCheckRecord).where(
                    ServiceCheckRecord.day < day(now) - timedelta(days=30)
                )
            )

    async def claim(
        self, now: datetime
    ) -> tuple[UUID, date, UUID, Node, Node, str, list[str], datetime, datetime] | None:
        async with self.postgres.session() as session, session.begin():
            job = await session.scalar(
                select(ServiceCheckRecord)
                .where(
                    ServiceCheckRecord.finished_at.is_(None),
                    ServiceCheckRecord.next_attempt_at <= now,
                    or_(
                        ServiceCheckRecord.claim_until.is_(None),
                        ServiceCheckRecord.claim_until < now,
                    ),
                )
                .order_by(ServiceCheckRecord.next_attempt_at)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if job is None:
                return None
            service = await session.get(TrafficServiceRecord, job.service_id)
            if (
                not service
                or not service.enabled
                or (job.started_at and now - job.started_at >= timedelta(minutes=30))
                or len(job.attempts) >= 30
                or job.day < day(now)
            ):
                job.finished_at = now
                job.score = 0 if any(a.get("tested") for a in job.attempts) else None
                job.code = "UNAVAILABLE" if job.score == 0 else "NOT_OBSERVED"
                return None
            nodes = (
                await session.scalars(
                    select(FleetNodeRecord)
                    .where(FleetNodeRecord.enabled)
                    .order_by(FleetNodeRecord.id)
                )
            ).all()
            methods = (
                await session.scalars(
                    select(FleetMethodRecord).where(
                        FleetMethodRecord.configured_at.is_not(None),
                        FleetMethodRecord.state == "READY",
                    )
                )
            ).all()
            by_id = {n.id: n for n in nodes}
            roster: list[tuple[UUID, str]] = []
            for configured in methods:
                node = by_id.get(configured.node_id)
                if not node or node.group == "INTERMEDIATE":
                    continue
                names = (
                    ["wireguard"]
                    if configured.method == "wireguard"
                    else list(MANAGED_METHODS)
                    if configured.method == "managed" and self.managed.key
                    else []
                )
                roster.extend((node.id, name) for name in names)
            candidate = choose_candidate(roster, job.attempts)
            if candidate is None:
                # An empty configured fleet is missing evidence, not service failure.
                job.finished_at, job.score = (
                    now,
                    0 if roster and any(a.get("tested") for a in job.attempts) else None,
                )
                job.code = "UNAVAILABLE" if job.score == 0 else "NO_PROBE_ROUTE"
                return None
            target_id, method = candidate
            busy_clients = set(
                await session.scalars(
                    select(ClientLeaseRecord.node_id).where(ClientLeaseRecord.claim_until > now)
                )
            )
            busy_clients.update(
                await session.scalars(
                    select(ClientLeaseRecord.relay_node_id).where(
                        ClientLeaseRecord.claim_until > now
                    )
                )
            )
            available = [
                n
                for n in nodes
                if (n.lock_until is None or n.lock_until < now) and n.id not in busy_clients
            ]
            sources = [
                n
                for n in available
                if n.id != target_id and any(m.node_id == n.id for m in methods)
            ]
            target = by_id[target_id]
            if not sources or target not in available:
                job.next_attempt_at = now + timedelta(seconds=10)
                return None
            source = secrets.choice(sources)
            locked = (
                await session.scalars(
                    select(FleetNodeRecord)
                    .where(FleetNodeRecord.id.in_([target.id, source.id]))
                    .order_by(FleetNodeRecord.id)
                    .with_for_update(skip_locked=True)
                    .execution_options(populate_existing=True)
                )
            ).all()
            if len(locked) != 2 or any(
                node.lock_until is not None and node.lock_until > now for node in locked
            ):
                job.next_attempt_at = now + timedelta(seconds=10)
                return None
            token = uuid4()
            job.started_at = job.started_at or now
            job.claim_token, job.claim_until = token, now + timedelta(seconds=150)
            job.next_attempt_at = now + timedelta(minutes=1)
            job.attempts = [
                *job.attempts,
                {
                    "node": str(target_id),
                    "method": method,
                    "at": now.isoformat(),
                    "code": "INTERRUPTED",
                    "tested": False,
                },
            ]
            for node in (target, source):
                node.lock_owner, node.lock_until = token, job.claim_until
            return (
                job.service_id,
                job.day,
                token,
                node_value(source),
                node_value(target),
                method,
                service.domains,
                now,
                job.started_at + timedelta(minutes=30),
            )

    async def tick(self) -> None:
        now = datetime.now(UTC)
        await self.schedule(now)
        claim = await self.claim(now)
        if claim is None:
            return
        service_id, on, token, source, target, method, domains, attempt_at, deadline = claim
        result: Observation | None = None
        code = "SERVICE_SAMPLE_UNAVAILABLE"
        try:
            async with asyncio.timeout(min(120, (deadline - datetime.now(UTC)).total_seconds())):
                url = await asyncio.to_thread(discover, domains)
                if url:
                    result = await (
                        self.wireguard.probe(source, target, token, url, domains)
                        if method == "wireguard"
                        else self.managed.probe(source, target, token, url, domains, method)
                    )
                    code = result.code
        except Exception:
            code = "SERVICE_PROBE_INTERRUPTED"
        async with self.postgres.session() as session, session.begin():
            job = await session.get(ServiceCheckRecord, (service_id, on), with_for_update=True)
            if job and job.claim_token == token:
                finished = datetime.now(UTC)
                tested = (
                    result is not None
                    and result.mode == "SYNTHETIC"
                    and result.code
                    in {
                        "SERVICE_CHECK_PASSED",
                        "SERVICE_HTTP_FAILED",
                        "HANDSHAKE_FAILED",
                        "DNS_FAILED",
                        "HTTPS_FAILED",
                        "EGRESS_IP_MISMATCH",
                    }
                )
                job.attempts = [
                    *job.attempts[:-1],
                    {**job.attempts[-1], "code": code, "tested": tested},
                ]
                job.code, job.claim_token, job.claim_until = code, None, None
                if finished >= deadline:
                    job.score = 0 if any(a.get("tested") for a in job.attempts) else None
                    job.code = "UNAVAILABLE" if job.score == 0 else "NOT_OBSERVED"
                    job.finished_at = finished
                elif (
                    result is not None
                    and result.status == "HEALTHY"
                    and result.code == "SERVICE_CHECK_PASSED"
                    and result.cleanup_confirmed
                ):
                    assert job.started_at is not None
                    job.score = assessment_score(job.started_at, attempt_at, True)
                    job.finished_at = finished
                elif len(job.attempts) >= 30:
                    job.score = 0 if any(a.get("tested") for a in job.attempts) else None
                    job.finished_at = finished
            await session.execute(
                update(FleetNodeRecord)
                .where(FleetNodeRecord.lock_owner == token)
                .values(lock_owner=None, lock_until=None)
            )

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                await self.tick()
            except Exception:
                logger.error("service_check_cycle_failed")
            try:
                await asyncio.wait_for(stop.wait(), timeout=5)
            except TimeoutError:
                pass
