"""Authenticated read model for reconciling a device's current VPN session."""

from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy.exc import SQLAlchemyError

from prettylisavpn.auth.session_service import AuthenticatedSessionHandler
from prettylisavpn.config import Settings
from prettylisavpn.connections import Postgres
from prettylisavpn.vpn_nodes.repository import VpnNodeRepository
from prettylisavpn.vpn_sessions.connection import ActiveVpnTransport
from prettylisavpn.vpn_sessions.domain import VpnSessionStatus
from prettylisavpn.vpn_sessions.repository import VpnSessionRepository


class VpnSessionStatusUnavailableError(RuntimeError):
    pass


class VpnSessionStatusHandler(Protocol):
    async def current(self, access_token: str) -> ActiveVpnTransport | None: ...


class VpnSessionStatusService:
    def __init__(
        self,
        postgres: Postgres,
        authenticated_sessions: AuthenticatedSessionHandler,
        settings: Settings,
    ) -> None:
        self._postgres = postgres
        self._authenticated_sessions = authenticated_sessions
        self._dns = tuple(settings.vpn_client_dns)
        self._allowed_ips = tuple(settings.vpn_client_allowed_ips)

    async def current(self, access_token: str) -> ActiveVpnTransport | None:
        identity = await self._authenticated_sessions.authenticate(access_token)
        try:
            async with self._postgres.session() as database_session:
                vpn_session = await VpnSessionRepository(database_session).get_live_for_device(
                    identity.device_id, datetime.now(UTC)
                )
                if vpn_session is None or vpn_session.status is not VpnSessionStatus.ACTIVE:
                    return None
                node = await VpnNodeRepository(database_session).get(vpn_session.vpn_node_id)
                if node is None:
                    raise VpnSessionStatusUnavailableError
                return ActiveVpnTransport(
                    session_id=vpn_session.id,
                    node_id=node.id,
                    country_code=node.country_code,
                    endpoint_ipv4=node.public_ipv4,
                    endpoint_port=node.wireguard_port,
                    server_public_key=node.wireguard_public_key,
                    client_ipv4=vpn_session.allocated_client_ipv4,
                    dns=self._dns,
                    allowed_ips=self._allowed_ips,
                    expires_at=vpn_session.expires_at,
                )
        except VpnSessionStatusUnavailableError:
            raise
        except SQLAlchemyError:
            raise VpnSessionStatusUnavailableError from None
