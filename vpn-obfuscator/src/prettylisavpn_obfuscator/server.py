"""Concurrent UDP forwarding between public obfuscation clients and local WireGuard."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from dataclasses import dataclass

from .config import Settings
from .logging import log_event
from .protocol import ObfuscationError, V1ObfuscationTransport

ClientAddress = tuple[str, int]


@dataclass
class _ClientSession:
    transport: asyncio.DatagramTransport
    last_seen: float


@dataclass
class ServerCounters:
    accepted_packets: int = 0
    rejected_packets: int = 0
    wireguard_replies: int = 0
    dropped_packets: int = 0


class _WireGuardReplyProtocol(asyncio.DatagramProtocol):
    def __init__(self, server: ObfuscationServerProtocol, client: ClientAddress) -> None:
        self._server = server
        self._client = client

    def datagram_received(self, data: bytes, addr: ClientAddress) -> None:
        del addr
        self._server.forward_wireguard_reply(self._client, data)

    def error_received(self, exc: Exception) -> None:
        self._server.record_upstream_error(exc)


class ObfuscationServerProtocol(asyncio.DatagramProtocol):
    """Public listener with one connected loopback UDP socket per client endpoint."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._codec = V1ObfuscationTransport(
            settings.secret,
            max_packet_size=settings.max_packet_size,
            max_padding_size=settings.max_padding_size,
        )
        self._public_transport: asyncio.DatagramTransport | None = None
        self._clients: dict[ClientAddress, _ClientSession] = {}
        self._pending: dict[ClientAddress, list[bytes]] = {}
        self._tasks: set[asyncio.Task[None]] = set()
        self.counters = ServerCounters()
        self._logger = logging.getLogger("prettylisavpn.obfuscator")

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        if not isinstance(transport, asyncio.DatagramTransport):
            raise RuntimeError("obfuscator requires a datagram transport")
        self._public_transport = transport
        log_event(
            self._logger,
            logging.INFO,
            "obfuscator_started",
            bind_host=self._settings.bind_host,
            bind_port=self._settings.bind_port,
            wireguard_host=self._settings.wireguard_host,
            wireguard_port=self._settings.wireguard_port,
            protocol_version=1,
        )

    def datagram_received(self, data: bytes, addr: ClientAddress) -> None:
        try:
            decoded = self._codec.decode(data)
        except ObfuscationError:
            self.counters.rejected_packets += 1
            return
        self.counters.accepted_packets += 1
        session = self._clients.get(addr)
        if session is not None:
            session.last_seen = time.monotonic()
            session.transport.sendto(decoded)
            return
        queued = self._pending.get(addr)
        if queued is not None:
            if len(queued) >= 64:
                self.counters.dropped_packets += 1
            else:
                queued.append(decoded)
            return
        if len(self._clients) + len(self._pending) >= self._settings.max_clients:
            self.counters.dropped_packets += 1
            return
        self._pending[addr] = [decoded]
        task = asyncio.create_task(self._create_client_session(addr))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _create_client_session(self, client: ClientAddress) -> None:
        loop = asyncio.get_running_loop()
        try:
            transport, _ = await loop.create_datagram_endpoint(
                lambda: _WireGuardReplyProtocol(self, client),
                local_addr=(self._settings.wireguard_host, 0),
                remote_addr=(self._settings.wireguard_host, self._settings.wireguard_port),
            )
        except OSError:
            queued = self._pending.pop(client, [])
            self.counters.dropped_packets += len(queued)
            log_event(self._logger, logging.ERROR, "wireguard_transport_unavailable")
            return
        if not isinstance(transport, asyncio.DatagramTransport):
            transport.close()
            self._pending.pop(client, None)
            self.counters.dropped_packets += 1
            return
        queued = self._pending.pop(client, [])
        self._clients[client] = _ClientSession(transport, time.monotonic())
        for packet in queued:
            transport.sendto(packet)
        log_event(
            self._logger,
            logging.INFO,
            "client_transport_created",
            active_clients=len(self._clients),
        )

    def forward_wireguard_reply(self, client: ClientAddress, packet: bytes) -> None:
        session = self._clients.get(client)
        if session is None or self._public_transport is None:
            self.counters.dropped_packets += 1
            return
        try:
            encoded = self._codec.encode(packet)
        except ObfuscationError:
            self.counters.dropped_packets += 1
            return
        session.last_seen = time.monotonic()
        self.counters.wireguard_replies += 1
        self._public_transport.sendto(encoded, client)

    def record_upstream_error(self, exc: Exception) -> None:
        del exc
        self.counters.dropped_packets += 1
        log_event(self._logger, logging.WARNING, "wireguard_transport_error")

    def expire_idle_clients(self) -> None:
        deadline = time.monotonic() - self._settings.client_idle_timeout_seconds
        expired = [
            client for client, session in self._clients.items() if session.last_seen < deadline
        ]
        for client in expired:
            self._clients.pop(client).transport.close()
        if expired:
            log_event(
                self._logger,
                logging.INFO,
                "client_transports_expired",
                expired_clients=len(expired),
                active_clients=len(self._clients),
            )

    def log_status(self) -> None:
        log_event(
            self._logger,
            logging.INFO,
            "obfuscator_status",
            active_clients=len(self._clients),
            accepted_packets=self.counters.accepted_packets,
            rejected_packets=self.counters.rejected_packets,
            wireguard_replies=self.counters.wireguard_replies,
            dropped_packets=self.counters.dropped_packets,
        )

    async def close(self) -> None:
        if self._public_transport is not None:
            self._public_transport.close()
        for session in self._clients.values():
            session.transport.close()
        self._clients.clear()
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()


async def serve(settings: Settings, stop: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()
    protocol = ObfuscationServerProtocol(settings)
    await loop.create_datagram_endpoint(
        lambda: protocol,
        local_addr=(settings.bind_host, settings.bind_port),
    )

    async def maintenance() -> None:
        while not stop.is_set():
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=settings.status_interval_seconds)
            protocol.expire_idle_clients()
            protocol.log_status()

    maintenance_task = asyncio.create_task(maintenance())
    try:
        await stop.wait()
    finally:
        maintenance_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await maintenance_task
        await protocol.close()
