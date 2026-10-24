"""Managed authorization lifetimes, isolation, crash recovery and HTTP boundaries."""

from dataclasses import replace
from ipaddress import IPv4Interface, IPv4Network
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from test_agent import AUTH_HEADERS, AUTH_TOKEN

from prettylisavpn_node_agent.app import create_app
from prettylisavpn_node_agent.config import AgentSettings
from prettylisavpn_node_agent.managed import ManagedController, ManagedLease, ManagedUnavailable


class Child:
    pid = 123
    dead = False

    def poll(self):
        return 0 if self.dead else None

    def kill(self):
        self.dead = True

    def wait(self, timeout):
        assert self.dead
        return 0


@pytest.fixture
def managed(tmp_path):
    clock = [1000]
    launches = []
    orphan = Mock()
    node = dict(
        listen="0.0.0.0",
        private_key="private",
        public_key="public",
        server_name="api.prettylisavpn.com",
        target="95.140.152.42",
        short_id="ab",
        port_first=18443,
        port_last=18444,
    )

    def launch(config):
        child = Child()
        launches.append((config, child))
        return child

    controller = ManagedController(
        tmp_path / "state.sqlite3", node, launch, orphan, lambda: clock[0]
    )
    yield controller, launches, clock, orphan
    controller.db.close()


def lease():
    return ManagedLease(uuid4(), str(uuid4()), 1900)


def test_retry_never_extends_or_changes_authorization(managed):
    controller, launches, _, _ = managed
    original = lease()
    response = controller.issue(original)
    assert controller.issue(original) == response
    assert len(launches) == 1
    assert "secret" not in response and original.secret not in repr(original)
    for changed in (replace(original, secret=str(uuid4())), replace(original, expires=1901)):
        with pytest.raises(ManagedUnavailable):
            controller.issue(changed)


def test_revoke_kills_only_owned_process_and_blocks_late_create(managed):
    controller, launches, _, _ = managed
    first, other, late = lease(), lease(), lease()
    controller.issue(first)
    controller.issue(other)
    controller.remove(first.id)
    controller.remove(first.id)
    controller.remove(late.id)
    assert launches[0][1].dead and not launches[1][1].dead
    for removed in (first, late):
        with pytest.raises(ManagedUnavailable):
            controller.issue(removed)
    assert controller.issue(lease())["port"] == 18443


def test_capacity_and_expiry_close_process_before_port_reuse(managed):
    controller, launches, clock, _ = managed
    controller.issue(lease())
    controller.issue(lease())
    with pytest.raises(ManagedUnavailable):
        controller.issue(lease())
    clock[0] = 1901
    controller.issue(replace(lease(), expires=2000))
    assert all(child.dead for _, child in launches[:2])


def test_restart_revokes_surviving_and_partially_revoked_children(managed, tmp_path):
    controller, _, clock, orphan = managed
    original = lease()
    controller.issue(original)
    # Crash after durable intent, before native acknowledgement.
    controller.db.execute("UPDATE leases SET revoked=1")
    controller.db.commit()
    restarted = ManagedController(
        tmp_path / "state.sqlite3", controller.node, controller.launcher, orphan, lambda: clock[0]
    )
    try:
        orphan.assert_called_once_with(123, str(original.id))
        with pytest.raises(ManagedUnavailable):
            restarted.issue(original)
    finally:
        restarted.db.close()


def test_failed_start_is_tombstoned(managed):
    controller, _, _, _ = managed
    controller.launcher = Mock(side_effect=RuntimeError("private detail"))
    original = lease()
    for _ in range(2):
        with pytest.raises(ManagedUnavailable):
            controller.issue(original)
    assert controller.launcher.call_count == 1


@pytest.mark.parametrize("expires", [0, 1000, 2201])
def test_expired_or_unbounded_lease_is_rejected(managed, expires):
    controller, launches, _, _ = managed
    with pytest.raises(ValueError):
        controller.issue(replace(lease(), expires=expires))
    assert not launches


def test_api_authentication_validation_and_closed_errors(managed):
    controller, _, _, _ = managed
    settings = AgentSettings(
        auth_token=AUTH_TOKEN,
        client_subnet=IPv4Network("10.77.0.0/16"),
        gateway=IPv4Interface("10.77.0.1/16"),
    )
    client = TestClient(create_app(settings, Mock(), controller))
    original = lease()
    path = f"/v1/managed/{original.id}"
    body = dict(secret=original.secret, expires=original.expires)
    assert client.put(path, json=body).status_code == 401
    assert client.delete(path).status_code == 401
    assert client.put(path, headers=AUTH_HEADERS, json=body).status_code == 200
    assert client.delete(path, headers=AUTH_HEADERS).json() == {"removed": True}
    assert client.put(path, headers=AUTH_HEADERS, json=body).status_code == 503
    response = client.put(path, headers=AUTH_HEADERS, json={**body, "expires": original.secret})
    assert response.status_code == 422 and original.secret not in response.text
    controller.remove = Mock(side_effect=RuntimeError(original.secret))
    response = client.delete(path, headers=AUTH_HEADERS)
    assert response.status_code == 503 and original.secret not in response.text
