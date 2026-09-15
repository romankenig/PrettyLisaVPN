"""Plan-aware VPN session creation with internal node placement."""

from datetime import datetime, timedelta
from ipaddress import IPv4Address
from typing import Protocol
from uuid import UUID

from prettylisavpn.subscriptions.domain import SubscriptionPlan
from prettylisavpn.subscriptions.entitlements import FREE_ENTITLEMENTS
from prettylisavpn.vpn_nodes.selection import NodeSelectionRequest, VpnNodeSelectionService
from prettylisavpn.vpn_sessions.domain import VpnSession


class VpnSessionPersistence(Protocol):
    async def get_live_for_device(self, device_id: UUID) -> VpnSession | None: ...

    async def add(self, vpn_session: VpnSession) -> VpnSession: ...


class DeviceAlreadyHasLiveVpnSessionError(RuntimeError):
    pass


class VpnSessionService:
    """Creates sessions; callers own the surrounding database transaction."""

    def __init__(
        self,
        repository: VpnSessionPersistence,
        node_selection: VpnNodeSelectionService,
        free_session_limit: timedelta | None = FREE_ENTITLEMENTS.vpn_session_limit,
    ) -> None:
        self._repository = repository
        self._node_selection = node_selection
        self._free_session_limit = free_session_limit

    async def create(
        self,
        *,
        user_id: UUID,
        device_id: UUID,
        node_selection: NodeSelectionRequest,
        client_wireguard_public_key: str,
        allocated_client_ipv4: IPv4Address,
        plan: SubscriptionPlan,
        now: datetime,
    ) -> VpnSession:
        if await self._repository.get_live_for_device(device_id) is not None:
            raise DeviceAlreadyHasLiveVpnSessionError
        node = await self._node_selection.select_node_for_session(node_selection, plan, now)
        vpn_session = VpnSession.new(
            user_id=user_id,
            device_id=device_id,
            vpn_node_id=node.id,
            client_wireguard_public_key=client_wireguard_public_key,
            allocated_client_ipv4=allocated_client_ipv4,
            plan_snapshot=plan,
            now=now,
            free_session_limit=self._free_session_limit,
        )
        return await self._repository.add(vpn_session)
