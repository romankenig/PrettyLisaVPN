"""VPN node registration, agent health, and availability tests."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from ipaddress import IPv4Address
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient, MockTransport, Request, Response

from prettylisavpn.vpn_nodes.agent import (
    HttpNodeAgentClient,
    NodeAgentHealth,
    NodeAgentUnavailableError,
)
from prettylisavpn.vpn_nodes.availability import (
    NodeUnavailabilityReason,
    VpnNodeAvailabilityPolicy,
)
from prettylisavpn.vpn_nodes.domain import (
    VpnNode,
    VpnNodeHealthStatus,
    VpnNodeProvider,
    VpnNodeStatus,
)
from prettylisavpn.vpn_nodes.service import VpnNodeRegistration, VpnNodeService

PUBLIC_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="


def make_node(**changes: object) -> VpnNode:
    now = datetime(2026, 9, 14, 12, tzinfo=UTC)
    node = VpnNode(
        id=uuid4(),
        name="fra1-01",
        provider=VpnNodeProvider.DIGITALOCEAN,
        provider_region="fra1",
        country_code="DE",
        city="Frankfurt",
        public_ipv4=IPv4Address("203.0.113.10"),
        private_ipv4=IPv4Address("10.10.0.5"),
        wireguard_port=51820,
        wireguard_public_key=PUBLIC_KEY,
        capacity=100,
        is_available_for_free=True,
        status=VpnNodeStatus.ACTIVE,
        last_seen_at=now,
        created_at=now - timedelta(days=1),
        updated_at=now,
        health_status=VpnNodeHealthStatus.HEALTHY,
        health_checked_at=now,
    )
    return replace(node, **changes)


@pytest.mark.parametrize(
    ("status", "expected_reason"),
    [
        (VpnNodeStatus.OFFLINE, NodeUnavailabilityReason.ADMINISTRATIVE_STATUS),
        (VpnNodeStatus.DRAINING, NodeUnavailabilityReason.ADMINISTRATIVE_STATUS),
        (VpnNodeStatus.DISABLED, NodeUnavailabilityReason.ADMINISTRATIVE_STATUS),
    ],
)
def test_non_active_nodes_never_receive_sessions(
    status: VpnNodeStatus, expected_reason: NodeUnavailabilityReason
):
    now = datetime(2026, 9, 14, 12, tzinfo=UTC)
    availability = VpnNodeAvailabilityPolicy(timedelta(seconds=90)).evaluate(
        make_node(status=status), now
    )

    assert availability.available is False
    assert availability.reason is expected_reason


def test_active_healthy_fresh_node_may_receive_sessions():
    now = datetime(2026, 9, 14, 12, tzinfo=UTC)

    availability = VpnNodeAvailabilityPolicy(timedelta(seconds=90)).evaluate(make_node(), now)

    assert availability.available is True
    assert availability.reason is None


def test_active_node_becomes_unavailable_after_configured_stale_timeout():
    now = datetime(2026, 9, 14, 12, tzinfo=UTC)
    node = make_node(last_seen_at=now - timedelta(seconds=91))

    availability = VpnNodeAvailabilityPolicy(timedelta(seconds=90)).evaluate(node, now)

    assert availability.available is False
    assert availability.reason is NodeUnavailabilityReason.STALE


def test_active_node_with_explicit_unhealthy_agent_state_is_unavailable():
    now = datetime(2026, 9, 14, 12, tzinfo=UTC)
    node = make_node(health_status=VpnNodeHealthStatus.UNHEALTHY)

    availability = VpnNodeAvailabilityPolicy(timedelta(seconds=90)).evaluate(node, now)

    assert availability.available is False
    assert availability.reason is NodeUnavailabilityReason.NOT_HEALTHY


class FakeRepository:
    def __init__(self, nodes: list[VpnNode] | None = None) -> None:
        self.nodes = {node.id: node for node in nodes or []}

    async def get(self, node_id: UUID) -> VpnNode | None:
        return self.nodes.get(node_id)

    async def get_by_name(self, name: str) -> VpnNode | None:
        return next((node for node in self.nodes.values() if node.name == name), None)

    async def list_all(self) -> list[VpnNode]:
        return list(self.nodes.values())

    async def add(self, node: VpnNode) -> VpnNode:
        self.nodes[node.id] = node
        return node

    async def update(self, node: VpnNode) -> VpnNode:
        self.nodes[node.id] = node
        return node

    async def update_health(
        self,
        node_id: UUID,
        health_status: VpnNodeHealthStatus,
        health_checked_at: datetime,
        last_seen_at: datetime | None,
    ) -> VpnNode | None:
        node = self.nodes.get(node_id)
        if node is None:
            return None
        updated = replace(
            node,
            health_status=health_status,
            health_checked_at=health_checked_at,
            last_seen_at=last_seen_at,
            updated_at=health_checked_at,
        )
        self.nodes[node_id] = updated
        return updated


class FakeAgent:
    def __init__(self, health: NodeAgentHealth | Exception) -> None:
        self.health = health

    async def get_health(self, node: VpnNode) -> NodeAgentHealth:
        if isinstance(self.health, Exception):
            raise self.health
        return self.health


class DrainingAgent:
    def __init__(self, repository: FakeRepository, node_id: UUID) -> None:
        self._repository = repository
        self._node_id = node_id

    async def get_health(self, node: VpnNode) -> NodeAgentHealth:
        self._repository.nodes[self._node_id] = replace(node, status=VpnNodeStatus.DRAINING)
        return NodeAgentHealth(True, True, 51820)


async def test_authenticated_agent_health_updates_last_seen_and_availability():
    now = datetime(2026, 9, 14, 12, 2, tzinfo=UTC)
    node = make_node(
        last_seen_at=None,
        health_status=VpnNodeHealthStatus.UNKNOWN,
        health_checked_at=None,
    )
    repository = FakeRepository([node])
    service = VpnNodeService(
        repository, FakeAgent(NodeAgentHealth(True, True, 51820)), timedelta(seconds=90)
    )

    availability = await service.refresh_health(node.id, now)
    updated = repository.nodes[node.id]

    assert availability.available is True
    assert updated.health_status is VpnNodeHealthStatus.HEALTHY
    assert updated.health_checked_at == now
    assert updated.last_seen_at == now


@pytest.mark.parametrize(
    "health",
    [
        NodeAgentHealth(False, False, None),
        NodeAgentHealth(True, True, 51821),
        NodeAgentUnavailableError("authentication or network failure"),
    ],
)
async def test_unhealthy_mismatched_or_unreachable_agent_is_immediately_unavailable(
    health: NodeAgentHealth | Exception,
):
    now = datetime(2026, 9, 14, 12, 2, tzinfo=UTC)
    node = make_node()
    prior_last_seen = node.last_seen_at
    repository = FakeRepository([node])
    service = VpnNodeService(repository, FakeAgent(health), timedelta(seconds=90))

    availability = await service.refresh_health(node.id, now)
    updated = repository.nodes[node.id]

    assert availability.available is False
    assert updated.health_status is VpnNodeHealthStatus.UNHEALTHY
    assert updated.health_checked_at == now
    assert updated.last_seen_at == prior_last_seen


async def test_concurrent_draining_change_is_not_overwritten_by_healthy_response():
    now = datetime(2026, 9, 14, 12, 2, tzinfo=UTC)
    node = make_node()
    repository = FakeRepository([node])
    service = VpnNodeService(repository, DrainingAgent(repository, node.id), timedelta(seconds=90))

    availability = await service.refresh_health(node.id, now)

    assert repository.nodes[node.id].status is VpnNodeStatus.DRAINING
    assert repository.nodes[node.id].health_status is VpnNodeHealthStatus.HEALTHY
    assert availability.available is False
    assert availability.reason is NodeUnavailabilityReason.ADMINISTRATIVE_STATUS


async def test_registration_starts_offline_and_preserves_lifecycle_on_reregistration():
    now = datetime(2026, 9, 14, 12, tzinfo=UTC)
    repository = FakeRepository()
    service = VpnNodeService(
        repository, FakeAgent(NodeAgentHealth(True, True, 51820)), timedelta(seconds=90)
    )
    registration = VpnNodeRegistration(
        name="fra1-01",
        provider=VpnNodeProvider.DIGITALOCEAN,
        provider_region="fra1",
        country_code="DE",
        city="Frankfurt",
        public_ipv4=IPv4Address("203.0.113.10"),
        private_ipv4=None,
        wireguard_port=51820,
        wireguard_public_key=PUBLIC_KEY,
        capacity=100,
        is_available_for_free=True,
    )

    created = await service.register(registration, now)
    repository.nodes[created.id] = replace(created, status=VpnNodeStatus.DRAINING)
    updated = await service.register(
        replace(registration, capacity=200), now + timedelta(minutes=1)
    )

    assert created.status is VpnNodeStatus.OFFLINE
    assert created.health_status is VpnNodeHealthStatus.UNKNOWN
    assert created.is_available_for_free is True
    assert updated.id == created.id
    assert updated.status is VpnNodeStatus.DRAINING
    assert updated.capacity == 200
    assert updated.is_available_for_free is True


async def test_http_agent_client_sends_machine_credential_and_uses_node_address():
    requests: list[Request] = []

    def handler(request: Request) -> Response:
        requests.append(request)
        return Response(
            200,
            json={
                "status": "HEALTHY",
                "interface": "wg0",
                "interface_up": True,
                "listen_port": 51820,
            },
        )

    async_client = AsyncClient(transport=MockTransport(handler))
    agent = HttpNodeAgentClient(async_client, "machine-secret", 8443)
    try:
        health = await agent.get_health(make_node())
    finally:
        await agent.close()

    assert health.healthy is True
    assert str(requests[0].url) == "https://203.0.113.10:8443/v1/health"
    assert requests[0].headers["Authorization"] == "Bearer machine-secret"


async def test_http_agent_client_adds_and_removes_peer_with_structured_json():
    requests: list[Request] = []

    def handler(request: Request) -> Response:
        requests.append(request)
        if request.method in ("PUT", "GET"):
            return Response(
                200,
                json={
                    "public_key": PUBLIC_KEY,
                    "vpn_ip": "10.77.0.2",
                    "latest_handshake_at": None,
                    "created": True,
                },
            )
        return Response(200, json={"removed": True})

    async_client = AsyncClient(transport=MockTransport(handler))
    agent = HttpNodeAgentClient(async_client, "machine-secret", 8443)
    try:
        await agent.add_peer(make_node(), PUBLIC_KEY, IPv4Address("10.77.0.2"))
        assert await agent.peer_exists(make_node(), PUBLIC_KEY) is True
        await agent.remove_peer(make_node(), PUBLIC_KEY)
    finally:
        await agent.close()

    assert [request.method for request in requests] == ["PUT", "GET", "DELETE"]
    assert all(request.headers["Authorization"] == "Bearer machine-secret" for request in requests)
    assert requests[0].read() == (
        b'{"public_key":"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=","vpn_ip":"10.77.0.2"}'
    )
    assert requests[1].url.params["public_key"] == PUBLIC_KEY
    assert requests[2].read() == (b'{"public_key":"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="}')


async def test_http_agent_missing_peer_is_a_reconcilable_state():
    async_client = AsyncClient(transport=MockTransport(lambda request: Response(404)))
    agent = HttpNodeAgentClient(async_client, "machine-secret", 8443)
    try:
        assert await agent.peer_exists(make_node(), PUBLIC_KEY) is False
    finally:
        await agent.close()
