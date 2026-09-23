"""Authenticated orchestration for establishing WireGuard VPN sessions."""

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from ipaddress import IPv4Address, IPv4Network
from typing import Protocol
from uuid import UUID

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from prettylisavpn.auth.session_service import AuthenticatedSessionHandler
from prettylisavpn.config import Settings
from prettylisavpn.connections import Postgres
from prettylisavpn.subscriptions.domain import SubscriptionPlan
from prettylisavpn.subscriptions.repository import SubscriptionRepository
from prettylisavpn.vpn_nodes.agent import NodeAgentPeerPort, NodeAgentUnavailableError
from prettylisavpn.vpn_nodes.domain import VpnNode
from prettylisavpn.vpn_nodes.profiles import ProfileId
from prettylisavpn.vpn_nodes.repository import VpnNodeRepository
from prettylisavpn.vpn_nodes.selection import (
    NodeSelectionMode,
    NodeSelectionRequest,
    NoEligibleVpnNodeError,
    VpnNodeSelectionService,
)
from prettylisavpn.vpn_sessions.address_allocation import (
    AddressPoolExhaustedError,
    VpnClientAddressAllocator,
)
from prettylisavpn.vpn_sessions.domain import VpnSession, VpnSessionStatus
from prettylisavpn.vpn_sessions.protocol import ConnectionConfig
from prettylisavpn.vpn_sessions.repository import VpnSessionRepository
from prettylisavpn.vpn_sessions.service import (
    DeviceAlreadyHasLiveVpnSessionError,
    VpnSessionService,
)


class CountryUnavailableError(LookupError):
    pass


class VpnUnavailableError(LookupError):
    pass


class VpnSetupFailedError(RuntimeError):
    pass


class VpnSessionPersistenceUnavailableError(RuntimeError):
    pass


def deployed_session_candidates(
    node: VpnNode, now: datetime
) -> tuple[ConnectionConfig, ...] | None:
    if not node.deployed_profiles:
        return None  # Preserve legacy nodes until explicitly migrated by an operator.
    profile = node.verified_wireguard_session_profile(now)
    if profile is None:
        return ()  # Never substitute local NATIVE policy for failed/mismatched evidence.
    return (
        ConnectionConfig.for_profile(
            ProfileId.WIREGUARD_UDP, node.country_code, node.id, profile.port
        ),
    )


@dataclass(frozen=True, slots=True)
class ActiveVpnTransport:
    session_id: UUID
    country_code: str
    endpoint_ipv4: IPv4Address
    endpoint_port: int
    server_public_key: str
    client_ipv4: IPv4Address
    dns: tuple[IPv4Address, ...]
    allowed_ips: tuple[IPv4Network, ...]
    expires_at: datetime | None
    node_id: UUID | None = None
    deployed_candidates: tuple[ConnectionConfig, ...] | None = None

    @property
    def candidates(self) -> tuple[ConnectionConfig, ...]:
        # Only the provisioned node is connectable. No additional peers or fallback.
        if self.deployed_candidates is not None:
            return self.deployed_candidates
        return (ConnectionConfig(self.country_code, self.node_id, self.endpoint_port),)


class VpnConnectionHandler(Protocol):
    async def connect(
        self, access_token: str, request: NodeSelectionRequest, public_key: str
    ) -> ActiveVpnTransport: ...


