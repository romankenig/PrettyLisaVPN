import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import probe as verifier
from profiles import load


@pytest.fixture
def checks(monkeypatch):
    manifest = load(Path(__file__).resolve().parents[1] / "examples/node.json")
    profile = manifest["profiles"][0]
    calls = []

    def run(*args):
        calls.append(args)
        if args[:3] == ("ip", "-j", "link"):
            return json.dumps([{"flags": ["UP"]}])
        if args[0] == "curl":
            return manifest["public_ipv4"] + "\n200"
        return json.dumps([{"dev": profile["interface"]}])

    monkeypatch.setattr(verifier, "run", run)
    monkeypatch.setattr(verifier, "resolve", lambda *args: "93.184.216.34")
    endpoints = [{"url": "https://health.example.test", "egress_response": "plain_ip"}]
    return manifest, profile, endpoints, calls, run


def test_probe_binds_dns_https_and_rechecks_routes(checks):
    manifest, profile, endpoints, calls, _ = checks
    result = verifier.classify(verifier.probe(manifest, profile, endpoints), True)
    assert result["status"] == "E2E_VERIFIED"
    curl = next(args for args in calls if args[0] == "curl")
    assert curl[curl.index("--interface") + 1] == profile["interface"]
    assert "--resolve" in curl and "--noproxy" in curl
    assert len([args for args in calls if "get" in args]) == 4
    assert "health.example.test" not in json.dumps(result)


@pytest.mark.parametrize(
    "stage", ["dns", "https", "route_before", "route_after", "egress"]
)
def test_handshake_never_overrides_internet_failure(checks, monkeypatch, stage):
    manifest, profile, endpoints, _, normal_run = checks
    route_count = 0

    def run(*args):
        nonlocal route_count
        if "get" in args:
            route_count += 1
            if stage == "route_before" or (stage == "route_after" and route_count >= 3):
                return '[{"dev":"eth0"}]'
        if args[0] == "curl":
            if stage == "https":
                raise subprocess.CalledProcessError(28, "curl")
            if stage == "egress":
                return "192.0.2.99\n200"
        return normal_run(*args)

    def failed_dns(*args):
        raise TimeoutError()

    monkeypatch.setattr(verifier, "run", run)
    if stage == "dns":
        monkeypatch.setattr(verifier, "resolve", failed_dns)
    result = verifier.classify(verifier.probe(manifest, profile, endpoints), True)
    assert result["tunnel"] and result["transport_established"]
    assert result["status"] == "E2E_FAILED"
    assert not result["internet"]
    expected = {
        "dns": "DNS_FAILED",
        "https": "HTTPS_CHECK_FAILED",
        "route_before": "ROUTE_LEAK_DETECTED",
        "route_after": "ROUTE_LEAK_DETECTED",
        "egress": "EGRESS_MISMATCH",
    }
    assert result["failure_code"] == expected[stage]


def test_second_health_endpoint_can_verify_same_profile(checks, monkeypatch):
    manifest, profile, endpoints, _, normal_run = checks
    attempts = 0

    def run(*args):
        nonlocal attempts
        if args[0] == "curl":
            attempts += 1
            if attempts == 1:
                return "unavailable\n503"
        return normal_run(*args)

    monkeypatch.setattr(verifier, "run", run)
    result = verifier.classify(verifier.probe(manifest, profile, endpoints * 2), True)
    assert attempts == 2
    assert result["status"] == "E2E_VERIFIED"
