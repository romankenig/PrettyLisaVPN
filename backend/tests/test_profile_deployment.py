"""Deployment declarations do not imply demonstrated Internet connectivity."""

from datetime import UTC, datetime, timedelta
from ipaddress import IPv4Address
from uuid import uuid4

import pytest
from pydantic import ValidationError
from test_vpn_nodes import make_node

from prettylisavpn.vpn_nodes.deployment import (
    DeployedConnectionProfile,
    ProfileEvidence,
    ProfileHealth,
)
from prettylisavpn.vpn_nodes.import_profiles import DeploymentImport, validate_import


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
        {"checked_at": datetime.now(UTC) - timedelta(days=2)},
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
    assert updated.verified_profiles(now + timedelta(days=2)) == ()
