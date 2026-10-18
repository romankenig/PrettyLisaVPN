"""VPN session persistence tests against local Compose PostgreSQL or CI."""

import asyncio
import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from ipaddress import IPv4Address
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError

from prettylisavpn.auth.session_service import AccessIdentity
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
from prettylisavpn.vpn_nodes.agent import NodeAgentUnavailableError
from prettylisavpn.vpn_nodes.domain import (
    VpnNode,
    VpnNodeHealthStatus,
    VpnNodeProvider,
    VpnNodeStatus,
)
from prettylisavpn.vpn_nodes.model import VpnNodeRecord
from prettylisavpn.vpn_nodes.repository import VpnNodeRepository
from prettylisavpn.vpn_nodes.selection import NodeSelectionRequest, VpnNodeSelectionService
from prettylisavpn.vpn_sessions.address_allocation import VpnClientAddressAllocator
from prettylisavpn.vpn_sessions.connection import (
    VpnConnectionService,
    VpnSetupFailedError,
    VpnUnavailableError,
)
from prettylisavpn.vpn_sessions.domain import VpnSession, VpnSessionStatus
from prettylisavpn.vpn_sessions.model import VpnSessionRecord
from prettylisavpn.vpn_sessions.repository import VpnSessionRepository
from prettylisavpn.vpn_sessions.service import (
    DeviceAlreadyHasLiveVpnSessionError,
    VpnSessionService,
)
from prettylisavpn.vpn_sessions.termination import (
    OwnedVpnSessionNotFoundError,
    VpnSessionReconciler,
    VpnSessionTerminationService,
)

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
            assert (
                await repository.get_live_for_device(device_id, vpn_session.started_at)
                == vpn_session
            )
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
            assert (
                await VpnSessionRepository(session).get_live_for_device(
                    device_id, datetime.now(UTC)
                )
                is None
            )
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
                VpnClientAddressAllocator(
                    VpnSessionRepository(session),
                    Settings().vpn_client_subnet,
                    {Settings().vpn_client_gateway_ipv4},
                ),
            )
            created = await service.create(
                user_id=user_id,
                device_id=device_id,
                node_selection=NodeSelectionRequest.country("de"),
                client_wireguard_public_key=public_key(7),
                plan=SubscriptionPlan.FREE,
                now=now,
            )
            await session.commit()

        assert created.vpn_node_id == node_id
        assert created.plan_snapshot is SubscriptionPlan.FREE
        assert created.allocated_client_ipv4 == IPv4Address("10.77.0.2")
        assert created.expires_at == now + timedelta(hours=1)
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


async def test_concurrent_allocations_are_distinct_and_persisted():
    postgres = Postgres(Settings())
    user_id, first_device_id, node_id = await create_dependencies(postgres)
    async with postgres.session() as session:
        second_device = await DeviceService(DeviceRepository(session)).register(
            user_id, uuid4(), DevicePlatform.ANDROID, "Second test device"
        )
        await session.commit()

    async def allocate_and_persist(device_id: UUID, key_byte: int) -> VpnSession:
        async with postgres.session() as session:
            repository = VpnSessionRepository(session)
            allocator = VpnClientAddressAllocator(
                repository,
                Settings().vpn_client_subnet,
                {Settings().vpn_client_gateway_ipv4},
            )
            address = await allocator.allocate(datetime.now(UTC))
            vpn_session = VpnSession.new(
                user_id=user_id,
                device_id=device_id,
                vpn_node_id=node_id,
                client_wireguard_public_key=public_key(key_byte),
                allocated_client_ipv4=address,
                plan_snapshot=SubscriptionPlan.PREMIUM,
                now=datetime.now(UTC),
            )
            await repository.add(vpn_session)
            await session.commit()
            return vpn_session

    try:
        first, second = await asyncio.gather(
            allocate_and_persist(first_device_id, 21),
            allocate_and_persist(second_device.id, 22),
        )

        assert first.allocated_client_ipv4 != second.allocated_client_ipv4
        async with postgres.session() as session:
            persisted = await VpnSessionRepository(session).list_by_user(user_id)
            assert {item.allocated_client_ipv4 for item in persisted} == {
                first.allocated_client_ipv4,
                second.allocated_client_ipv4,
            }
    finally:
        await clean_up(postgres, user_id, node_id)
        await postgres.close()


def test_schema_has_no_client_private_key_column():
    columns = set(VpnSessionRecord.__table__.columns.keys())

    assert "client_wireguard_private_key" not in columns
    assert "wireguard_private_key" not in columns


