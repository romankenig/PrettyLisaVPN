"""Deployment declarations do not imply demonstrated Internet connectivity."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from ipaddress import IPv4Address
from uuid import uuid4

import pytest
from pydantic import ValidationError
from test_vpn_nodes import make_node

from prettylisavpn.vpn_nodes.availability import NodeUnavailabilityReason, VpnNodeAvailabilityPolicy
from prettylisavpn.vpn_nodes.deployment import (
    DeployedConnectionProfile,
    ProfileEvidence,
    ProfileHealth,
)
from prettylisavpn.vpn_nodes.import_profiles import DeploymentImport, validate_import
from prettylisavpn.vpn_sessions.connection import deployed_session_candidates


def sample(node, now, **changes):
    evidence = ProfileEvidence(
        node_id=node.id,
        profile="wg-direct",
        configuration_sha256="a" * 64,
        checked_at=now,
        transport_established=True,
        tunnel=True,
        dns=True,
        https=True,
        internet=True,
        route_verified=True,
        egress_ip=node.public_ipv4,
    )
    values = dict(
        id="wg-direct",
        protocol="WIREGUARD",
        transport="UDP",
        port=node.wireguard_port,
        encryption_mode="WIREGUARD",
        obfuscation_mode="NONE",
        enabled=True,
        free_available=False,
        configuration_sha256="a" * 64,
        health_status="E2E_VERIFIED",
        evidence=evidence,
    )
    return DeployedConnectionProfile(**(values | changes))


@pytest.mark.parametrize("status", list(ProfileHealth))
def test_status_is_not_enough(status):
    node = make_node()
    now = datetime.now(UTC)
    profile = sample(node, now, health_status=status)
    assert profile.usable(node.id, node.public_ipv4, now) == (status is ProfileHealth.E2E_VERIFIED)


@pytest.mark.parametrize(
    "field", ["transport_established", "tunnel", "dns", "https", "internet", "route_verified"]
)
def test_all_stages_are_required(field):
    node = make_node()
    now = datetime.now(UTC)
    profile = sample(node, now)
    evidence = profile.evidence.model_copy(update={field: False})
    profile = profile.model_copy(update={"evidence": evidence})
    assert not profile.usable(node.id, node.public_ipv4, now)
    with pytest.raises(ValueError):
        validate_import(node, DeploymentImport(node_id=node.id, profiles=(profile,)), now)


@pytest.mark.parametrize(
    "change",
    [
        {"profile": "other"},
        {"configuration_sha256": "b" * 64},
        {"node_id": uuid4()},
        {"egress_ip": IPv4Address("192.0.2.1")},
        {"checked_at": datetime.now(UTC) + timedelta(days=2)},
    ],
)
def test_identity_revision_egress_and_freshness(change):
    node = make_node()
    now = datetime.now(UTC)
    profile = sample(node, now)
    profile = profile.model_copy(update={"evidence": profile.evidence.model_copy(update=change)})
    assert not profile.usable(node.id, node.public_ipv4, now)


def test_unknown_and_secrets_rejected():
    node = make_node()
    with pytest.raises(ValidationError):
        sample(node, datetime.now(UTC), private_key="must-not-be-in-metadata")


def test_import_and_verified_projection():
    node = make_node()
    now = datetime.now(UTC)
    profile = sample(node, now)
    assert node.verified_profiles(now) == ()
    updated = validate_import(node, DeploymentImport(node_id=node.id, profiles=(profile,)), now)
    assert updated.verified_profiles(now) == (profile,)
    # An unchanged deployed revision retains its demonstrated capability. This
    # does not waive live node-health or per-connection Internet verification.
    assert updated.verified_profiles(now + timedelta(days=2)) == (profile,)
    with pytest.raises(ValueError):
        validate_import(
            node, DeploymentImport(node_id=node.id, profiles=(profile,)), now + timedelta(days=2)
        )


def test_verified_wireguard_uses_actual_endpoint_instead_of_native_udp443():
    now = datetime.now(UTC)
    node = make_node(wireguard_port=51820)
    assert deployed_session_candidates(node, now) is None
    node = replace(node, deployed_profiles=(sample(node, now),))
    candidates = deployed_session_candidates(node, now)
    assert len(candidates) == 1
    assert (candidates[0].transport, candidates[0].port, candidates[0].obfuscation_mode) == (
        "UDP",
        51820,
        "NONE",
    )
    failed = replace(node, deployed_profiles=(sample(node, now, health_status="E2E_FAILED"),))
    assert deployed_session_candidates(failed, now) == ()
    assert (
        VpnNodeAvailabilityPolicy(timedelta(minutes=5)).evaluate(failed, now).reason
        is NodeUnavailabilityReason.NO_RUNNABLE_PROFILE
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"enabled": False},
        {"port": 5443},
        {
            "protocol": "OPENVPN",
            "transport": "TCP",
            "port": 443,
            "encryption_mode": "TLS_1_3_AES_256_GCM",
        },
        {"obfuscation_mode": "SIMPLE_PACKET_WRAPPER_V1", "port": 5443},
    ],
)
def test_no_unprovisioned_or_disabled_profile_advertised_by_wireguard_session(changes):
    now = datetime.now(UTC)
    node = make_node()
    node = replace(node, deployed_profiles=(sample(node, now, **changes),))
    assert deployed_session_candidates(node, now) == ()


def test_empty_import_cannot_restore_unverified_legacy_policy():
    with pytest.raises(ValidationError):
        DeploymentImport(node_id=uuid4(), profiles=())
