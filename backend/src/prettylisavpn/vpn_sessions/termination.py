"""Owned disconnects and durable server-side VPN peer reconciliation."""

import asyncio
import logging
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError

from prettylisavpn.auth.session_service import AuthenticatedSessionHandler
from prettylisavpn.config import Settings
from prettylisavpn.connections import Postgres
from prettylisavpn.vpn_nodes.agent import NodeAgentPeerPort, NodeAgentUnavailableError
from prettylisavpn.vpn_nodes.domain import VpnNode
from prettylisavpn.vpn_nodes.repository import VpnNodeRepository
from prettylisavpn.vpn_sessions.domain import VpnSession, VpnSessionStatus
from prettylisavpn.vpn_sessions.repository import VpnSessionRepository

logger = logging.getLogger(__name__)


class OwnedVpnSessionNotFoundError(LookupError):
    pass


class VpnTerminationUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class TerminatedVpnSession:
    session_id: UUID
    status: VpnSessionStatus


class VpnTerminationHandler(Protocol):
    async def disconnect(self, access_token: str, session_id: UUID) -> TerminatedVpnSession: ...


class VpnSessionReconcilerPort(Protocol):
    async def run(self, stop: asyncio.Event) -> None: ...


class VpnSessionTerminationService:
    def __init__(
        self,
        postgres: Postgres,
        authenticated_sessions: AuthenticatedSessionHandler,
        agent: NodeAgentPeerPort,
    ) -> None:
        self._postgres = postgres
        self._authenticated_sessions = authenticated_sessions
        self._agent = agent

    async def disconnect(self, access_token: str, session_id: UUID) -> TerminatedVpnSession:
        identity = await self._authenticated_sessions.authenticate(access_token)
        now = datetime.now(UTC)
        try:
            async with self._postgres.session() as database_session:
                async with database_session.begin():
                    sessions = VpnSessionRepository(database_session)
                    current = await sessions.get_owned_for_update(
                        session_id, identity.user_id, identity.device_id
                    )
                    if current is None:
                        raise OwnedVpnSessionNotFoundError
                    if current.status in (VpnSessionStatus.PENDING, VpnSessionStatus.ACTIVE):
                        current = replace(
                            current,
                            status=VpnSessionStatus.DISCONNECTED,
                            disconnected_at=now,
                            updated_at=now,
                        )
                        await sessions.update(current)
                    node = await VpnNodeRepository(database_session).get(current.vpn_node_id)
                    if node is None:
                        raise VpnTerminationUnavailableError
        except (OwnedVpnSessionNotFoundError, VpnTerminationUnavailableError):
            raise
        except SQLAlchemyError:
            raise VpnTerminationUnavailableError from None

        if current.peer_removed_at is None:
            await remove_and_record_peer(self._postgres, self._agent, current, node)
        return TerminatedVpnSession(current.id, current.status)


class UnavailableVpnTerminationService:
    def __init__(self, authenticated_sessions: AuthenticatedSessionHandler) -> None:
        self._authenticated_sessions = authenticated_sessions

    async def disconnect(self, access_token: str, session_id: UUID) -> TerminatedVpnSession:
        await self._authenticated_sessions.authenticate(access_token)
        raise VpnTerminationUnavailableError


class VpnSessionReconciler:
    """Replays durable cleanup intent and detects missing peers after restarts/outages."""

    def __init__(self, postgres: Postgres, agent: NodeAgentPeerPort, settings: Settings) -> None:
        self._postgres = postgres
        self._agent = agent
        self._poll_interval = settings.vpn_session_reconcile_interval_seconds

    async def run_once(self) -> None:
        now = datetime.now(UTC)
        try:
            async with self._postgres.session() as database_session:
                async with database_session.begin():
                    repository = VpnSessionRepository(database_session)
                    await repository.expire_allocations(now)
                cleanup = await repository.list_cleanup_pending()
                active = await repository.list_active()
        except SQLAlchemyError:
            logger.error("vpn_session_reconciliation_persistence_unavailable")
            return

        for vpn_session in cleanup:
            node = await self._node(vpn_session.vpn_node_id)
            if node is not None:
                await remove_and_record_peer(self._postgres, self._agent, vpn_session, node)

        for vpn_session in active:
            node = await self._node(vpn_session.vpn_node_id)
            if node is None:
                continue
            try:
                exists = await self._agent.peer_exists(
                    node, vpn_session.client_wireguard_public_key
                )
            except NodeAgentUnavailableError:
                continue
            if not exists:
                await self._mark_missing(vpn_session.id)

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            await self.run_once()
            try:
                await asyncio.wait_for(stop.wait(), timeout=self._poll_interval)
            except TimeoutError:
                pass

    async def _node(self, node_id: UUID) -> VpnNode | None:
        try:
            async with self._postgres.session() as session:
                return await VpnNodeRepository(session).get(node_id)
        except SQLAlchemyError:
            return None

    async def _mark_missing(self, session_id: UUID) -> None:
        now = datetime.now(UTC)
        try:
            async with self._postgres.session() as database_session:
                async with database_session.begin():
                    repository = VpnSessionRepository(database_session)
                    current = await repository.get_for_update(session_id)
                    if current is None or current.status is not VpnSessionStatus.ACTIVE:
                        return
                    await repository.update(
                        replace(
                            current,
                            status=VpnSessionStatus.FAILED,
                            peer_removed_at=now,
                            updated_at=now,
                        )
                    )
        except SQLAlchemyError:
            logger.error("vpn_session_missing_peer_persistence_unavailable")


async def remove_and_record_peer(
    postgres: Postgres,
    agent: NodeAgentPeerPort,
    vpn_session: VpnSession,
    node: VpnNode,
) -> None:
    try:
        async with postgres.session() as database_session:
            async with database_session.begin():
                repository = VpnSessionRepository(database_session)
                current = await repository.get_for_update(vpn_session.id)
                if current is None or current.peer_removed_at is not None:
                    return
                if current.status in (VpnSessionStatus.PENDING, VpnSessionStatus.ACTIVE):
                    return
                await repository.acquire_peer_lock(current.client_wireguard_public_key)
                try:
                    await agent.remove_peer(node, current.client_wireguard_public_key)
                except NodeAgentUnavailableError:
                    return  # Intent is committed already; retry after node recovery.
                now = datetime.now(UTC)
                await repository.update(replace(current, peer_removed_at=now, updated_at=now))
    except SQLAlchemyError:
        logger.error("vpn_session_peer_cleanup_persistence_unavailable")
