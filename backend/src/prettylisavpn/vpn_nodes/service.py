"""VPN node registration, authenticated health tracking, and eligibility."""

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from ipaddress import IPv4Address
from uuid import UUID, uuid4

from prettylisavpn.vpn_nodes.agent import (
    NodeAgentHealthPort,
    NodeAgentUnavailableError,
)
from prettylisavpn.vpn_nodes.availability import NodeAvailability, VpnNodeAvailabilityPolicy
from prettylisavpn.vpn_nodes.domain import (
    VpnNode,
    VpnNodeHealthStatus,
    VpnNodeProvider,
    VpnNodeStatus,
)
from prettylisavpn.vpn_nodes.repository import VpnNodeRepository


class VpnNodeNotFoundError(LookupError):
    pass


@dataclass(frozen=True, slots=True)
class VpnNodeRegistration:
    name: str
    provider: VpnNodeProvider
    provider_region: str
    country_code: str
    city: str | None
    public_ipv4: IPv4Address
    private_ipv4: IPv4Address | None
    wireguard_port: int
    wireguard_public_key: str
    capacity: int


class VpnNodeService:
    def __init__(
        self,
        repository: VpnNodeRepository,
        agent: NodeAgentHealthPort,
        stale_timeout: timedelta,
    ) -> None:
        self._repository = repository
        self._agent = agent
        self._availability = VpnNodeAvailabilityPolicy(stale_timeout)

    async def register(
        self, registration: VpnNodeRegistration, now: datetime | None = None
    ) -> VpnNode:
        checked_at = now if now is not None else datetime.now(UTC)
        existing = await self._repository.get_by_name(registration.name.strip())
        if existing is None:
            return await self._repository.add(
                VpnNode(
                    id=uuid4(),
                    name=registration.name,
                    provider=registration.provider,
                    provider_region=registration.provider_region,
                    country_code=registration.country_code,
                    city=registration.city,
                    public_ipv4=registration.public_ipv4,
                    private_ipv4=registration.private_ipv4,
                    wireguard_port=registration.wireguard_port,
                    wireguard_public_key=registration.wireguard_public_key,
                    capacity=registration.capacity,
                    status=VpnNodeStatus.OFFLINE,
                    last_seen_at=None,
                    created_at=checked_at,
                    updated_at=checked_at,
                )
            )
        updated = replace(
            existing,
            name=registration.name,
            provider=registration.provider,
            provider_region=registration.provider_region,
            country_code=registration.country_code,
            city=registration.city,
            public_ipv4=registration.public_ipv4,
            private_ipv4=registration.private_ipv4,
            wireguard_port=registration.wireguard_port,
            wireguard_public_key=registration.wireguard_public_key,
            capacity=registration.capacity,
            updated_at=checked_at,
        )
        return await self._repository.update(updated)

    async def refresh_health(self, node_id: UUID, now: datetime | None = None) -> NodeAvailability:
        checked_at = now if now is not None else datetime.now(UTC)
        node = await self._repository.get(node_id)
        if node is None:
            raise VpnNodeNotFoundError
        try:
            health = await self._agent.get_health(node)
            healthy = (
                health.healthy and health.interface_up and health.listen_port == node.wireguard_port
            )
        except NodeAgentUnavailableError:
            healthy = False
        updated = await self._repository.update_health(
            node.id,
            VpnNodeHealthStatus.HEALTHY if healthy else VpnNodeHealthStatus.UNHEALTHY,
            checked_at,
            checked_at if healthy else node.last_seen_at,
        )
        if updated is None:
            raise VpnNodeNotFoundError
        return self._availability.evaluate(updated, checked_at)

    async def list_available(self, now: datetime | None = None) -> list[VpnNode]:
        checked_at = now if now is not None else datetime.now(UTC)
        return [
            node
            for node in await self._repository.list_all()
            if self._availability.evaluate(node, checked_at).available
        ]
