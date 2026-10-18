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
from prettylisavpn.devices.repository import DeviceRepository
from prettylisavpn.subscriptions.domain import SubscriptionPlan
from prettylisavpn.subscriptions.entitlements import free_session_duration
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
from prettylisavpn.vpn_sessions.termination import remove_and_record_peer


class CountryUnavailableError(LookupError):
    pass


class VpnUnavailableError(LookupError):
    pass


class VpnSetupFailedError(RuntimeError):
    pass


class VpnSessionPersistenceUnavailableError(RuntimeError):
    pass


class FreeDailyLimitReachedError(RuntimeError):
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
            active = await self._activate(pending, node)
        except (VpnSetupFailedError, VpnSessionPersistenceUnavailableError):
            await self._compensate(node, pending)
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
                    if not await DeviceRepository(database_session).lock_user(user_id):
                        raise VpnSetupFailedError
                    device = await DeviceRepository(database_session).get_for_update(device_id)
                    if device is None or device.user_id != user_id or not device.is_active():
                        raise VpnSetupFailedError
                    sessions = VpnSessionRepository(database_session)
                    # Allocation may expire other rows. Take its global lock before
                    # session locks so parallel connects cannot invert this order.
                    await sessions.acquire_address_allocation_lock()
                    now = datetime.now(UTC)
                    await sessions.reconcile_paid_access(now, user_id)
                    await sessions.expire_allocations(now, user_id)
                    if await sessions.get_live_for_device(device_id, now) is not None:
                        raise DeviceAlreadyHasLiveVpnSessionError
                    await sessions.acquire_peer_lock(public_key)
                    if await sessions.has_unremoved_public_key(public_key):
                        raise VpnUnavailableError
                    subscriptions = SubscriptionRepository(database_session)
                    subscription = await subscriptions.get_by_user_id(user_id)
                    if subscription is None:
                        raise VpnSessionPersistenceUnavailableError
                    plan = (
                        subscription.effective_plan(now)
                    )
                    free_limit = None
                    if plan is SubscriptionPlan.FREE:
                        remaining = await sessions.remaining_free_seconds(user_id, now)
                        if remaining <= 0:
                            raise FreeDailyLimitReachedError
                        free_limit = free_session_duration(now, remaining)
                    sessions = VpnSessionRepository(database_session)
                    nodes = VpnNodeRepository(database_session)
                    pending = await VpnSessionService(
                        sessions,
                        VpnNodeSelectionService(nodes, self._stale_timeout),
                        VpnClientAddressAllocator(sessions, self._subnet, self._reserved),
                        free_session_limit=free_limit,
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
                    if plan is not SubscriptionPlan.FREE:
                        pending = await sessions.update(
                            replace(pending, expires_at=subscription.current_period_end)
                        )
                    else:
                        await sessions.reserve_free_usage(pending)
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

    async def _activate(self, pending: VpnSession, node: VpnNode) -> VpnSession:
        try:
            async with self._postgres.session() as database_session:
                async with database_session.begin():
                    # Same device -> session lock order as revoke. Keep the bounded
                    # node operation inside this lock so revoke cannot acknowledge
                    # deletion before an in-flight provisioning call finishes.
                    device = await DeviceRepository(database_session).get_for_update(
                        pending.device_id
                    )
                    if device is None or not device.is_active():
                        raise VpnSetupFailedError
                    repository = VpnSessionRepository(database_session)
                    current = await repository.get_for_update(pending.id)
                    if current is None or current.status is not VpnSessionStatus.PENDING:
                        raise VpnSetupFailedError
                    now = datetime.now(UTC)
                    if current.plan_snapshot is not SubscriptionPlan.FREE:
                        subscription = await SubscriptionRepository(database_session).get_by_user_id(current.user_id)
                        if subscription is None or subscription.effective_plan(now) is SubscriptionPlan.FREE:
                            raise VpnSetupFailedError
                        current = replace(current, expires_at=subscription.current_period_end)
                    elif current.expires_at is not None and current.expires_at <= now:
                        raise VpnSetupFailedError
                    await repository.acquire_peer_lock(current.client_wireguard_public_key)
                    try:
                        await self._agent.add_peer(
                            node, current.client_wireguard_public_key, current.allocated_client_ipv4
                        )
                    except NodeAgentUnavailableError:
                        raise VpnSetupFailedError from None
                    # Provisioning can cross the paid deadline. Compensation persists
                    # cleanup intent and removes a peer even if the agent later fails.
                    if current.expires_at is not None and current.expires_at <= datetime.now(UTC):
                        raise VpnSetupFailedError
                    await repository.activate_free_usage(current.id, datetime.now(UTC))
                    return await repository.update(
                        replace(
                            current, status=VpnSessionStatus.ACTIVE, updated_at=datetime.now(UTC)
                        )
                    )
        except SQLAlchemyError:
            raise VpnSessionPersistenceUnavailableError from None

    async def _compensate(self, node: VpnNode, pending: VpnSession) -> None:
        try:
            async with self._postgres.session() as database_session:
                async with database_session.begin():
                    await DeviceRepository(database_session).get_for_update(pending.device_id)
                    repository = VpnSessionRepository(database_session)
                    current = await repository.get_for_update(pending.id)
                    if current is None or current.peer_removed_at is not None:
                        return
                    if current.status in (VpnSessionStatus.PENDING, VpnSessionStatus.ACTIVE):
                        current = replace(
                            current, status=VpnSessionStatus.FAILED, updated_at=datetime.now(UTC)
                        )
                        await repository.update(current)
            # Persist terminal cleanup intent before contacting the node.
            await remove_and_record_peer(self._postgres, self._agent, current, node)
        except SQLAlchemyError:
            pass  # Revocation can still persist cleanup when storage recovers.


class UnavailableVpnConnectionService:
    def __init__(self, authenticated_sessions: AuthenticatedSessionHandler) -> None:
        self._authenticated_sessions = authenticated_sessions

    async def connect(
        self, access_token: str, request: NodeSelectionRequest, public_key: str
    ) -> ActiveVpnTransport:
        await self._authenticated_sessions.authenticate(access_token)
        raise VpnSetupFailedError