async def test_connection_orchestration_activates_only_after_agent_peer_creation():
    postgres = Postgres(Settings())
    user_id, device_id, node_id = await create_dependencies(postgres)
    authentication = AsyncMock()
    authentication.authenticate.return_value = AccessIdentity(user_id, device_id, uuid4())
    agent = AsyncMock()
    service = VpnConnectionService(postgres, authentication, agent, Settings())
    try:
        result = await service.connect("token", NodeSelectionRequest.auto(), public_key(31))

        agent.add_peer.assert_awaited_once()
        async with postgres.session() as session:
            persisted = await VpnSessionRepository(session).get(result.session_id)
        assert persisted is not None
        assert persisted.status is VpnSessionStatus.ACTIVE
        assert persisted.expires_at is not None
        assert result.expires_at == persisted.expires_at
        assert result.endpoint_port == 51820
        assert result.client_ipv4 == persisted.allocated_client_ipv4
    finally:
        await clean_up(postgres, user_id, node_id)
        await postgres.close()


async def test_agent_failure_marks_pending_failed_and_releases_address_for_retry():
    postgres = Postgres(Settings())
    user_id, device_id, node_id = await create_dependencies(postgres)
    authentication = AsyncMock()
    authentication.authenticate.return_value = AccessIdentity(user_id, device_id, uuid4())
    agent = AsyncMock()
    agent.add_peer.side_effect = NodeAgentUnavailableError
    service = VpnConnectionService(postgres, authentication, agent, Settings())
    try:
        with pytest.raises(VpnSetupFailedError):
            await service.connect("token", NodeSelectionRequest.country("DE"), public_key(32))

        async with postgres.session() as session:
            failed = (await VpnSessionRepository(session).list_by_user(user_id))[0]
        assert failed.status is VpnSessionStatus.FAILED
        agent.remove_peer.assert_awaited_once()

        agent.add_peer.side_effect = None
        recovered = await service.connect(
            "token", NodeSelectionRequest.country("DE"), public_key(33)
        )
        assert recovered.client_ipv4 == failed.allocated_client_ipv4
    finally:
        await clean_up(postgres, user_id, node_id)
        await postgres.close()


async def test_concurrent_connection_requests_for_one_device_create_only_one_session():
    postgres = Postgres(Settings())
    user_id, device_id, node_id = await create_dependencies(postgres)
    authentication = AsyncMock()
    authentication.authenticate.return_value = AccessIdentity(user_id, device_id, uuid4())
    service = VpnConnectionService(postgres, authentication, AsyncMock(), Settings())
    try:
        results = await asyncio.gather(
            service.connect("token", NodeSelectionRequest.auto(), public_key(34)),
            service.connect("token", NodeSelectionRequest.auto(), public_key(35)),
            return_exceptions=True,
        )

        assert sum(not isinstance(result, Exception) for result in results) == 1
        assert (
            sum(isinstance(result, DeviceAlreadyHasLiveVpnSessionError) for result in results) == 1
        )
        async with postgres.session() as session:
            persisted = await VpnSessionRepository(session).list_by_user(user_id)
        assert len(persisted) == 1
        assert persisted[0].status is VpnSessionStatus.ACTIVE
    finally:
        await clean_up(postgres, user_id, node_id)
        await postgres.close()


async def test_capacity_race_allows_only_one_pending_reservation():
    postgres = Postgres(Settings())
    first_user_id, first_device_id, node_id = await create_dependencies(postgres)
    async with postgres.session() as session:
        users = UserService(UserRepository(session), SubscriptionRepository(session))
        second_user = await users.create(f"capacity-race-{uuid4()}@example.com")
        second_device = await DeviceService(DeviceRepository(session)).register(
            second_user.id, uuid4(), DevicePlatform.ANDROID, "Capacity race device"
        )
        nodes = VpnNodeRepository(session)
        node = await nodes.get(node_id)
        assert node is not None
        await nodes.update(replace(node, capacity=1))
        await session.commit()

    authentication = AsyncMock()
    authentication.authenticate.side_effect = [
        AccessIdentity(first_user_id, first_device_id, uuid4()),
        AccessIdentity(second_user.id, second_device.id, uuid4()),
    ]
    service = VpnConnectionService(postgres, authentication, AsyncMock(), Settings())
    try:
        results = await asyncio.gather(
            service.connect("first-token", NodeSelectionRequest.auto(), public_key(36)),
            service.connect("second-token", NodeSelectionRequest.auto(), public_key(37)),
            return_exceptions=True,
        )

        assert sum(not isinstance(result, Exception) for result in results) == 1
        assert sum(isinstance(result, VpnUnavailableError) for result in results) == 1
    finally:
        async with postgres.session() as session:
            await session.execute(
                delete(UserRecord).where(UserRecord.id.in_((first_user_id, second_user.id)))
            )
            await session.execute(delete(VpnNodeRecord).where(VpnNodeRecord.id == node_id))
            await session.commit()
        await postgres.close()


