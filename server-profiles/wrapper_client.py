"""Standalone SIMPLE_PACKET_WRAPPER_V1 client carrier for external testing.

Encryption/authentication belongs entirely to WireGuard. Loopback only; one
WireGuard client per process. No traffic payloads or addresses are logged.
"""

import argparse
import select
import socket

from prettylisavpn_obfuscator.providers import packet_provider


def serve(server: str, port: int, local_port: int) -> None:
    provider = packet_provider("SIMPLE_PACKET_WRAPPER_V1", 1, 1400)
    with (
        socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as local,
        socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as remote,
    ):
        local.bind(("127.0.0.1", local_port))
        remote.connect((server, port))
        peer = None
        while True:
            ready, _, _ = select.select([local, remote], [], [])
            for sock in ready:
                try:
                    if sock is local:
                        packet, origin = local.recvfrom(65535)
                        if peer is not None and peer != origin:
                            continue
                        framed = provider.encode(packet)
                        peer = origin
                        remote.send(framed)
                    else:
                        packet = provider.decode(remote.recv(65535))
                        if peer is not None:
                            local.sendto(packet, peer)
                except (ValueError, OSError):
                    continue


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("server")
    parser.add_argument("port", type=int)
    parser.add_argument("--local-port", type=int, default=51821)
    args = parser.parse_args()
    serve(args.server, args.port, args.local_port)
