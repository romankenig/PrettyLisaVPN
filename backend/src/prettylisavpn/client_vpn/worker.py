"""Short node leases survive API/worker failures safely and share fleet node locks."""

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from ipaddress import IPv4Address
from uuid import UUID, uuid4

from sqlalchemy import or_, select, update

from prettylisavpn.auth.session_service import AccessIdentity
from prettylisavpn.client_vpn.domain import NODE_TTL_SECONDS, SETUP_TIMEOUT_SECONDS
from prettylisavpn.client_vpn.methods import MANAGED_METHODS, base_method
from prettylisavpn.client_vpn.model import ClientLeaseRecord
from prettylisavpn.client_vpn.quota import ClientQuotaRepository
from prettylisavpn.client_vpn.service import principals_valid
from prettylisavpn.connections import Postgres
from prettylisavpn.fleet.domain import (
    Access,
    FleetError,
    ManagedAccess,
    Node,
    RelayAccess,
    VpnMethod,
)
from prettylisavpn.fleet.model import FleetMethodRecord, FleetNodeRecord, FleetOperationRecord
from prettylisavpn.fleet.service import node_value
from prettylisavpn.subscriptions.domain import SubscriptionPlan
from prettylisavpn.subscriptions.repository import SubscriptionRepository
from prettylisavpn.users.model import UserRecord

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Claim:
    id: UUID
    token: UUID
    node: Node
    access: Access
    revoke: bool
    relay: Node | None = None
    relay_access: RelayAccess | None = None
    managed: bool = False


