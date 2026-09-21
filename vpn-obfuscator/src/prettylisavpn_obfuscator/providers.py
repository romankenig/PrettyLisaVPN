"""Independent keyless packet providers. They do not protect confidentiality or integrity."""

from typing import Protocol

from .protocol import MalformedPacketError, OversizedPacketError

HEADER_SIZE = 8
MAGIC = b"PLPW\x01\x00"


class ObfuscationProvider(Protocol):
    def encode(self, packet: bytes) -> bytes: ...
    def decode(self, packet: bytes) -> bytes: ...


class NoObfuscation:
    def __init__(self, max_datagram_size: int = 1400) -> None:
        if not 9 <= max_datagram_size <= 65507:
            raise ValueError("invalid datagram budget")
        self.maximum = max_datagram_size

    def encode(self, packet: bytes) -> bytes:
        if not packet:
            raise MalformedPacketError("empty packet")
        if len(packet) > self.maximum:
            raise OversizedPacketError("packet exceeds datagram budget")
        return packet

    def decode(self, packet: bytes) -> bytes:
        return self.encode(packet)


class SimplePacketWrapperV1(NoObfuscation):
    """Stateless 8-byte framing and fixed XOR transform, NOT cryptographic protection."""

    _translation = bytes(value ^ 0xA5 for value in range(256))

    def encode(self, packet: bytes) -> bytes:
        super().encode(packet)
        if len(packet) + HEADER_SIZE > self.maximum:
            raise OversizedPacketError("frame exceeds datagram budget")
        return MAGIC + len(packet).to_bytes(2, "big") + packet.translate(self._translation)

    def decode(self, packet: bytes) -> bytes:
        if len(packet) > self.maximum:
            raise OversizedPacketError("frame exceeds datagram budget")
        if (
            len(packet) <= HEADER_SIZE
            or packet[:6] != MAGIC
            or int.from_bytes(packet[6:8], "big") != len(packet) - HEADER_SIZE
        ):
            raise MalformedPacketError("invalid packet frame")
        return packet[HEADER_SIZE:].translate(self._translation)


def packet_provider(mode: str, version: int, max_datagram_size: int) -> ObfuscationProvider:
    providers = {("NONE", 0): NoObfuscation, ("SIMPLE_PACKET_WRAPPER_V1", 1): SimplePacketWrapperV1}
    provider = providers.get((mode, version))
    if provider is None:
        # TLS framing is owned by a TLS runtime, never synthesized as UDP packets.
        raise ValueError("unsupported packet provider")
    return provider(max_datagram_size)
