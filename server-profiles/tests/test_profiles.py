import sys
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from probe import classify
from profiles import load, revision, validate, verified
from render import render


@pytest.fixture
def manifest():
    return load(Path(__file__).resolve().parents[1] / "examples/node.json")


@pytest.mark.parametrize("index", range(5))
def test_supported_combinations(manifest, index):
    p = manifest["profiles"][index]
    p["enabled"] = True
    manifest["profiles"] = [p]
    validate(manifest)
    result = render(manifest)
    assert f"--dport {p['port']}" in result["routing.sh"]
    assert "-F" not in result["routing.sh"]
    assert "-P" not in result["routing.sh"]
    assert "--dport 22" not in result["routing.sh"]


def test_disabled_never_opens_ports_or_creates_services(manifest):
    for p in manifest["profiles"]:
        p["enabled"] = False
    files = render(manifest)
    assert "--dport" not in files["routing.sh"]
    assert len([name for name in files if name.endswith(".service")]) == 1


def test_socket_collision(manifest):
    manifest["profiles"][3]["enabled"] = True
    with pytest.raises(ValueError, match="collision"):
        validate(manifest)


@pytest.mark.parametrize("reverse", [False, True])
def test_overlap_order_independent(manifest, reverse):
    a, b = deepcopy(manifest["profiles"][0]), deepcopy(manifest["profiles"][2])
    b.update(subnet=a["subnet"], gateway=a["gateway"])
    manifest["profiles"] = [b, a] if reverse else [a, b]
    with pytest.raises(ValueError, match="overlapping"):
        validate(manifest)


@pytest.mark.parametrize(
    "field,value",
    [
        ("transport", "TCP"),
        ("obfuscation_mode", "TLS_TRANSPORT"),
        ("port", True),
        ("interface", "wg0;reboot"),
        ("mtu", 9000),
    ],
)
def test_reject_invalid(manifest, field, value):
    manifest["profiles"][0][field] = value
    with pytest.raises(ValueError):
        validate(manifest)


def evidence(manifest):
    return {
        "node_id": manifest["node_id"],
        "profile": "wg-direct",
        "configuration_sha256": revision(manifest),
        "checked_at": datetime.now(UTC).isoformat(),
        "status": "E2E_VERIFIED",
        "transport_established": True,
        "tunnel": True,
        "dns": True,
        "https": True,
        "internet": True,
        "route_verified": True,
        "egress_ip": manifest["public_ipv4"],
    }


def test_verified_requires_all_checks(manifest):
    report = evidence(manifest)
    assert verified(manifest, manifest["profiles"][0], report, datetime.now(UTC))
    for check in (
        "transport_established",
        "tunnel",
        "dns",
        "https",
        "internet",
        "route_verified",
    ):
        failed = {**report, check: False}
        assert not verified(
            manifest, manifest["profiles"][0], failed, datetime.now(UTC)
        )


@pytest.mark.parametrize(
    "status", ["UNTESTED", "UNIT_TESTED", "SERVER_READY", "E2E_FAILED"]
)
def test_readiness_is_not_e2e(manifest, status):
    report = evidence(manifest)
    report["status"] = status
    assert not verified(manifest, manifest["profiles"][0], report, datetime.now(UTC))


@pytest.mark.parametrize("hours", [-1, 25])
def test_expired_and_future_reports(manifest, hours):
    report = evidence(manifest)
    report["checked_at"] = (datetime.now(UTC) - timedelta(hours=hours)).isoformat()
    assert not verified(manifest, manifest["profiles"][0], report, datetime.now(UTC))


def test_configuration_change_invalidates_report(manifest):
    report = evidence(manifest)
    manifest["profiles"][0]["port"] = 5000
    assert not verified(manifest, manifest["profiles"][0], report, datetime.now(UTC))


def test_handshake_without_internet_is_failure():
    report = {
        "tunnel": True,
        "dns": False,
        "https": False,
        "internet": False,
        "route_verified": False,
    }
    assert classify(report, True)["status"] == "E2E_FAILED"


def test_internet_without_handshake_is_failure():
    report = {
        "tunnel": True,
        "dns": True,
        "https": True,
        "internet": True,
        "route_verified": True,
    }
    assert classify(report, False)["status"] == "E2E_FAILED"


def test_physical_interface_cannot_be_used_as_tunnel(manifest):
    manifest["profiles"][0]["interface"] = manifest["egress_interface"]
    with pytest.raises(ValueError, match="physical interface"):
        validate(manifest)