async def test_manual_disconnect_enforces_ownership_and_is_idempotent():
    postgres = Postgres(Settings())
    user_id, device_id, node_id = await create_dependencies(postgres)
    authentication = AsyncMock()
    identity = AccessIdentity(user_id, device_id, uuid4())
    authentication.authenticate.return_value = identity
    agent = AsyncMock()
    connection = VpnConnectionService(postgres, authentication, agent, Settings())
    termination = VpnSessionTerminationService(postgres, authentication, agent)
    try:
        active = await connection.connect("token", NodeSelectionRequest.auto(), public_key(41))
        authentication.authenticate.return_value = replace(identity, device_id=uuid4())
        with pytest.raises(OwnedVpnSessionNotFoundError):
            await termination.disconnect("other-device-token", active.session_id)

        authentication.authenticate.return_value = identity
        first = await termination.disconnect("token", active.session_id)
        duplicate = await termination.disconnect("token", active.session_id)

        assert first.status is duplicate.status is VpnSessionStatus.DISCONNECTED
        agent.remove_peer.assert_awaited_once()
        async with postgres.session() as session:
            persisted = await VpnSessionRepository(session).get(active.session_id)
        assert persisted is not None
        assert persisted.disconnected_at is not None
        assert persisted.peer_removed_at is not None
        assert not persisted.is_live()
    finally:
        await clean_up(postgres, user_id, node_id)
        await postgres.close()


async def test_expiry_survives_restart_and_retries_agent_outage_without_extending_session():
    postgres = Postgres(Settings())
    user_id, device_id, node_id = await create_dependencies(postgres)
    started_at = datetime.now(UTC) - timedelta(minutes=61)
    expired = VpnSession.new(
        user_id=user_id,
        device_id=device_id,
        vpn_node_id=node_id,
        client_wireguard_public_key=public_key(42),
        allocated_client_ipv4=IPv4Address("10.77.0.2"),
        plan_snapshot=SubscriptionPlan.FREE,
        now=started_at,
    )
    expired = replace(expired, status=VpnSessionStatus.ACTIVE)
    async with postgres.session() as session:
        await VpnSessionRepository(session).add(expired)
        await session.commit()

    agent = AsyncMock()
    agent.remove_peer.side_effect = NodeAgentUnavailableError
    try:
        await VpnSessionReconciler(postgres, agent, Settings()).run_once()
        async with postgres.session() as session:
            after_outage = await VpnSessionRepository(session).get(expired.id)
        assert after_outage is not None
        assert after_outage.status is VpnSessionStatus.EXPIRED
        assert after_outage.peer_removed_at is None

        agent.remove_peer.side_effect = None
        restarted_reconciler = VpnSessionReconciler(postgres, agent, Settings())
        await restarted_reconciler.run_once()
        async with postgres.session() as session:
            cleaned = await VpnSessionRepository(session).get(expired.id)
        assert cleaned is not None
        assert cleaned.status is VpnSessionStatus.EXPIRED
        assert cleaned.peer_removed_at is not None

        removal_calls = agent.remove_peer.await_count
        await restarted_reconciler.run_once()
        assert agent.remove_peer.await_count == removal_calls
    finally:
        await clean_up(postgres, user_id, node_id)
        await postgres.close()


async def test_reconciler_releases_active_session_when_agent_peer_is_missing():
    postgres = Postgres(Settings())
    user_id, device_id, node_id = await create_dependencies(postgres)
    active = replace(
        make_session(user_id, device_id, node_id, 43),
        status=VpnSessionStatus.ACTIVE,
    )
    async with postgres.session() as session:
        await VpnSessionRepository(session).add(active)
        await session.commit()
    agent = AsyncMock()
    agent.peer_exists.return_value = False
    try:
        await VpnSessionReconciler(postgres, agent, Settings()).run_once()

        async with postgres.session() as session:
            reconciled = await VpnSessionRepository(session).get(active.id)
        assert reconciled is not None
        assert reconciled.status is VpnSessionStatus.FAILED
        assert reconciled.peer_removed_at is not None
        assert not reconciled.is_live()
    finally:
        await clean_up(postgres, user_id, node_id)
        await postgres.close()
