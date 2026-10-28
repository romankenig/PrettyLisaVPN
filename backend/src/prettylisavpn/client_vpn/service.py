"""Authenticated, account-serialized reservations. SSH belongs exclusively to the worker."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from prettylisavpn.auth.session_service import AccessIdentity, AuthenticatedSessionHandler
from prettylisavpn.auth_sessions.model import AuthSessionRecord
from prettylisavpn.client_vpn.domain import (
    HEARTBEAT_SECONDS,
    ConnectRequest,
    allocate_address,
    deadline,
)
from prettylisavpn.client_vpn.model import ClientLeaseRecord
from prettylisavpn.client_vpn.quota import ClientQuotaRepository
from prettylisavpn.config import Settings
from prettylisavpn.connections import Postgres
from prettylisavpn.devices.domain import DevicePlatform, DeviceStatus
from prettylisavpn.devices.model import DeviceRecord
from prettylisavpn.fleet.domain import FleetError
from prettylisavpn.fleet.model import FleetMethodRecord, FleetNodeRecord
from prettylisavpn.fleet.service import FleetService
from prettylisavpn.subscriptions.domain import SubscriptionPlan
from prettylisavpn.subscriptions.repository import SubscriptionRepository
from prettylisavpn.users.domain import UserStatus
from prettylisavpn.users.model import UserRecord


async def principals_valid(session: AsyncSession, identity: AccessIdentity, now: datetime) -> bool:
    user = await session.get(UserRecord, identity.user_id)
    device = await session.get(DeviceRecord, identity.device_id)
    auth = await session.get(AuthSessionRecord, identity.session_id)
    return bool(
        user
        and user.status == UserStatus.ACTIVE
        and device
        and device.user_id == identity.user_id
        and device.status == DeviceStatus.ACTIVE
        and device.platform in (DevicePlatform.ANDROID, DevicePlatform.WINDOWS)
        and auth
        and auth.user_id == identity.user_id
        and auth.device_id == identity.device_id
        and auth.revoked_at is None
        and auth.expires_at > now
    )


async def view(session: AsyncSession, row: ClientLeaseRecord) -> dict[str, Any]:
    node = await session.get(FleetNodeRecord, row.node_id)
    method = await session.get(FleetMethodRecord, (row.node_id, "wireguard"))
    assert node and method
    relay = await session.get(FleetNodeRecord, row.relay_node_id) if row.relay_node_id else None
    result: dict[str, Any] = {
        "id": str(row.id),
        "status": row.status,
        "code": row.code,
        "country": node.country_code,
        "method": row.method,
        "intermediate": {"name": relay.name, "country": relay.country_code} if relay else None,
        "expires_at": row.expires_at,
        "heartbeat_seconds": HEARTBEAT_SECONDS,
        "heartbeat_required": False,
        "removed_at": row.removed_at,
    }
    if row.status == "READY":
        result["configuration"] = {
            "address": row.address,
            "server_public_key": method.public_key,
            "endpoint": f"{relay.host}:{row.relay_port}"
            if relay
            else f"{node.host}:{method.configuration['listen_port']}",
            "dns": ["1.1.1.1", "9.9.9.9"],
            "allowed_ips": ["0.0.0.0/0", "::/0"],
            "mtu": method.configuration["mtu"],
            "persistent_keepalive": 25,
            "expected_egress_ips": node.expected_egress_ips,
        }
    return result


class ClientVpnService:
    def __init__(
        self,
        postgres: Postgres,
        auth: AuthenticatedSessionHandler,
        settings: Settings,
        fleet: FleetService,
    ) -> None:
        self.postgres, self.auth, self.settings, self.fleet = postgres, auth, settings, fleet

    async def identity(self, token: str) -> AccessIdentity:
        if not self.settings.fleet_enabled:
            raise FleetError("VPN_UNAVAILABLE", 503)
        return await self.auth.authenticate(token)

    async def connect(self, token: str, data: ConnectRequest, request_id: UUID) -> dict[str, Any]:
        if not self.settings.client_vpn_enabled:
            raise FleetError("VPN_UNAVAILABLE", 503)
        identity = await self.identity(token)
        snapshot = await self.fleet.monitoring(days=1)
        candidates = sorted(
            (item for item in snapshot["nodes"] if item["available"]),
            key=lambda item: (-item["quality"], item["id"]),
        )
        now = datetime.now(UTC)
        async with self.postgres.session() as session, session.begin():
            await session.scalar(
                select(UserRecord).where(UserRecord.id == identity.user_id).with_for_update()
            )
            if not await principals_valid(session, identity, now):
                raise FleetError("ACCOUNT_UNAVAILABLE", 403)
            previous = await session.scalar(
                select(ClientLeaseRecord).where(
                    ClientLeaseRecord.user_id == identity.user_id,
                    ClientLeaseRecord.request_id == request_id,
                )
            )
            if previous:
                if (
                    previous.device_id != identity.device_id
                    or previous.public_key != data.public_key
                    or previous.country != data.country
                    or previous.method != data.method
                ):
                    raise FleetError("VPN_IDEMPOTENCY_CONFLICT", 409)
                return await view(session, previous)
            if await session.scalar(
                select(ClientLeaseRecord.id).where(
                    ClientLeaseRecord.device_id == identity.device_id,
                    ClientLeaseRecord.removed_at.is_(None),
                )
            ):
                raise FleetError("VPN_CLEANUP_PENDING", 409)
            if await session.scalar(
                select(ClientLeaseRecord.id).where(
                    ClientLeaseRecord.public_key == data.public_key,
                    ClientLeaseRecord.removed_at.is_(None),
                )
            ):
                raise FleetError("VPN_KEY_IN_USE", 409)
            subscription = await SubscriptionRepository(session).get_by_user_id(identity.user_id)
            if subscription is None:
                raise FleetError("ACCOUNT_UNAVAILABLE", 403)
            remaining = (
                await ClientQuotaRepository(session).remaining_free_seconds(identity.user_id, now)
                if subscription.effective_plan(now) == SubscriptionPlan.FREE
                else 0
            )
            is_free, expires = deadline(subscription, now, remaining)
            # Acquire the small candidate roster in UUID order. Exit/relay capacity
            # reservations and administrative group changes share these locks.
            locked = (
                await session.scalars(
                    select(FleetNodeRecord)
                    .where(FleetNodeRecord.id.in_([UUID(item["id"]) for item in candidates]))
                    .order_by(FleetNodeRecord.id)
                    .with_for_update()
                )
            ).all()
            nodes = {node.id: node for node in locked}
            relay: FleetNodeRecord | None = None
            relay_port: int | None = None
            if data.method == "wireguard_relay":
                for candidate in candidates:
                    intermediate = nodes[UUID(candidate["id"])]
                    if not intermediate.enabled or intermediate.group != "INTERMEDIATE":
                        continue
                    relay_method = await session.get(
                        FleetMethodRecord, (intermediate.id, "wireguard")
                    )
                    if not relay_method or relay_method.state != "READY":
                        continue
                    ports = set(
                        (
                            await session.scalars(
                                select(ClientLeaseRecord.relay_port).where(
                                    ClientLeaseRecord.relay_node_id == intermediate.id,
                                    ClientLeaseRecord.removed_at.is_(None),
                                )
                            )
                        ).all()
                    )
                    if len(ports) < intermediate.capacity:
                        relay_port = next(
                            (port for port in range(20000, 30000) if port not in ports), None
                        )
                        if relay_port is not None:
                            relay = intermediate
                            break
                if relay is None:
                    raise FleetError("VPN_NO_AVAILABLE_RELAY", 503)
            for candidate in candidates:
                node = nodes.get(UUID(candidate["id"]))
                if (
                    not node
                    or not node.enabled
                    or node.group == "INTERMEDIATE"
                    or (is_free and not node.is_available_for_free)
                    or (data.country != "AUTO" and node.country_code != data.country)
                ):
                    continue
                method = await session.get(FleetMethodRecord, (node.id, "wireguard"))
                if not method or method.state != "READY" or not method.public_key:
                    continue
                used = set(
                    (
                        await session.scalars(
                            select(ClientLeaseRecord.address).where(
                                ClientLeaseRecord.node_id == node.id,
                                ClientLeaseRecord.removed_at.is_(None),
                            )
                        )
                    ).all()
                )
                if len(used) >= node.capacity:
                    continue
                try:
                    address = allocate_address(method.configuration, used)
                except FleetError:
                    continue
                row = ClientLeaseRecord(
                    request_id=request_id,
                    user_id=identity.user_id,
                    device_id=identity.device_id,
                    auth_session_id=identity.session_id,
                    node_id=node.id,
                    method=data.method,
                    relay_node_id=relay.id if relay else None,
                    relay_port=relay_port,
                    country=data.country,
                    public_key=data.public_key,
                    address=address,
                    is_free=is_free,
                    created_at=now,
                    expires_at=expires,
                    heartbeat_at=now,
                    next_attempt_at=now,
                )
                session.add(row)
                await session.flush()
                return await view(session, row)
            raise FleetError("VPN_NO_AVAILABLE_NODE", 503)

    async def get(
        self,
        token: str,
        identifier: UUID | None = None,
        action: str = "get",
        observed_ip: str | None = None,
    ) -> dict[str, Any] | None:
        identity = await self.identity(token)
        now = datetime.now(UTC)
        async with self.postgres.session() as session, session.begin():
            query = select(ClientLeaseRecord).where(
                ClientLeaseRecord.user_id == identity.user_id,
                ClientLeaseRecord.device_id == identity.device_id,
            )
            query = (
                query.where(ClientLeaseRecord.id == identifier)
                if identifier
                else query.where(ClientLeaseRecord.removed_at.is_(None))
            )
            row = await session.scalar(query.with_for_update())
            if row is None:
                if identifier:
                    raise FleetError("VPN_SESSION_NOT_FOUND", 404)
                return None
            if action == "heartbeat" and row.status in ("PROVISIONING", "READY"):
                row.heartbeat_at = now
            if action == "revoke" and row.removed_at is None:
                row.status, row.next_attempt_at = "REVOKING", now
            if action == "probe":
                node = await session.get(FleetNodeRecord, row.node_id)
                return {
                    "verified": bool(
                        row.status == "READY"
                        and row.expires_at > now
                        and node
                        and observed_ip in node.expected_egress_ips
                    ),
                    "ip": observed_ip,
                }
            return await view(session, row)
