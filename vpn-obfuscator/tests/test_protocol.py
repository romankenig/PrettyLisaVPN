import base64

import pytest
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

from prettylisavpn_obfuscator.protocol import (
    AuthenticationError,
    MalformedPacketError,
    OversizedPacketError,
    UnsupportedVersionError,
    V1ObfuscationTransport,
    decode_secret,
)

KEY = bytes(range(32))
COMPATIBILITY_PACKET = bytes.fromhex("010000005072657474794c6973612d7631")
COMPATIBILITY_ENVELOPE = bytes.fromhex(
    "01a0a1a2a3a4a5a6a7a8a9aaab0cba795f4de692dfc57b876db0938e9ab0"
    "28e24fb2989357412e2cd8a5a754bed05f8bc4bd651e9b7b96a0"
)


def test_round_trip_hides_raw_wireguard_header() -> None:
    codec = V1ObfuscationTransport(KEY)
    wireguard_packet = bytes([1, 0, 0, 0]) + b"wireguard-handshake"

    encoded = codec.encode(wireguard_packet)

    assert encoded[0] == 1
    assert not encoded.startswith(wireguard_packet)
    assert wireguard_packet not in encoded
    assert codec.decode(encoded) == wireguard_packet


def test_matches_stage_3ac_rust_compatibility_vector() -> None:
    nonce = bytes(range(0xA0, 0xAC))
    padding = bytes(range(0xF0, 0xF8))
    codec = V1ObfuscationTransport(
        KEY,
        random_bytes=lambda size: nonce if size == 12 else padding,
        random_below=lambda limit: 8,
    )

    assert codec.encode(COMPATIBILITY_PACKET) == COMPATIBILITY_ENVELOPE
    assert codec.decode(COMPATIBILITY_ENVELOPE) == COMPATIBILITY_PACKET


def test_random_padding_varies_envelope_size() -> None:
    padding_lengths = iter([0, 17])
    codec = V1ObfuscationTransport(
        KEY,
        random_bytes=lambda size: bytes([7]) * size,
        random_below=lambda limit: next(padding_lengths),
    )

    first = codec.encode(b"same packet")
    second = codec.encode(b"same packet")

    assert len(second) - len(first) == 17
    assert codec.decode(first) == codec.decode(second) == b"same packet"


def test_rejects_invalid_authentication() -> None:
    codec = V1ObfuscationTransport(KEY)
    encoded = bytearray(codec.encode(b"authenticated"))
    encoded[-1] ^= 1

    with pytest.raises(AuthenticationError):
        codec.decode(bytes(encoded))


def test_rejects_unsupported_version_before_decryption() -> None:
    codec = V1ObfuscationTransport(KEY)
    encoded = bytearray(codec.encode(b"versioned"))
    encoded[0] = 2

    with pytest.raises(UnsupportedVersionError):
        codec.decode(bytes(encoded))


def test_rejects_malformed_packets() -> None:
    codec = V1ObfuscationTransport(KEY)

    with pytest.raises(MalformedPacketError):
        codec.decode(b"\x01too-short")

    nonce = bytes(12)
    plaintext = (20).to_bytes(2, "big") + b"short"
    malformed = b"\x01" + nonce + ChaCha20Poly1305(KEY).encrypt(nonce, plaintext, b"\x01")
    with pytest.raises(MalformedPacketError):
        codec.decode(malformed)


def test_rejects_oversized_packets() -> None:
    codec = V1ObfuscationTransport(KEY, max_packet_size=32, max_padding_size=0)

    with pytest.raises(OversizedPacketError):
        codec.encode(bytes(33))


def test_decodes_only_canonical_256_bit_secret() -> None:
    encoded = base64.b64encode(KEY).decode("ascii")
    assert decode_secret(encoded) == KEY

    with pytest.raises(ValueError):
        decode_secret("not-base64")
    with pytest.raises(ValueError):
        decode_secret(base64.b64encode(bytes(31)).decode("ascii"))
