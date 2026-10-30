"""Durable process intent, revocation fences, bounded grants and TCP/UDP rules."""

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock
from uuid import uuid4

import pytest

from prettylisavpn.fleet.ubuntu import managed


@pytest.fixture
def host(tmp_path, monkeypatch):
    root = tmp_path / "managed"
    root.mkdir()
    (root / "leases").mkdir()
    (root / "closed").mkdir()
    monkeypatch.setattr(managed, "ROOT", root)
    monkeypatch.setattr(managed, "inspect", lambda: {"installed": True})
    monkeypatch.setattr(managed, "active", lambda _id: True)
    monkeypatch.setattr(managed.time, "sleep", lambda _: None)
    command = Mock(return_value="")
    monkeypatch.setattr(managed, "cmd", command)
    return root, command


def access(method="VLESS_REALITY"):
    return {
        "id": str(uuid4()),
        "secret": str(uuid4()),
        "method": method,
        "port": 40001,
        "expires_at": (datetime.now(UTC) + timedelta(seconds=120)).isoformat(),
    }


def test_grant_journal_precedes_mutation_and_retry_reuses_identity(host):
    root, command = host
    grant = access()
    ready = managed.lease_path(grant["id"]).with_suffix(".ready")
    ready.write_text("ready")

    def invoke(argv, **kwargs):
        if argv[0] == "iptables-restore":
            assert (
                json.loads(managed.lease_path(grant["id"]).read_text())["secret"] == grant["secret"]
            )
            assert "--datestop" in kwargs["data"]
        return ""

    command.side_effect = invoke
    assert managed.grant(grant) == {"granted": True}
    assert managed.grant(grant) == {"granted": True}
    assert len(list((root / "leases").glob("*.json"))) == 1
    for changed in ({"secret": str(uuid4())}, {"port": 40002}, {"method": "VMESS_TLS"}):
        with pytest.raises(managed.Failure, match="MANAGED_ACCESS_CONFLICT"):
            managed.grant({**grant, **changed})


def test_revoke_tombstone_is_durable_even_when_process_cannot_be_stopped(host):
    _, command = host
    grant = access()
    managed.write(
        managed.lease_path(grant["id"]), json.dumps(managed.validate(grant, managed.time.time()))
    )
    assert managed.revoke(grant["id"]) == {"removed": False}
    assert managed.tombstone(grant["id"]).is_file()
    assert managed.lease_path(grant["id"]).is_file()
    with pytest.raises(managed.Failure, match="MANAGED_ACCESS_CLOSED"):
        managed.grant(grant)
    assert any(call.args[0][:2] == ["systemctl", "stop"] for call in command.call_args_list)


def test_missing_revoke_still_prevents_late_grant(host, monkeypatch):
    monkeypatch.setattr(managed, "active", lambda _: False)
    grant = access()
    assert managed.revoke(grant["id"]) == {"removed": True}
    with pytest.raises(managed.Failure, match="MANAGED_ACCESS_CLOSED"):
        managed.grant(grant)


@pytest.mark.parametrize(
    "method,protocols",
    [
        ("VLESS_REALITY", ["tcp"]),
        ("SHADOWSOCKS_2022", ["tcp", "udp"]),
        ("HYSTERIA2_SALAMANDER", ["udp"]),
    ],
)
def test_fenced_rules_match_method_network(host, method, protocols):
    _, command = host
    row = managed.validate(access(method), managed.time.time())
    managed.firewall(row, row["expires"])
    hooks = [call.args[0] for call in command.call_args_list if "-I" in call.args[0]]
    assert [hook[hook.index("-p") + 1] for hook in hooks] == protocols
    assert all("40001" in hook for hook in hooks)


def test_revoke_only_acknowledges_closed_listener_and_removed_firewall(host, monkeypatch):
    _, command = host
    monkeypatch.setattr(managed, "active", lambda _: False)
    grant = access("SHADOWSOCKS_2022")
    managed.write(
        managed.lease_path(grant["id"]), json.dumps(managed.validate(grant, managed.time.time()))
    )
    command.side_effect = lambda argv, **_: "listener" if argv[0] == "ss" else ""
    assert managed.revoke(grant["id"]) == {"removed": False}
    assert managed.lease_path(grant["id"]).exists()
    command.side_effect = lambda *_args, **_kwargs: ""
    assert managed.revoke(grant["id"]) == {"removed": True}
    assert not managed.lease_path(grant["id"]).exists()


def test_invalid_grants_cannot_mutate_host(host):
    _, command = host
    grant = access()
    for change in (
        {"method": "HTTP"},
        {"port": 22},
        {"port": 50000},
        {"expires_at": datetime.now(UTC).isoformat()},
        {"expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat()},
        {"expires_at": "2026-10-29T12:00:00"},
    ):
        with pytest.raises(managed.Failure, match="MANAGED_ACCESS_INVALID"):
            managed.grant({**grant, **change})
    command.assert_not_called()


def test_counts_only_recent_customer_traffic_and_never_monitoring(host, monkeypatch):
    root, _ = host
    now = managed.time.time()
    monkeypatch.setattr(managed.time, "time", lambda: now)
    rows = [access() for _ in range(4)]
    for index, row in enumerate(rows):
        value = managed.validate(row, now)
        if index == 3:
            value["purpose"] = "monitor"
        path = managed.lease_path(row["id"])
        managed.write(path, json.dumps(value))
        sample = {
            "rx_bytes": 20,
            "tx_bytes": 30,
            "flowed_at": now - (200 if index == 1 else 1),
            "observed_at": now - (40 if index == 2 else 1),
        }
        managed.write(path.with_suffix(".stats"), json.dumps(sample))
    assert managed.counts() == (3, 1, 40, 60)
