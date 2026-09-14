"""VPN session persistence tests against local Compose PostgreSQL or CI."""

import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from ipaddress import IPv4Address
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError

from prettylisavpn.config import Settings
from prettylisavpn.connections import Postgres
from prettylisavpn.devices.domain import DevicePlatform
from prettylisavpn.devices.repository import DeviceRepository
from prettylisavpn.devices.service import DeviceService
from prettylisavpn.subscriptions.domain import SubscriptionPlan
from prettylisavpn.subscriptions.repository import SubscriptionRepository
from prettylisavpn.users.model import UserRecord
from prettylisavpn.users.repository import UserRepository
from prettylisavpn.users.service import UserService
from prettylisavpn.vpn_nodes.domain import (
    VpnNode,
    VpnNodeHealthStatus,
    VpnNodeProvider,
    VpnNodeStatus,
)
from prettylisavpn.vpn_nodes.model import VpnNodeRecord
from prettylisavpn.vpn_nodes.repository import VpnNodeRepository
from prettylisavpn.vpn_nodes.selection import VpnNodeSelectionService
from prettylisavpn.vpn_sessions.domain import VpnSession, VpnSessionStatus
from prettylisavpn.vpn_sessions.model import VpnSessionRecord
from prettylisavpn.vpn_sessions.repository import VpnSessionRepository
from prettylisavpn.vpn_sessions.service import VpnSessionService

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1",
        reason="Set RUN_INTEGRATION_TESTS=1 with PostgreSQL running",
    ),
]


def public_key(value: int) -> str:
    import base64

    return base64.b64encode(bytes([value]) * 32).decode()


async def create_dependencies(postgres: Postgres) -> tuple[UUID, UUID, UUID]:
    now = datetime.now(UTC)
    node = VpnNode(
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
        await VpnNodeRepository(database_session).add(node)
        await database_session.commit()
    return user.id, device.id, node.id


def make_session(user_id: UUID, device_id: UUID, node_id: UUID, key_byte: int = 2) -> VpnSession:
    return VpnSession.new(
        user_id=user_id,
        device_id=device_id,
        vpn_node_id=node_id,
        client_wireguard_public_key=public_key(key_byte),
        allocated_client_ipv4=IPv4Address(f"10.88.0.{key_byte}"),
        plan_snapshot=SubscriptionPlan.FREE,
        now=datetime.now(UTC),
    )


async def clean_up(postgres: Postgres, user_id: UUID, node_id: UUID) -> None:
    async with postgres.session() as session:
        await session.execute(delete(UserRecord).where(UserRecord.id == user_id))
        await session.execute(delete(VpnNodeRecord).where(VpnNodeRecord.id == node_id))
        await session.commit()


async def test_round_trip_lookup_list_and_lifecycle_update():
    postgres = Postgres(Settings())
    user_id, device_id, node_id = await create_dependencies(postgres)
    vpn_session = make_session(user_id, device_id, node_id)
    try:
        async with postgres.session() as session:
            repository = VpnSessionRepository(session)
            assert await repository.add(vpn_session) == vpn_session
            await session.commit()

        async with postgres.session() as session:
            repository = VpnSessionRepository(session)
            assert await repository.get(vpn_session.id) == vpn_session
            assert await repository.get_live_for_device(device_id) == vpn_session
            assert await repository.list_by_user(user_id) == [vpn_session]
            snapshots = await VpnNodeRepository(session).list_capacity_snapshots(
                "DE", at=vpn_session.started_at
            )
            assert len(snapshots) == 1
            assert snapshots[0].live_sessions == 1
            assert vpn_session.expires_at is not None
            after_expiry = await VpnNodeRepository(session).list_capacity_snapshots(
                "DE", at=vpn_session.expires_at + timedelta(seconds=1)
            )
            assert after_expiry[0].live_sessions == 0
            disconnected_at = vpn_session.started_at + timedelta(minutes=1)
            disconnected = replace(
                vpn_session,
                status=VpnSessionStatus.DISCONNECTED,
                disconnected_at=disconnected_at,
                updated_at=disconnected_at,
            )
            assert await repository.update(disconnected) == disconnected
            await session.commit()

        async with postgres.session() as session:
            assert await VpnSessionRepository(session).get_live_for_device(device_id) is None
    finally:
        await clean_up(postgres, user_id, node_id)
        await postgres.close()


async def test_database_prevents_two_live_sessions_for_one_device():
    postgres = Postgres(Settings())
    user_id, device_id, node_id = await create_dependencies(postgres)
    first = make_session(user_id, device_id, node_id, 3)
    second = make_session(user_id, device_id, node_id, 4)
    try:
        async with postgres.session() as session:
            await VpnSessionRepository(session).add(first)
            await session.commit()

        with pytest.raises(IntegrityError):
            async with postgres.session() as session:
                await VpnSessionRepository(session).add(second)
    finally:
        await clean_up(postgres, user_id, node_id)
        await postgres.close()


async def test_plan_aware_service_selects_node_and_creates_session_in_one_transaction():
    postgres = Postgres(Settings())
    user_id, device_id, node_id = await create_dependencies(postgres)
    now = datetime.now(UTC)
    try:
        async with postgres.session() as session:
            service = VpnSessionService(
                VpnSessionRepository(session),
                VpnNodeSelectionService(VpnNodeRepository(session), timedelta(seconds=90)),
            )
            created = await service.create(
                user_id=user_id,
                device_id=device_id,
                country_code="de",
                client_wireguard_public_key=public_key(7),
                allocated_client_ipv4=IPv4Address("10.88.0.7"),
                plan=SubscriptionPlan.FREE,
                now=now,
            )
            await session.commit()

        assert created.vpn_node_id == node_id
        assert created.plan_snapshot is SubscriptionPlan.FREE
        assert created.expires_at == now + timedelta(minutes=15)
    finally:
        await clean_up(postgres, user_id, node_id)
        await postgres.close()


async def test_terminal_session_releases_device_for_another_session():
    postgres = Postgres(Settings())
    user_id, device_id, node_id = await create_dependencies(postgres)
    first = make_session(user_id, device_id, node_id, 5)
    disconnected_at = first.started_at + timedelta(seconds=1)
    first = replace(
        first,
        status=VpnSessionStatus.DISCONNECTED,
        disconnected_at=disconnected_at,
        updated_at=disconnected_at,
    )
    second = make_session(user_id, device_id, node_id, 6)
    try:
        async with postgres.session() as session:
            repository = VpnSessionRepository(session)
            await repository.add(first)
            await repository.add(second)
            await session.commit()
    finally:
        await clean_up(postgres, user_id, node_id)
        await postgres.close()


def test_schema_has_no_client_private_key_column():
    columns = set(VpnSessionRecord.__table__.columns.keys())

    assert "client_wireguard_private_key" not in columns
    assert "wireguard_private_key" not in columns
