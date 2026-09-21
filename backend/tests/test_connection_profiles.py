"""Profile configuration validation and node eligibility boundaries."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError
from test_vpn_nodes import make_node

from prettylisavpn.vpn_nodes.availability import NodeUnavailabilityReason, VpnNodeAvailabilityPolicy
from prettylisavpn.vpn_nodes.profiles import PROFILES, NodeConnectionProfile, ProfileId
from prettylisavpn.vpn_sessions.protocol import ConnectionConfig


@pytest.mark.parametrize("profile_id", list(ProfileId))
def test_profile_instantiation_and_common_configuration(profile_id):
    capabilities = PROFILES[profile_id]
    declaration = NodeConnectionProfile(profile=profile_id, ports=(capabilities.default_port,))
    node_id = uuid4()
    config = ConnectionConfig.for_profile(profile_id, "DE", node_id)
    assert config.protocol == capabilities.protocol
    assert config.transport == capabilities.transport
    assert config.encryption_mode == capabilities.encryption
    assert config.port in declaration.ports
    assert config.node_id == node_id
    assert config.obfuscation_mode == "NONE"
    assert capabilities.supports_full_tunnel


@pytest.mark.parametrize("port", [0, 65536, -1, 1.5, True, "443"])
def test_rejects_invalid_ports(port):
    with pytest.raises(ValidationError):
        NodeConnectionProfile(profile=ProfileId.WIREGUARD_UDP, ports=(port,))
    with pytest.raises(ValueError):
        ConnectionConfig.for_profile(ProfileId.WIREGUARD_UDP, "DE", None, port)


@pytest.mark.parametrize("profile_id", list(ProfileId))
@pytest.mark.parametrize(
    "change",
    [
        {"transport": "INVALID"},
        {"encryption_mode": "TLS_1_2"},
        {"obfuscation_mode": "CUSTOM"},
        {"routing_mode": "SPLIT"},
        {"dns_mode": "SYSTEM"},
        {"mtu": 9000},
        {"country": "INVALID"},
    ],
)
def test_rejects_incompatible_configuration(profile_id, change):
    with pytest.raises(ValueError):
        replace(ConnectionConfig.for_profile(profile_id, "DE", None), **change)


def test_node_can_declare_multiple_profiles_with_distinct_ports():
    profiles = tuple(
        NodeConnectionProfile(profile=key, ports=(value.default_port,))
        for key, value in PROFILES.items()
    )
    node = make_node(connection_profiles=profiles)
    assert node.supported_profiles == profiles
    assert node.supports_current_session_protocol
    assert NodeConnectionProfile(profile=ProfileId.WIREGUARD_UDP, ports=(53, 443, 51820)).ports == (
        53,
        443,
        51820,
    )


def test_legacy_node_uses_its_existing_wireguard_port():
    node = make_node(wireguard_port=12345)
    assert node.supported_profiles == (
        NodeConnectionProfile(profile=ProfileId.WIREGUARD_UDP, ports=(12345,)),
    )


@pytest.mark.parametrize(
    "profiles",
    [
        (),
        (NodeConnectionProfile(profile=ProfileId.MASQUE_QUIC, ports=(443,)),),
        (NodeConnectionProfile(profile=ProfileId.WIREGUARD_UDP, ports=(53,)),),
    ],
)
def test_unprovisionable_nodes_are_not_advertised_or_selected(profiles):
    node = make_node(connection_profiles=profiles)
    result = VpnNodeAvailabilityPolicy(timedelta(seconds=90)).evaluate(node, datetime.now(UTC))
    assert result.reason is NodeUnavailabilityReason.NO_RUNNABLE_PROFILE
    assert not result.available


def test_rejects_duplicate_profiles_ports_and_unknown_fields():
    profile = NodeConnectionProfile(profile=ProfileId.WIREGUARD_UDP, ports=(51820,))
    with pytest.raises(ValueError):
        make_node(connection_profiles=(profile, profile))
    for data in [
        {"profile": "UNKNOWN", "ports": [443]},
        {"profile": "WIREGUARD_UDP", "ports": [443, 443]},
        {"profile": "WIREGUARD_UDP", "ports": []},
        {"profile": "OPENVPN_TLS_TCP", "ports": [80]},
        {"profile": "MASQUE_QUIC", "ports": [443], "private_key": "secret"},
    ]:
        with pytest.raises(ValidationError):
            NodeConnectionProfile.model_validate(data)
