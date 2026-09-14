"""Periodic authenticated VPN node health refresh loop."""

import asyncio
import logging
from datetime import timedelta
from typing import Protocol

from sqlalchemy.exc import SQLAlchemyError

from prettylisavpn.config import Settings
from prettylisavpn.connections import Postgres
from prettylisavpn.vpn_nodes.agent import NodeAgentHealthPort
from prettylisavpn.vpn_nodes.repository import VpnNodeRepository
from prettylisavpn.vpn_nodes.service import VpnNodeService

logger = logging.getLogger(__name__)


class NodeHealthMonitorPort(Protocol):
    async def run(self, stop: asyncio.Event) -> None: ...


class VpnNodeHealthMonitor:
    def __init__(self, postgres: Postgres, agent: NodeAgentHealthPort, settings: Settings) -> None:
        self._postgres = postgres
        self._agent = agent
        self._poll_interval = settings.vpn_node_health_poll_interval_seconds
        self._stale_timeout = timedelta(seconds=settings.vpn_node_stale_timeout_seconds)

    async def run_once(self) -> None:
        try:
            async with self._postgres.session() as session:
                nodes = await VpnNodeRepository(session).list_all()
            for node in nodes:
                async with self._postgres.session() as session:
                    service = VpnNodeService(
                        VpnNodeRepository(session), self._agent, self._stale_timeout
                    )
                    await service.refresh_health(node.id)
                    await session.commit()
        except SQLAlchemyError:
            logger.error("vpn_node_health_persistence_unavailable")

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            await self.run_once()
            try:
                await asyncio.wait_for(stop.wait(), timeout=self._poll_interval)
            except TimeoutError:
                pass
