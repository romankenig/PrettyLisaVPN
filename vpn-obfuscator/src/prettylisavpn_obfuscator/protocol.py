"""Versioned packet encoding isolated from UDP forwarding."""

from __future__ import annotations

import base64
import binascii
import secrets
from collections.abc import Callable

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

PROTOCOL_VERSION = 1
KEY_SIZE = 32
NONCE_SIZE = 12
TAG_SIZE = 16
LENGTH_SIZE = 2
HEADER_SIZE = 1 + NONCE_SIZE
MAX_UDP_DATAGRAM_SIZE = 65_507


class ObfuscationError(ValueError):
    """A public datagram cannot be safely decoded."""


class UnsupportedVersionError(ObfuscationError):
    """The packet uses an unsupported protocol version."""


class AuthenticationError(ObfuscationError):
    """AEAD authentication failed."""


class MalformedPacketError(ObfuscationError):
    """The packet envelope is structurally invalid."""


class OversizedPacketError(ObfuscationError):
    """The encoded or decoded packet exceeds configured bounds."""


class ObfuscationTransport:
    """Encode and decode opaque UDP payloads."""

    def encode(self, packet: bytes) -> bytes:
        raise NotImplementedError

    def decode(self, packet: bytes) -> bytes:
        raise NotImplementedError


class V1ObfuscationTransport(ObfuscationTransport):
    """Version 1 envelope using ChaCha20-Poly1305 and random padding."""

    def __init__(
        self,
        key: bytes,
        *,
        max_packet_size: int = 4_096,
        max_padding_size: int = 255,
        random_bytes: Callable[[int], bytes] = secrets.token_bytes,
        random_below: Callable[[int], int] = secrets.randbelow,
    ) -> None:
        if len(key) != KEY_SIZE:
            raise ValueError("obfuscation key must contain exactly 32 bytes")
        if not 1 <= max_packet_size <= 65_535:
            raise ValueError("max packet size must be between 1 and 65535")
        if not 0 <= max_padding_size <= 65_535:
            raise ValueError("max padding size must be between 0 and 65535")
        maximum_envelope = HEADER_SIZE + LENGTH_SIZE + max_packet_size + max_padding_size + TAG_SIZE
        if maximum_envelope > MAX_UDP_DATAGRAM_SIZE:
            raise ValueError("configured envelope exceeds the maximum UDP datagram size")
        self._aead = ChaCha20Poly1305(key)
        self._max_packet_size = max_packet_size
        self._max_padding_size = max_padding_size
        self._max_envelope_size = maximum_envelope
        self._random_bytes = random_bytes
        self._random_below = random_below

    def encode(self, packet: bytes) -> bytes:
        if not packet:
            raise MalformedPacketError("empty inner packet")
        if len(packet) > self._max_packet_size:
            raise OversizedPacketError("inner packet exceeds configured limit")
        padding_size = self._random_below(self._max_padding_size + 1)
        nonce = self._random_bytes(NONCE_SIZE)
        if len(nonce) != NONCE_SIZE:
            raise RuntimeError("random nonce source returned an invalid length")
        plaintext = (
            len(packet).to_bytes(LENGTH_SIZE, "big") + packet + self._random_bytes(padding_size)
        )
        version = bytes([PROTOCOL_VERSION])
        return version + nonce + self._aead.encrypt(nonce, plaintext, version)

    def decode(self, packet: bytes) -> bytes:
        minimum_size = HEADER_SIZE + LENGTH_SIZE + 1 + TAG_SIZE
        if len(packet) < minimum_size:
            raise MalformedPacketError("truncated envelope")
        if len(packet) > self._max_envelope_size:
            raise OversizedPacketError("envelope exceeds configured limit")
        version = packet[0]
        if version != PROTOCOL_VERSION:
            raise UnsupportedVersionError("unsupported protocol version")
        nonce = packet[1:HEADER_SIZE]
        try:
            plaintext = self._aead.decrypt(nonce, packet[HEADER_SIZE:], packet[:1])
        except InvalidTag as error:
            raise AuthenticationError("packet authentication failed") from error
        if len(plaintext) < LENGTH_SIZE + 1:
            raise MalformedPacketError("missing inner packet")
        packet_size = int.from_bytes(plaintext[:LENGTH_SIZE], "big")
        if packet_size == 0:
            raise MalformedPacketError("empty inner packet")
        if packet_size > self._max_packet_size:
            raise OversizedPacketError("inner packet exceeds configured limit")
        packet_end = LENGTH_SIZE + packet_size
        if packet_end > len(plaintext):
            raise MalformedPacketError("declared inner length exceeds envelope")
        return plaintext[LENGTH_SIZE:packet_end]


def decode_secret(value: str) -> bytes:
    """Decode a canonical base64 256-bit configured secret."""
    try:
        secret = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError("obfuscation secret must be valid base64") from error
    if len(secret) != KEY_SIZE:
        raise ValueError("obfuscation secret must decode to exactly 32 bytes")
    if base64.b64encode(secret).decode("ascii") != value:
        raise ValueError("obfuscation secret must use canonical base64 encoding")
    return secret
