import asyncio

import pytest

from prettylisavpn_obfuscator.config import Settings
from prettylisavpn_obfuscator.protocol import V1ObfuscationTransport
from prettylisavpn_obfuscator.providers import packet_provider
from prettylisavpn_obfuscator.server import ObfuscationServerProtocol

KEY = bytes(range(32))


class EchoProtocol(asyncio.DatagramProtocol):
    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        self.transport.sendto(data, addr)


class ClientProtocol(asyncio.DatagramProtocol):
    def __init__(
        self, packet: bytes, result: asyncio.Future[bytes], mode: str = "PRETTYLISA_V1"
    ) -> None:
        self.packet = packet
        self.result = result
        self.codec = (
            V1ObfuscationTransport(KEY)
            if mode == "PRETTYLISA_V1"
            else packet_provider(mode, 0 if mode == "NONE" else 1, 1400)
        )

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport
        self.transport.sendto(self.codec.encode(self.packet))

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        del addr
        if not self.result.done():
            self.result.set_result(self.codec.decode(data))


@pytest.mark.parametrize("mode", ["PRETTYLISA_V1", "NONE", "SIMPLE_PACKET_WRAPPER_V1"])
def test_forwards_multiple_clients_and_returns_replies(mode: str) -> None:
    async def scenario() -> None:
        loop = asyncio.get_running_loop()
        echo_transport, _ = await loop.create_datagram_endpoint(
            EchoProtocol,
            local_addr=("127.0.0.1", 0),
        )
        echo_port = echo_transport.get_extra_info("sockname")[1]
        settings = Settings(
            secret=KEY,
            obfuscation_mode=mode,
            obfuscation_version=0 if mode == "NONE" else 1,
            bind_host="127.0.0.1",
            bind_port=0,
            wireguard_host="127.0.0.1",
            wireguard_port=echo_port,
            max_packet_size=4_096,
            max_padding_size=255,
            max_clients=8,
            client_idle_timeout_seconds=180,
            status_interval_seconds=60,
        )
        server = ObfuscationServerProtocol(settings)
        public_transport, _ = await loop.create_datagram_endpoint(
            lambda: server,
            local_addr=("127.0.0.1", 0),
        )
        public_endpoint = public_transport.get_extra_info("sockname")
        first_result: asyncio.Future[bytes] = loop.create_future()
        second_result: asyncio.Future[bytes] = loop.create_future()
        first_transport, _ = await loop.create_datagram_endpoint(
            lambda: ClientProtocol(b"first-wireguard-packet", first_result, mode),
            remote_addr=public_endpoint,
        )
        second_transport, _ = await loop.create_datagram_endpoint(
            lambda: ClientProtocol(b"second-wireguard-packet", second_result, mode),
            remote_addr=public_endpoint,
        )
        try:
            replies = await asyncio.wait_for(
                asyncio.gather(first_result, second_result),
                timeout=2,
            )
            assert replies == [b"first-wireguard-packet", b"second-wireguard-packet"]
            assert server.counters.accepted_packets == 2
            assert server.counters.wireguard_replies == 2
            if mode == "SIMPLE_PACKET_WRAPPER_V1":
                before = len(server._clients)
                server.datagram_received(b"malformed-frame", ("127.0.0.1", 12345))
                assert server.counters.rejected_packets == 1
                assert len(server._clients) == before
            for session in server._clients.values():
                session.last_seen = 0
            server.expire_idle_clients()
            assert not server._clients
            reconnect_result: asyncio.Future[bytes] = loop.create_future()
            reconnect_transport, _ = await loop.create_datagram_endpoint(
                lambda: ClientProtocol(b"reconnect", reconnect_result, mode),
                remote_addr=public_endpoint,
            )
            try:
                assert await asyncio.wait_for(reconnect_result, 2) == b"reconnect"
            finally:
                reconnect_transport.close()
        finally:
            first_transport.close()
            second_transport.close()
            echo_transport.close()
            await server.close()

    asyncio.run(scenario())
