"""Privileged helper safety using fake OS commands; no host networking changes."""

import json
import sys
import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from prettylisavpn.fleet.domain import Observation
from prettylisavpn.fleet.ubuntu import node

PUBKEY = "A" * 43 + "="


@pytest.fixture
def helper(monkeypatch, tmp_path):
    root, run = tmp_path / "etc", tmp_path / "run"
    root.mkdir()
    run.mkdir()
    monkeypatch.setattr(node, "ROOT", root)
    monkeypatch.setattr(node, "RUN", run)
    node.write(root / "state.json", json.dumps({"configuration": {"address": "10.88.0.1/24"}}))
    return root, run


def test_foreign_peers_prevent_synthetic_issuance(helper, monkeypatch):
    calls = []
    monkeypatch.setattr(node, "counts", lambda: (1, 1, 0, 0))
    monkeypatch.setattr(node, "peers", lambda: [PUBKEY])
    monkeypatch.setattr(node, "cmd", lambda args, **kwargs: calls.append(args))
    with pytest.raises(node.Failure, match="NODE_BUSY"):
        node.grant(
            {
                "id": str(uuid4()),
                "public_key": PUBKEY,
                "address": "10.88.0.254/32",
                "expires_at": (datetime.now(UTC) + timedelta(minutes=3)).isoformat(),
            }
        )
    assert calls == []


def test_monitor_coexists_with_owned_customer_without_changing_its_peer(helper, monkeypatch):
    root, run = helper
    clients = root / "clients"
    clients.mkdir()
    customer_key = "B" * 43 + "="
    customer_id, check_id = str(uuid4()), str(uuid4())
    journal = {"public_key": customer_key, "address": "10.88.0.2/32", "expires": time.time() + 180}
    node.write(clients / (customer_id + ".json"), json.dumps(journal))
    calls = []
    monkeypatch.setattr(node, "peers", lambda: [customer_key])
    monkeypatch.setattr(node, "cmd", lambda args, **kwargs: calls.append(args) or "")
    access = {
        "id": check_id,
        "public_key": PUBKEY,
        "address": "10.88.0.254/32",
        "expires_at": (datetime.now(UTC) + timedelta(minutes=3)).isoformat(),
    }
    assert node.grant(access)["granted"]
    assert node.read(clients / (customer_id + ".json")) == journal
    assert calls == [["wg", "set", node.WG, "peer", PUBKEY, "allowed-ips", "10.88.0.254/32"]]
    assert node.read(run / ("lease-" + check_id + ".json"))["public_key"] == PUBKEY
    with pytest.raises(node.Failure, match="ACCESS_CONFLICT"):
        node.grant({**access, "id": str(uuid4()), "public_key": customer_key})


def test_peer_journal_survives_failed_grant_for_autonomous_cleanup(helper, monkeypatch):
    _, run = helper
    identifier = str(uuid4())
    monkeypatch.setattr(node, "counts", lambda: (0, 0, 0, 0))
    monkeypatch.setattr(node, "peers", lambda: [])

    def failed(args, **kwargs):
        raise node.Failure("NODE_COMMAND_FAILED")

    monkeypatch.setattr(node, "cmd", failed)
    with pytest.raises(node.Failure):
        node.grant(
            {
                "id": identifier,
                "public_key": PUBKEY,
                "address": "10.88.0.254/32",
                "expires_at": (datetime.now(UTC) + timedelta(minutes=3)).isoformat(),
            }
        )
    assert node.read(run / f"lease-{identifier}.json")["public_key"] == PUBKEY


def test_cleanup_removes_only_expired_monitoring_state(helper, monkeypatch):
    _, run = helper
    expired, current, probe = str(uuid4()), str(uuid4()), str(uuid4())
    for identifier, expiry in ((expired, time.time() - 1), (current, time.time() + 200)):
        node.write(run / f"lease-{identifier}.json", json.dumps({"expires": expiry}))
    node.write(run / f"probe-{probe}.json", json.dumps({"expires": time.time() - 1}))
    revoked, disposed = [], []
    monkeypatch.setattr(node, "revoke", lambda identifier: revoked.append(identifier))
    monkeypatch.setattr(node, "dispose", lambda identifier: disposed.append(identifier))
    node.cleanup()
    assert revoked == [expired]
    assert disposed == [probe]


def test_passive_evidence_requires_fresh_handshake_and_bidirectional_growth(helper, monkeypatch):
    monkeypatch.setattr(node, "counts", lambda: (2, 1, 100, 200))
    first = Observation.model_validate(node.observe())
    assert first.status == "UNKNOWN"
    monkeypatch.setattr(node, "counts", lambda: (2, 1, 150, 250))
    second = Observation.model_validate(node.observe())
    assert second.status == "HEALTHY" and second.mode == "PASSIVE"
    assert second.dns_ok is None and second.https_ok is None and second.egress_ok is None
    third = Observation.model_validate(node.observe())
    assert third.status == "UNKNOWN"


