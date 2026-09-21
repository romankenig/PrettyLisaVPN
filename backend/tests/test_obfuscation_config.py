from dataclasses import replace

import pytest

from prettylisavpn.vpn_nodes.profiles import ProfileId
from prettylisavpn.vpn_sessions.protocol import ConnectionConfig


@pytest.mark.parametrize(
    ("profile", "mode", "version"),
    [
        (ProfileId.WIREGUARD_UDP, "NONE", 0),
        (ProfileId.WIREGUARD_UDP, "SIMPLE_PACKET_WRAPPER_V1", 1),
        (ProfileId.OPENVPN_TLS_TCP, "TLS_TRANSPORT", 1),
        (ProfileId.MASQUE_QUIC, "NONE", 0),
    ],
)
def test_obfuscation_does_not_change_vpn_encryption(profile, mode, version):
    original = ConnectionConfig.for_profile(profile, "DE", None)
    config = replace(original, obfuscation_mode=mode, obfuscation_version=version)
    assert config.encryption_mode == original.encryption_mode


@pytest.mark.parametrize(
    "change",
    [
        {"obfuscation_version": 2},
        {"obfuscation_version": True},
        {"transport": "TCP"},
        {"transport_parameters": {"max_datagram_size": 1319}},
        {"transport_parameters": {"max_datagram_size": 65508}},
        {"transport_parameters": {"private_key": "secret"}},
    ],
)
def test_invalid_wrapper_configuration(change):
    config = replace(
        ConnectionConfig.for_profile(ProfileId.WIREGUARD_UDP, "DE", None),
        obfuscation_mode="SIMPLE_PACKET_WRAPPER_V1",
        obfuscation_version=1,
    )
    with pytest.raises(ValueError):
        replace(config, **change)


def test_exact_mtu_boundary_and_quic_rejects_tls_records():
    replace(
        ConnectionConfig.for_profile(ProfileId.WIREGUARD_UDP, "DE", None),
        obfuscation_mode="SIMPLE_PACKET_WRAPPER_V1",
        obfuscation_version=1,
        transport_parameters={"max_datagram_size": 1320},
    )
    with pytest.raises(ValueError):
        replace(
            ConnectionConfig.for_profile(ProfileId.MASQUE_QUIC, "DE", None),
            obfuscation_mode="TLS_TRANSPORT",
            obfuscation_version=1,
        )
