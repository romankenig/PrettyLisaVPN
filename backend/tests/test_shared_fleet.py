"""Secondary controller isolation, stale observations and node ownership fences."""

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from prettylisavpn.config import Settings
from prettylisavpn.fleet.domain import FleetError
from prettylisavpn.fleet.service import FleetService
from prettylisavpn.fleet.shared_policy import (
    ADDRESS_END,
    ADDRESS_START,
    allocate_shared_address,
    lease_id,
    owns_lease,
    snapshot_fresh,
)
from prettylisavpn.fleet.ubuntu import shared_access as guard


def test_shared_ranges_cannot_overlap_owner_first_free_allocation():
    from prettylisavpn.client_vpn.domain import allocate_address

    config = {"address": "10.88.1.1/24"}
    used = set()
    for _ in range(100):
        used.add(allocate_address(config, used))
    test_used = set()
    for _ in range(ADDRESS_END - ADDRESS_START):
        test_used.add(allocate_shared_address(config, test_used))
    assert not used & test_used
    with pytest.raises(FleetError, match="VPN_NODE_FULL"):
        allocate_shared_address(config, test_used)
    with pytest.raises(FleetError, match="VPN_SHARED_SUBNET_UNSUPPORTED"):
        allocate_shared_address({"address": "10.88.1.1/28"}, set())


def test_snapshot_freshness_fails_closed():
    now = datetime.now(UTC)
    assert snapshot_fresh({"shared_snapshot_at": now.isoformat()}, now)
    for timestamp in (
        "bad",
        now.replace(tzinfo=None).isoformat(),
        (now + timedelta(seconds=1)).isoformat(),
        (now - timedelta(seconds=120)).isoformat(),
    ):
        assert not snapshot_fresh({"shared_snapshot_at": timestamp}, now)
    assert not snapshot_fresh({}, now)


def test_shared_mode_cannot_become_production_owner():
    with pytest.raises(ValidationError, match="Shared fleet consumer"):
        Settings(environment="production", fleet_shared_nodes=True)
    settings = Settings(environment="test", fleet_shared_nodes=True)
    with pytest.raises(FleetError, match="FLEET_SHARED_READ_ONLY"):
        FleetService(Mock(), settings).require_owner()
    assert owns_lease(lease_id(True))
    assert not owns_lease(UUID(int=0))


@pytest.fixture
def node_guard(tmp_path, monkeypatch):
    root, run = tmp_path / "etc", tmp_path / "run"
    root.mkdir()
    run.mkdir()
    monkeypatch.setattr(guard.node, "ROOT", root)
    monkeypatch.setattr(guard.node, "RUN", run)
    monkeypatch.setattr(guard.managed, "ROOT", root / "managed")
    guard.node.write(
        root / "state.json", json.dumps({"configuration": {"address": "10.88.1.1/24"}})
    )
    guard.node.write(
        root / "shared-test-policy.json",
        json.dumps({"enabled": True, "capacity": 20, "relay": True, "relay_targets": ["8.8.8.8"]}),
    )
    monkeypatch.setattr(guard.node, "counts", lambda: (0, 0, 0, 0))
    monkeypatch.setattr(guard.managed, "counts", lambda: (0, 0, 0, 0))
    mutate = Mock(return_value={"granted": True, "removed": True})
    monkeypatch.setattr(guard.node, "dispatch", mutate)
    monkeypatch.setattr(guard.managed, "dispatch", mutate)
    return root, mutate


def access(**changes):
    return {
        "id": str(lease_id(True)),
        "purpose": "client",
        "public_key": "public-only",
        "address": "10.88.1.128/32",
        "expires_at": "2030-01-01T00:00:00Z",
        **changes,
    }


@pytest.mark.parametrize(
    "action",
    [
        "configure",
        "rollback",
        "prepare",
        "probe",
        "cleanup",
        "managed-configure",
        "managed-probe",
        "traffic",
        "inspect",
    ],
)
def test_test_key_cannot_control_fleet(node_guard, action):
    _, mutate = node_guard
    with pytest.raises(guard.node.Failure, match="SHARED_ACTION_DENIED"):
        guard.dispatch({"action": action})
    mutate.assert_not_called()


def test_prefix_is_not_authority_to_remove_or_adopt_owner_session(node_guard):
    root, mutate = node_guard
    row = access()
    clients = root / "clients"
    clients.mkdir()
    guard.node.write(clients / (row["id"] + ".json"), json.dumps({"owner": "production"}))
    for payload in (
        {"action": "grant", "access": row},
        {"action": "revoke", "access_id": row["id"], "purpose": "client"},
    ):
        with pytest.raises(guard.node.Failure, match="SHARED_FOREIGN_ACCESS"):
            guard.dispatch(payload)
    mutate.assert_not_called()
    assert guard.node.read(clients / (row["id"] + ".json")) == {"owner": "production"}


def test_renewal_disconnect_and_late_retry_preserve_fence(node_guard):
    _, mutate = node_guard
    row = access()
    guard.dispatch({"action": "grant", "access": row})
    guard.dispatch({"action": "grant", "access": {**row, "expires_at": "2030-01-01T00:01:00Z"}})
    with pytest.raises(guard.node.Failure, match="SHARED_ACCESS_CONFLICT"):
        guard.dispatch({"action": "grant", "access": {**row, "public_key": "other"}})
    guard.dispatch({"action": "revoke", "access_id": row["id"], "purpose": "client"})
    with pytest.raises(guard.node.Failure, match="SHARED_ACCESS_CONFLICT"):
        guard.dispatch({"action": "grant", "access": row})
    assert mutate.call_count == 3


@pytest.mark.parametrize(
    "action,changes",
    [
        ("grant", {"address": "10.88.1.2/32"}),
        ("grant", {"address": "10.88.1.254/32"}),
        ("managed-grant", {"port": 40000}),
        ("managed-grant", {"port": 49900}),
        ("grant-relay", {"listen_port": 28000, "target_host": "192.168.0.4", "target_port": 51820}),
        ("grant-relay", {"listen_port": 20000, "target_host": "8.8.8.8", "target_port": 51820}),
    ],
)
def test_owner_resources_and_unlisted_targets_are_denied(node_guard, action, changes):
    _, mutate = node_guard
    with pytest.raises(guard.node.Failure, match="SHARED_RESOURCE_DENIED"):
        guard.dispatch({"action": action, "access": access(**changes)})
    mutate.assert_not_called()


def test_unknown_test_revoke_is_idempotent_but_never_mutates_node(node_guard):
    _, mutate = node_guard
    assert guard.dispatch({"action": "managed-revoke", "access_id": str(lease_id(True))}) == {
        "removed": True
    }
    with pytest.raises(guard.node.Failure, match="SHARED_ACCESS_DENIED"):
        guard.dispatch({"action": "managed-revoke", "access_id": str(uuid4())})
    mutate.assert_not_called()
