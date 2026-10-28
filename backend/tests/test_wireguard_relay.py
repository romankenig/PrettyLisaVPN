"""Relay configuration, bounded access and cleanup without touching host networking."""

import json
import time
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError
from test_fleet_node import helper  # noqa: F401

from prettylisavpn.fleet.domain import NodeInput, RelayAccess
from prettylisavpn.fleet.ubuntu import node


def registration(**kwargs):
    return NodeInput(
        name="node-001",
        country_code="RU",
        host="1.1.1.1",
        credential_ref="test",
        expected_egress_ips=["1.1.1.1"],
        **kwargs,
    )


def test_groups_preserve_legacy_eligibility_and_prohibit_conflicting_input():
    assert registration(is_available_for_free=True).group == "FREE"
    assert registration().group == "PREMIUM"
    assert registration(group="FREE").is_available_for_free
    assert not registration(group="INTERMEDIATE").is_available_for_free
    with pytest.raises(ValidationError):
        registration(group="INTERMEDIATE", is_available_for_free=True)
    with pytest.raises(ValidationError):
        registration(group="PUBLIC")


def access(**kwargs):
    return {
        "id": str(uuid4()),
        "listen_port": 20000,
        "target_host": "8.8.8.8",
        "target_port": 51820,
        "expires_at": (datetime.now(UTC) + timedelta(seconds=180)).isoformat(),
        **kwargs,
    }


@pytest.fixture
def relay_helper(helper, monkeypatch):  # noqa: F811
    root, _ = helper
    node.write(root / "state.json", json.dumps({"host": "1.1.1.1", "committed": True}))
    commands, rules = [], set()

    def command(args, **kwargs):
        commands.append((args, kwargs))
        if args[:1] == ["iptables"] and "-I" in args:
            at = args.index("-I")
            rules.add((args[4], args[at + 1], tuple(args[at + 3 :])))
        if args[:1] == ["iptables"] and "-D" in args:
            at = args.index("-D")
            rules.discard((args[4], args[at + 1], tuple(args[at + 2 :])))
        return ""

    monkeypatch.setattr(node, "cmd", command)
    monkeypatch.setattr(
        node, "has_rule", lambda table, parent, rule: (table, parent, tuple(rule)) in rules
    )
    return root, commands, rules


def test_relay_renewal_retains_endpoint_and_kernel_deadline(relay_helper):
    root, commands, rules = relay_helper
    row = access()
    assert node.grant_relay(row) == {"granted": True}
    assert len(rules) == 3
    journal = node.read(root / "relays" / (row["id"] + ".json"))
    assert journal["target_host"] == row["target_host"]
    assert journal["expires"] > time.time()
    assert all(call[0][0] != "wg" for call in commands)  # No key/peer on the intermediate.
    payload = next(options["data"] for args, options in commands if args[0] == "iptables-restore")
    assert "--datestop" in payload and "-j ACCEPT" in payload and "-j DROP" in payload
    count = sum("-I" in args for args, _ in commands)
    node.grant_relay(row)
    assert sum("-I" in args for args, _ in commands) == count
    with pytest.raises(node.Failure, match="RELAY_ACCESS_CONFLICT"):
        node.grant_relay({**row, "target_host": "9.9.9.9"})
    with pytest.raises(node.Failure, match="RELAY_PORT_IN_USE"):
        node.grant_relay({**row, "id": str(uuid4())})


def test_relay_revoke_blocks_then_removes_nat_and_conntrack(relay_helper):
    root, commands, rules = relay_helper
    row = access()
    node.grant_relay(row)
    commands.clear()
    assert node.revoke_relay(row["id"])["removed"]
    assert not rules and not (root / "relays" / (row["id"] + ".json")).exists()
    assert "-j DROP" in commands[0][1]["data"] and "-j ACCEPT" not in commands[0][1]["data"]
    assert any(args[:2] == ["conntrack", "-D"] and "--dst-nat" in args for args, _ in commands)
    assert node.revoke_relay(row["id"])["removed"]


def test_relay_uncertain_cleanup_keeps_journal_and_filter(relay_helper, monkeypatch):
    root, commands, _ = relay_helper
    row = access()
    node.grant_relay(row)
    original = node.cmd
    monkeypatch.setattr(
        node,
        "cmd",
        lambda args, **kwargs: (
            "flow" if args[:2] == ["conntrack", "-L"] else original(args, **kwargs)
        ),
    )
    with pytest.raises(node.Failure, match="RELAY_CLEANUP_FAILED"):
        node.revoke_relay(row["id"])
    assert (root / "relays" / (row["id"] + ".json")).exists()
    assert not any(args[:1] == ["iptables"] and "-X" in args for args, _ in commands)


@pytest.mark.parametrize(
    "values", [{"target_host": "127.0.0.1"}, {"listen_port": 51820}, {"target_port": 22}]
)
def test_relay_contract_rejects_private_hosts_and_unreserved_ports(values):
    with pytest.raises(ValidationError):
        RelayAccess.model_validate(access(**values))


def test_relay_failed_grant_has_durable_cleanup_journal(relay_helper, monkeypatch):
    root, _, _ = relay_helper
    row = access()

    def fail(*args, **kwargs):
        raise node.Failure("NODE_COMMAND_FAILED")

    monkeypatch.setattr(node, "relay_deadline", fail)
    with pytest.raises(node.Failure):
        node.grant_relay(row)
    assert (root / "relays" / (row["id"] + ".json")).exists()