class ClientVpnWorker:
    def __init__(
        self,
        postgres: Postgres,
        method: VpnMethod,
        *,
        enabled: bool = True,
        managed_method: VpnMethod | None = None,
        managed_enabled: bool = False,
    ) -> None:
        self.postgres, self.method = postgres, method
        self.enabled = enabled
        self.managed_method, self.managed_enabled = managed_method, managed_enabled

    async def claim(self, now: datetime) -> Claim | None:
        async with self.postgres.session() as session, session.begin():
            # Small batches prevent a locked node from starving other nodes.
            rows = (
                await session.scalars(
                    select(ClientLeaseRecord)
                    .where(
                        ClientLeaseRecord.removed_at.is_(None),
                        ClientLeaseRecord.next_attempt_at <= now,
                        or_(
                            ClientLeaseRecord.claim_until.is_(None),
                            ClientLeaseRecord.claim_until < now,
                        ),
                    )
                    .order_by(ClientLeaseRecord.next_attempt_at)
                    .with_for_update(skip_locked=True)
                    .limit(30)
                )
            ).all()
            for row in rows:
                # Admission and every extension serialize on the same account.
                # Skip busy accounts so one connect cannot stall all node grants.
                account = await session.scalar(
                    select(UserRecord)
                    .where(UserRecord.id == row.user_id)
                    .with_for_update(skip_locked=True)
                )
                if account is None:
                    continue
                identifiers = {row.node_id} | ({row.relay_node_id} if row.relay_node_id else set())
                locked = (
                    await session.scalars(
                        select(FleetNodeRecord)
                        .where(FleetNodeRecord.id.in_(identifiers))
                        .order_by(FleetNodeRecord.id)
                        .with_for_update(skip_locked=True)
                    )
                ).all()
                if len(locked) != len(identifiers):
                    continue
                shared_checks: set[UUID] = set()
                blocked = False
                for locked_node in locked:
                    if locked_node.lock_until is None or locked_node.lock_until < now:
                        continue
                    if bool(
                        await session.scalar(
                            select(FleetOperationRecord.id).where(
                                FleetOperationRecord.claim_token == locked_node.lock_owner,
                                FleetOperationRecord.kind == "CHECK",
                                FleetOperationRecord.status == "RUNNING",
                                FleetOperationRecord.lease_until > now,
                                or_(
                                    FleetOperationRecord.node_id == locked_node.id,
                                    FleetOperationRecord.source_id == locked_node.id,
                                ),
                            )
                        )
                    ):
                        shared_checks.add(locked_node.id)
                    else:
                        blocked = True
                        break
                if blocked:
                    continue
                node = next(item for item in locked if item.id == row.node_id)
                relay = next((item for item in locked if item.id == row.relay_node_id), None)
                identity = AccessIdentity(row.user_id, row.device_id, row.auth_session_id)
                valid = self.enabled and await principals_valid(session, identity, now)
                is_managed = base_method(row.method) != "wireguard"
                if is_managed and not self.managed_enabled:
                    valid = False
                subscription = await SubscriptionRepository(session).get_by_user_id(row.user_id)
                if not row.is_free and subscription:
                    if subscription.effective_plan(now) != SubscriptionPlan.FREE:
                        assert subscription.current_period_end
                        row.expires_at = subscription.current_period_end
                    else:
                        valid = False
                if not subscription:
                    valid = False
                if (
                    not valid
                    or not node.enabled
                    or node.group == "INTERMEDIATE"
                    or (relay is not None and (not relay.enabled or relay.group != "INTERMEDIATE"))
                    or (row.is_free and not node.is_available_for_free)
                ):
                    row.status, row.code = "REVOKING", "VPN_ACCESS_ENDED"
                elif row.expires_at <= now:
                    row.status, row.code = "REVOKING", "VPN_SESSION_EXPIRED"
                elif (
                    row.status in ("PROVISIONING", "READY")
                    and row.verified_at is None
                    and row.created_at + timedelta(seconds=SETUP_TIMEOUT_SECONDS) <= now
                ):
                    row.status, row.code = "REVOKING", "VPN_SETUP_TIMEOUT"
                # A sleeping device cannot reliably run HTTP heartbeats. Once
                # provisioned, access belongs to the authenticated session until
                # explicit revocation or its entitlement/auth deadline. The worker
                # still renews short node grants and rechecks every principal.
                if row.is_free and row.status != "REVOKING":
                    if row.quota_reserved_until is None:
                        # Legacy grants were already limited to NODE_TTL_SECONDS.
                        # Do not release any part of a possibly outstanding grant.
                        row.quota_reserved_until = min(
                            row.expires_at, now + timedelta(seconds=NODE_TTL_SECONDS)
                        )
                        await session.flush()
                    elif row.quota_reserved_until <= now:
                        row.status, row.code = "REVOKING", "VPN_RESERVATION_EXPIRED"
                    if row.status != "REVOKING":
                        available = await ClientQuotaRepository(session).remaining_free_seconds(
                            row.user_id, now
                        )
                        row.quota_reserved_until = min(
                            row.expires_at,
                            max(
                                row.quota_reserved_until,
                                min(
                                    now + timedelta(seconds=NODE_TTL_SECONDS),
                                    row.quota_reserved_until + timedelta(seconds=available),
                                ),
                            ),
                        )
                revoke = row.status == "REVOKING"
                grant_until = min(row.expires_at, now + timedelta(seconds=NODE_TTL_SECONDS))
                if row.is_free and row.quota_reserved_until:
                    grant_until = min(grant_until, row.quota_reserved_until)
                token = uuid4()
                row.claim_token, row.claim_until = token, now + timedelta(seconds=60)
                # A monitoring namespace can coexist with customer grants. Never
                # replace its lock; CONFIGURE and competing client claims remain
                # exclusive. Fleet claims also exclude in-flight client rows.
                for locked_node in locked:
                    if locked_node.id not in shared_checks:
                        locked_node.lock_owner, locked_node.lock_until = token, row.claim_until
                if not revoke and row.activated_at is None:
                    # Reserve billable time BEFORE a possibly ambiguous external mutation.
                    row.activated_at = now
                relay_access = None
                if relay is not None:
                    method = await session.get(
                        FleetMethodRecord, (node.id, "managed" if is_managed else "wireguard")
                    )
                    assert method is not None and row.relay_port is not None
                    relay_access = RelayAccess(
                        id=row.id,
                        listen_port=row.relay_port,
                        target_host=IPv4Address(node.host),
                        target_port=row.engine_port
                        if is_managed and row.engine_port
                        else int(str(method.configuration["listen_port"])),
                        expires_at=grant_until,
                        protocol=MANAGED_METHODS[base_method(row.method)].network
                        if is_managed
                        else "udp",
                    )
                access = Access(
                    id=row.id,
                    public_key=row.public_key,
                    address=row.address or "",
                    expires_at=grant_until,
                    purpose="client",
                )
                if is_managed:
                    assert row.engine_port is not None
                    access = ManagedAccess(
                        **access.model_dump(), method=row.method, listen_port=row.engine_port
                    )
                return Claim(
                    row.id,
                    token,
                    node_value(node),
                    access,
                    revoke,
                    node_value(relay) if relay else None,
                    relay_access,
                    is_managed,
                )
        return None

    async def finish(self, claim: Claim, success: bool, code: str | None = None) -> bool:
        now = datetime.now(UTC)
        async with self.postgres.session() as session, session.begin():
            row = await session.scalar(
                select(ClientLeaseRecord).where(ClientLeaseRecord.id == claim.id).with_for_update()
            )
            if row is None or row.claim_token != claim.token:
                return False
            if success and claim.revoke:
                row.status, row.removed_at = "CLOSED", now
            elif success and row.status == "PROVISIONING":
                row.status, row.code = "READY", None
            elif not success:
                row.code = code or "VPN_NODE_UNAVAILABLE"
            row.claim_token, row.claim_until = None, None
            row.next_attempt_at = now + timedelta(
                seconds=0 if row.status == "REVOKING" and success else 10 if not success else 30
            )
            await session.execute(
                update(FleetNodeRecord)
                .where(FleetNodeRecord.lock_owner == claim.token)
                .values(lock_owner=None, lock_until=None)
            )
            return True

    async def tick(self) -> bool:
        claim = await self.claim(datetime.now(UTC))
        if claim is None:
            return False
        try:
            method = self.managed_method if claim.managed else self.method
            if method is None:
                raise FleetError("VPN_ENGINE_UNAVAILABLE", 503)
            async with asyncio.timeout(25):
                if claim.revoke:
                    if claim.relay and claim.relay_access:
                        # Always attempt both removals, even when one host is unreachable.
                        results = await asyncio.gather(
                            method.revoke_relay(claim.relay, claim.relay_access),
                            method.revoke_access(claim.node, claim.access),
                            return_exceptions=True,
                        )
                        success = all(result is True for result in results)
                    else:
                        success = await method.revoke_access(claim.node, claim.access)
                else:
                    await method.grant_access(claim.node, claim.access)
                    if claim.relay and claim.relay_access:
                        await method.grant_relay(claim.relay, claim.relay_access)
                    success = True
            await self.finish(claim, success)
        except Exception as error:
            await self.finish(
                claim,
                False,
                error.code if isinstance(error, FleetError) else "VPN_NODE_UNAVAILABLE",
            )
        return True

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                if await self.tick():
                    continue
            except Exception:
                logger.warning("client_vpn_worker_cycle_failed")
            try:
                await asyncio.wait_for(stop.wait(), 2)
            except TimeoutError:
                pass