def test_unconfirmed_peer_removal_preserves_cleanup_journal(helper, monkeypatch):
    _, run = helper
    identifier = str(uuid4())
    path = run / f"lease-{identifier}.json"
    node.write(path, json.dumps({"public_key": PUBKEY, "expires": time.time() + 60}))
    monkeypatch.setattr(node, "cmd", lambda args, **kwargs: "interface-present")
    monkeypatch.setattr(node, "peers", lambda: [PUBKEY])
    assert node.revoke(identifier) == {"removed": False}
    assert path.exists()
    monkeypatch.setattr(node, "peers", lambda: [])
    assert node.revoke(identifier) == {"removed": True}
    assert not path.exists()


def test_private_key_inspection_is_not_exposed():
    for field in ("dump", "showconf", "private-key"):
        with pytest.raises(node.Failure, match="INVALID_FIELD"):
            node.wg(field)


def test_configuration_runs_firewall_outside_confined_wg_quick_and_rolls_back(
    helper, monkeypatch, tmp_path
):
    root, _ = helper
    (root / "state.json").unlink()
    paths = tmp_path / "system"
    paths.mkdir()
    monkeypatch.setattr(node, "Path", lambda path: paths / str(path).lstrip("/"))
    unit = paths / "etc/systemd/system/wg-quick@pl-wg0.service.d/50-prettylisavpn-firewall.conf"
    monkeypatch.setattr(node, "FIREWALL_UNIT", unit)
    monkeypatch.setattr(node.os, "chown", lambda *args: None, raising=False)
    monkeypatch.setitem(
        sys.modules, "grp", SimpleNamespace(getgrnam=lambda _: SimpleNamespace(gr_gid=0))
    )
    (paths / "etc/wireguard").mkdir(parents=True)
    (paths / "etc/sysctl.d").mkdir(parents=True)
    node.write(root / "measure.key", "test fixture")
    calls = []
    operation = str(uuid4())

    def command(args, **kwargs):
        calls.append(args)
        if args == ["ip", "-j", "route", "show"]:
            return "[]"
        if args == ["ip", "-j", "route", "get", "1.1.1.1"]:
            return '[{"dev":"eth0"}]'
        if args == ["systemctl", "enable", "--now", "wg-quick@pl-wg0"]:
            config = (paths / "etc/wireguard/pl-wg0.conf").read_text()
            assert "PostUp" not in config and "PostDown" not in config
            assert (
                "ExecStartPost=/usr/bin/python3 " + node.HELPER + " firewall-up" in unit.read_text()
            )
            assert (
                "ExecStopPost=/usr/bin/python3 " + node.HELPER + " firewall-down"
                in unit.read_text()
            )
            assert ["systemctl", "daemon-reload"] in calls
            raise node.Failure("NODE_COMMAND_FAILED")
        return "0" if args[:2] == ["sysctl", "-n"] else ""

    monkeypatch.setattr(node, "cmd", command)
    with pytest.raises(node.Failure, match="NODE_COMMAND_FAILED"):
        node.configure(
            {
                "configuration": {"address": "10.88.3.1/24", "listen_port": 51820, "mtu": 1380},
                "operation_id": operation,
                "host": "45.153.68.12",
            }
        )
    # A different operation must never remove this setup's files.
    assert node.rollback(str(uuid4())) == {"rolled_back": False}
    assert unit.exists()
    foreign = unit.parent / "90-owner.conf"
    foreign.write_text("# unrelated administrator override")
    assert node.rollback(operation) == {"rolled_back": True}
    assert not unit.exists() and foreign.exists()
    assert not (paths / "etc/wireguard/pl-wg0.conf").exists()
    assert not (root / "state.json").exists()


def test_probe_key_uses_pipe_without_relaxing_apparmor(helper, monkeypatch, tmp_path):
    _, run = helper
    identifier = str(uuid4())
    private = "disposable-private-fixture"
    node.write(run / f"probe-{identifier}.json", json.dumps({"expires": time.time() + 240}))
    node.write(run / f"probe-{identifier}.key", private)
    monkeypatch.setattr(node, "Path", lambda _: tmp_path / "netns")
    disposed, keys = [], []
    monkeypatch.setattr(node, "dispose", lambda value: disposed.append(value))

    def command(args, **kwargs):
        assert private not in str(args)
        if "private-key" in args:
            assert args[args.index("private-key") + 1] == "/dev/stdin"
            keys.append(kwargs["data"])
            raise node.Failure("PROBE_INTERRUPTED")
        return ""

    monkeypatch.setattr(node, "cmd", command)
    with pytest.raises(node.Failure, match="PROBE_INTERRUPTED"):
        node.probe(
            {
                "check_id": identifier,
                "public_key": PUBKEY,
                "endpoint": "5.181.49.183",
                "listen_port": 51820,
                "address": "10.88.1.254/32",
                "mtu": 1380,
                "expected_egress_ips": ["5.181.49.183"],
            }
        )
    assert keys == [private]
    assert disposed == [identifier]
