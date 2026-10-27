"""Short node leases survive API/worker failures safely and share fleet node locks."""

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import or_, select, update

from prettylisavpn.auth.session_service import AccessIdentity
from prettylisavpn.client_vpn.domain import HEARTBEAT_TIMEOUT, NODE_TTL_SECONDS
from prettylisavpn.client_vpn.model import ClientLeaseRecord
from prettylisavpn.client_vpn.service import principals_valid
from prettylisavpn.connections import Postgres
from prettylisavpn.fleet.domain import Access, FleetError, Node, VpnMethod
from prettylisavpn.fleet.model import FleetNodeRecord
from prettylisavpn.fleet.service import node_value
from prettylisavpn.subscriptions.domain import SubscriptionPlan
from prettylisavpn.subscriptions.repository import SubscriptionRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Claim:
    id: UUID
    token: UUID
    node: Node
    access: Access
    revoke: bool


class ClientVpnWorker:
    def __init__(self, postgres: Postgres, method: VpnMethod, *, enabled: bool = True) -> None:
        self.postgres, self.method = postgres, method
        self.enabled = enabled

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
                node = await session.scalar(
                    select(FleetNodeRecord)
                    .where(
                        FleetNodeRecord.id == row.node_id,
                        or_(FleetNodeRecord.lock_until.is_(None), FleetNodeRecord.lock_until < now),
                    )
                    .with_for_update(skip_locked=True)
                )
                if node is None:
                    continue
                identity = AccessIdentity(row.user_id, row.device_id, row.auth_session_id)
                valid = self.enabled and await principals_valid(session, identity, now)
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
                    or (row.is_free and not node.is_available_for_free)
                ):
                    row.status, row.code = "REVOKING", "VPN_ACCESS_ENDED"
                elif row.expires_at <= now:
                    row.status, row.code = "REVOKING", "VPN_SESSION_EXPIRED"
                elif row.heartbeat_at + timedelta(seconds=HEARTBEAT_TIMEOUT) <= now:
                    row.status, row.code = "REVOKING", "VPN_CLIENT_LOST"
                revoke = row.status == "REVOKING"
                token = uuid4()
                row.claim_token, row.claim_until = token, now + timedelta(seconds=60)
                node.lock_owner, node.lock_until = token, row.claim_until
                if not revoke and row.activated_at is None:
                    # Reserve billable time BEFORE a possibly ambiguous external mutation.
                    row.activated_at = now
                return Claim(
                    row.id,
                    token,
                    node_value(node),
                    Access(
                        id=row.id,
                        public_key=row.public_key,
                        address=row.address,
                        expires_at=min(row.expires_at, now + timedelta(seconds=NODE_TTL_SECONDS)),
                        purpose="client",
                    ),
                    revoke,
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
            async with asyncio.timeout(25):
                if claim.revoke:
                    success = await self.method.revoke_access(claim.node, claim.access)
                else:
                    await self.method.grant_access(claim.node, claim.access)
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
