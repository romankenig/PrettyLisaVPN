from dataclasses import replace

import pytest

from prettylisavpn_obfuscator.config import Settings
from prettylisavpn_obfuscator.protocol import ObfuscationError
from prettylisavpn_obfuscator.providers import NoObfuscation, SimplePacketWrapperV1, packet_provider


@pytest.mark.parametrize("size", [1, 148, 1280, 1312, 1392, 4096, 65499])
def test_symmetry_large_packets_and_fixed_overhead(size):
    packet = bytes(index % 256 for index in range(size))
    codec = SimplePacketWrapperV1(65507)
    assert codec.decode(codec.encode(packet)) == packet
    assert len(codec.encode(packet)) == size + 8
    assert NoObfuscation(65507).decode(packet) == packet


def test_cross_language_vector_and_mtu_boundary():
    codec = SimplePacketWrapperV1(1400)
    assert codec.encode(bytes([0, 1, 255])) == bytes([80, 76, 80, 87, 1, 0, 0, 3, 165, 164, 90])
    assert len(codec.encode(bytes(1392))) == 1400
    with pytest.raises(ObfuscationError):
        codec.encode(bytes(1393))
    with pytest.raises(ObfuscationError):
        codec.decode(bytes(1401))


@pytest.mark.parametrize(
    "frame",
    [
        b"",
        bytes(8),
        bytes(9),
        b"PLPW\x02\x00\x00\x01x",
        b"PLPW\x01\x01\x00\x01x",
        b"PLPW\x01\x00\x00\x02x",
        b"PLPW\x01\x00\x00\x01xx",
    ],
)
def test_malformed_packets(frame):
    with pytest.raises(ObfuscationError):
        SimplePacketWrapperV1().decode(frame)


def test_loss_reordering_duplicates_and_reconnect_do_not_desynchronize():
    sender = SimplePacketWrapperV1()
    frames = [(index, sender.encode(bytes([index]))) for index in range(100) if index % 3]
    for index, frame in reversed(frames):
        receiver = SimplePacketWrapperV1()  # new connection / no shared state
        assert receiver.decode(frame) == receiver.decode(frame) == bytes([index])


def test_transform_is_not_authentication_or_encryption():
    codec = SimplePacketWrapperV1()
    encoded = bytearray(codec.encode(b"ciphertext"))
    encoded[-1] ^= 1
    # Integrity belongs to WireGuard, not this frame.
    assert codec.decode(bytes(encoded)) != b"ciphertext"


def test_explicit_modes_do_not_require_secrets(monkeypatch):
    monkeypatch.delenv("PRETTYLISA_OBFUSCATION_SECRET", raising=False)
    for mode, version in [("NONE", 0), ("SIMPLE_PACKET_WRAPPER_V1", 1)]:
        monkeypatch.setenv("PRETTYLISA_OBFUSCATION_MODE", mode)
        monkeypatch.setenv("PRETTYLISA_OBFUSCATION_VERSION", str(version))
        settings = Settings.from_environment()
        assert settings.secret == b""
        assert (
            packet_provider(mode, version, settings.max_datagram_size).decode(
                packet_provider(mode, version, settings.max_datagram_size).encode(b"packet")
            )
            == b"packet"
        )
        assert "secret-value" not in repr(replace(settings, secret=b"secret-value"))
    with pytest.raises(ValueError):
        packet_provider("TLS_TRANSPORT", 1, 1400)
