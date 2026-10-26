"""Fixtures for retained migration/account data; no VPN connection implementation."""

from datetime import UTC, datetime
from ipaddress import IPv4Address
from uuid import UUID, uuid4

from sqlalchemy import delete

from prettylisavpn.connections import Postgres
from prettylisavpn.devices.domain import DevicePlatform
from prettylisavpn.devices.repository import DeviceRepository
from prettylisavpn.devices.service import DeviceService
from prettylisavpn.legacy_vpn.enums import VpnNodeHealthStatus, VpnNodeProvider, VpnNodeStatus
from prettylisavpn.legacy_vpn.nodes import VpnNodeRecord
from prettylisavpn.subscriptions.repository import SubscriptionRepository
from prettylisavpn.users.model import UserRecord
from prettylisavpn.users.repository import UserRepository
from prettylisavpn.users.service import UserService


def public_key(value: int) -> str:
    import base64

    return base64.b64encode(bytes([value]) * 32).decode()


async def create_dependencies(postgres: Postgres) -> tuple[UUID, UUID, UUID]:
    now = datetime.now(UTC)
    node = VpnNodeRecord(
        id=uuid4(),
        name=f"vpn-session-node-{uuid4()}",
        provider=VpnNodeProvider.DIGITALOCEAN,
        provider_region="fra1",
        country_code="DE",
        city="Frankfurt",
        public_ipv4=IPv4Address("203.0.113.30"),
        private_ipv4=None,
        wireguard_port=51820,
        wireguard_public_key=public_key(1),
        capacity=100,
        status=VpnNodeStatus.ACTIVE,
        last_seen_at=now,
        created_at=now,
        updated_at=now,
        health_status=VpnNodeHealthStatus.HEALTHY,
        health_checked_at=now,
        is_available_for_free=True,
    )
    async with postgres.session() as database_session:
        user = await UserService(
            UserRepository(database_session), SubscriptionRepository(database_session)
        ).create(f"vpn-session-{uuid4()}@example.com")
        device = await DeviceService(DeviceRepository(database_session)).register(
            user.id, uuid4(), DevicePlatform.WINDOWS, "Test laptop"
        )
        database_session.add(node)
        await database_session.commit()
    return user.id, device.id, node.id


async def clean_up(postgres: Postgres, user_id: UUID, node_id: UUID) -> None:
    async with postgres.session() as session:
        await session.execute(delete(UserRecord).where(UserRecord.id == user_id))
        await session.execute(delete(VpnNodeRecord).where(VpnNodeRecord.id == node_id))
        await session.commit()