class VpnConnectionService:
    def __init__(
        self,
        postgres: Postgres,
        authenticated_sessions: AuthenticatedSessionHandler,
        agent: NodeAgentPeerPort,
        settings: Settings,
    ) -> None:
        self._postgres = postgres
        self._authenticated_sessions = authenticated_sessions
        self._agent = agent
        self._stale_timeout = timedelta(seconds=settings.vpn_node_stale_timeout_seconds)
        self._subnet = settings.vpn_client_subnet
        self._reserved = {settings.vpn_client_gateway_ipv4}
        self._dns = tuple(settings.vpn_client_dns)
        self._allowed_ips = tuple(settings.vpn_client_allowed_ips)

    async def connect(
        self, access_token: str, request: NodeSelectionRequest, public_key: str
    ) -> ActiveVpnTransport:
        identity = await self._authenticated_sessions.authenticate(access_token)
        now = datetime.now(UTC)
        pending, node = await self._reserve(
            identity.user_id, identity.device_id, request, public_key, now
        )
        try:
            await self._agent.add_peer(node, public_key, pending.allocated_client_ipv4)
        except NodeAgentUnavailableError:
            await self._compensate(node, pending, remove_peer=True)
            raise VpnSetupFailedError from None

        try:
            active = await self._set_status(pending.id, VpnSessionStatus.ACTIVE)
        except VpnSessionPersistenceUnavailableError:
            await self._compensate(node, pending, remove_peer=True)
            raise
        return ActiveVpnTransport(
            session_id=active.id,
            node_id=node.id,
            country_code=node.country_code,
            endpoint_ipv4=node.public_ipv4,
            endpoint_port=node.wireguard_port,
            server_public_key=node.wireguard_public_key,
            client_ipv4=active.allocated_client_ipv4,
            dns=self._dns,
            allowed_ips=self._allowed_ips,
            expires_at=active.expires_at,
            deployed_candidates=deployed_session_candidates(node, datetime.now(UTC)),
        )

    async def _reserve(
        self,
        user_id: UUID,
        device_id: UUID,
        request: NodeSelectionRequest,
        public_key: str,
        now: datetime,
    ) -> tuple[VpnSession, VpnNode]:
        try:
            async with self._postgres.session() as database_session:
                async with database_session.begin():
                    subscriptions = SubscriptionRepository(database_session)
                    subscription = await subscriptions.get_by_user_id(user_id)
                    if subscription is None:
                        raise VpnSessionPersistenceUnavailableError
                    plan = (
                        subscription.plan if subscription.is_active(now) else SubscriptionPlan.FREE
                    )
                    sessions = VpnSessionRepository(database_session)
                    nodes = VpnNodeRepository(database_session)
                    pending = await VpnSessionService(
                        sessions,
                        VpnNodeSelectionService(nodes, self._stale_timeout),
                        VpnClientAddressAllocator(sessions, self._subnet, self._reserved),
                    ).create(
                        user_id=user_id,
                        device_id=device_id,
                        node_selection=request,
                        client_wireguard_public_key=public_key,
                        plan=plan,
                        now=now,
                    )
                    node = await nodes.get(pending.vpn_node_id)
                    if node is None:
                        raise VpnSessionPersistenceUnavailableError
                    return pending, node
        except NoEligibleVpnNodeError:
            if request.mode is NodeSelectionMode.COUNTRY:
                raise CountryUnavailableError from None
            raise VpnUnavailableError from None
        except (DeviceAlreadyHasLiveVpnSessionError, AddressPoolExhaustedError):
            raise
        except IntegrityError as error:
            if "uq_vpn_sessions_live_device" in str(error.orig):
                raise DeviceAlreadyHasLiveVpnSessionError from None
            raise VpnUnavailableError from None
        except VpnSessionPersistenceUnavailableError:
            raise
        except SQLAlchemyError:
            raise VpnSessionPersistenceUnavailableError from None

    async def _set_status(
        self,
        session_id: UUID,
        status: VpnSessionStatus,
        peer_removed_at: datetime | None = None,
    ) -> VpnSession:
        try:
            async with self._postgres.session() as database_session:
                async with database_session.begin():
                    repository = VpnSessionRepository(database_session)
                    current = await repository.get_for_update(session_id)
                    if current is None:
                        raise VpnSessionPersistenceUnavailableError
                    updated = replace(
                        current,
                        status=status,
                        peer_removed_at=peer_removed_at,
                        updated_at=datetime.now(UTC),
                    )
                    return await repository.update(updated)
        except VpnSessionPersistenceUnavailableError:
            raise
        except SQLAlchemyError:
            raise VpnSessionPersistenceUnavailableError from None

    async def _compensate(self, node: VpnNode, pending: VpnSession, *, remove_peer: bool) -> None:
        peer_removed_at: datetime | None = None
        if remove_peer:
            try:
                await self._agent.remove_peer(node, pending.client_wireguard_public_key)
                peer_removed_at = datetime.now(UTC)
            except NodeAgentUnavailableError:
                pass
        try:
            await self._set_status(
                pending.id, VpnSessionStatus.FAILED, peer_removed_at=peer_removed_at
            )
        except VpnSessionPersistenceUnavailableError:
            pass


class UnavailableVpnConnectionService:
    def __init__(self, authenticated_sessions: AuthenticatedSessionHandler) -> None:
        self._authenticated_sessions = authenticated_sessions

    async def connect(
        self, access_token: str, request: NodeSelectionRequest, public_key: str
    ) -> ActiveVpnTransport:
        await self._authenticated_sessions.authenticate(access_token)
        raise VpnSetupFailedError
