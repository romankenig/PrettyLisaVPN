"""Node agent API and WireGuard adapter security tests."""

import ssl
from collections.abc import Sequence
from datetime import UTC, datetime
from ipaddress import IPv4Interface, IPv4Network
from typing import Any

import pytest
from fastapi.testclient import TestClient

from prettylisavpn_node_agent import main as agent_main
from prettylisavpn_node_agent.app import create_app
from prettylisavpn_node_agent.config import AgentSettings
from prettylisavpn_node_agent.wireguard import IP_PATH, WG_PATH, WireGuardController

AUTH_TOKEN = "a" * 64
AUTH_HEADERS = {"Authorization": f"Bearer {AUTH_TOKEN}"}
PUBLIC_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
SECOND_PUBLIC_KEY = "AQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="


class FakeWireGuardRunner:
    def __init__(self) -> None:
        self.peers: dict[str, tuple[str, int]] = {}
        self.calls: list[list[str]] = []
        self.interface_up = True

    def __call__(self, arguments: Sequence[str]) -> str:
        command = list(arguments)
        self.calls.append(command)
        if command == [WG_PATH, "show", "wg0", "allowed-ips"]:
            return "".join(f"{key}\t{vpn_ip}/32\n" for key, (vpn_ip, _) in self.peers.items())
        if command == [WG_PATH, "show", "wg0", "latest-handshakes"]:
            return "".join(f"{key}\t{handshake}\n" for key, (_, handshake) in self.peers.items())
        if command == [IP_PATH, "-j", "link", "show", "dev", "wg0"]:
            if self.interface_up:
                return '[{"ifname":"wg0","flags":["UP"],"operstate":"UNKNOWN"}]'
            return '[{"ifname":"wg0","flags":[],"operstate":"DOWN"}]'
        if command == [WG_PATH, "show", "wg0", "listen-port"]:
            return "51820\n"
        if command == [WG_PATH, "show", "wg0", "public-key"]:
            return "server-public-key\n"
        if command[:4] == [WG_PATH, "set", "wg0", "peer"]:
            key = command[4]
            if command[5:] == ["remove"]:
                self.peers.pop(key, None)
            else:
                assert command[5] == "allowed-ips"
                self.peers[key] = (command[6].removesuffix("/32"), 0)
            return ""
        raise AssertionError(f"unexpected argv: {command!r}")


@pytest.fixture
def runner() -> FakeWireGuardRunner:
    return FakeWireGuardRunner()


@pytest.fixture
def client(runner: FakeWireGuardRunner) -> TestClient:
    settings = AgentSettings(
        auth_token=AUTH_TOKEN,
        client_subnet=IPv4Network("10.77.0.0/16"),
        gateway=IPv4Interface("10.77.0.1/16"),
    )
    controller = WireGuardController(
        settings.interface,
        settings.client_subnet,
        settings.gateway,
        runner,
    )
    return TestClient(create_app(settings, controller))


@pytest.mark.parametrize(
    "method,path,kwargs",
    [
        ("put", "/v1/peers", {"json": {"public_key": PUBLIC_KEY, "vpn_ip": "10.77.0.2"}}),
        ("delete", "/v1/peers", {"json": {"public_key": PUBLIC_KEY}}),
        ("get", "/v1/peers", {"params": {"public_key": PUBLIC_KEY}}),
        ("get", "/v1/health", {}),
        ("get", "/v1/metrics", {}),
    ],
)
def test_every_endpoint_requires_authentication(
    client: TestClient, method: str, path: str, kwargs: dict[str, object]
):
    response = client.request(method, path, **kwargs)

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "NODE_AGENT_UNAUTHORIZED"


def test_rejects_wrong_machine_credential(client: TestClient):
    response = client.get("/v1/health", headers={"Authorization": "Bearer wrong"})

    assert response.status_code == 401


def test_add_and_remove_are_idempotent(client: TestClient, runner: FakeWireGuardRunner):
    request = {"public_key": PUBLIC_KEY, "vpn_ip": "10.77.0.2"}

    first_add = client.put("/v1/peers", headers=AUTH_HEADERS, json=request)
    second_add = client.put("/v1/peers", headers=AUTH_HEADERS, json=request)
    found = client.get("/v1/peers", headers=AUTH_HEADERS, params={"public_key": PUBLIC_KEY})
    first_remove = client.request(
        "DELETE", "/v1/peers", headers=AUTH_HEADERS, json={"public_key": PUBLIC_KEY}
    )
    second_remove = client.request(
        "DELETE", "/v1/peers", headers=AUTH_HEADERS, json={"public_key": PUBLIC_KEY}
    )

    assert first_add.status_code == 200
    assert first_add.json()["created"] is True
    assert second_add.json()["created"] is False
    assert found.json()["vpn_ip"] == "10.77.0.2"
    assert first_remove.json() == {"removed": True}
    assert second_remove.json() == {"removed": False}
    mutations = [call for call in runner.calls if call[:2] == [WG_PATH, "set"]]
    assert mutations == [
        [
            WG_PATH,
            "set",
            "wg0",
            "peer",
            PUBLIC_KEY,
            "allowed-ips",
            "10.77.0.2/32",
        ],
        [WG_PATH, "set", "wg0", "peer", PUBLIC_KEY, "remove"],
    ]


@pytest.mark.parametrize(
    "payload",
    [
        {"public_key": "$(touch /tmp/pwned)", "vpn_ip": "10.77.0.2"},
        {"public_key": f"{PUBLIC_KEY};id", "vpn_ip": "10.77.0.2"},
        {"public_key": PUBLIC_KEY, "vpn_ip": "10.77.0.2;id"},
        {"public_key": PUBLIC_KEY, "vpn_ip": "192.0.2.2"},
        {"public_key": PUBLIC_KEY, "vpn_ip": "10.77.0.1"},
        {"public_key": PUBLIC_KEY, "vpn_ip": "10.77.0.0"},
        {
            "public_key": PUBLIC_KEY,
            "vpn_ip": "10.77.0.2",
            "client_private_key": "must-never-be-accepted",
        },
    ],
)
def test_invalid_and_injection_inputs_never_reach_mutation_command(
    client: TestClient, runner: FakeWireGuardRunner, payload: dict[str, str]
):
    response = client.put("/v1/peers", headers=AUTH_HEADERS, json=payload)

    assert response.status_code == 422
    assert not any(call[:2] == [WG_PATH, "set"] for call in runner.calls)


def test_rejects_public_key_or_ip_conflicts(client: TestClient):
    assert (
        client.put(
            "/v1/peers",
            headers=AUTH_HEADERS,
            json={"public_key": PUBLIC_KEY, "vpn_ip": "10.77.0.2"},
        ).status_code
        == 200
    )

    key_conflict = client.put(
        "/v1/peers",
        headers=AUTH_HEADERS,
        json={"public_key": PUBLIC_KEY, "vpn_ip": "10.77.0.3"},
    )
    ip_conflict = client.put(
        "/v1/peers",
        headers=AUTH_HEADERS,
        json={"public_key": SECOND_PUBLIC_KEY, "vpn_ip": "10.77.0.2"},
    )

    assert key_conflict.status_code == 409
    assert ip_conflict.status_code == 409


def test_health_and_minimal_metrics(client: TestClient, runner: FakeWireGuardRunner):
    runner.peers[PUBLIC_KEY] = (
        "10.77.0.2",
        int(datetime.now(UTC).timestamp()),
    )

    health = client.get("/v1/health", headers=AUTH_HEADERS)
    metrics = client.get("/v1/metrics", headers=AUTH_HEADERS)

    assert health.status_code == 200
    assert health.json() == {
        "status": "HEALTHY",
        "interface": "wg0",
        "interface_up": True,
        "listen_port": 51820,
    }
    assert metrics.status_code == 200
    assert metrics.json()["peers_total"] == 1
    assert metrics.json()["peers_with_recent_handshake"] == 1
    assert metrics.json()["interface_up"] is True


def test_health_reports_unhealthy_interface(client: TestClient, runner: FakeWireGuardRunner):
    runner.interface_up = False

    response = client.get("/v1/health", headers=AUTH_HEADERS)

    assert response.status_code == 200
    assert response.json()["status"] == "UNHEALTHY"
    assert response.json()["interface_up"] is False


def test_private_key_is_never_requested(client: TestClient, runner: FakeWireGuardRunner):
    client.get("/v1/health", headers=AUTH_HEADERS)
    client.get("/v1/metrics", headers=AUTH_HEADERS)

    flattened = " ".join(argument for call in runner.calls for argument in call)
    assert "private-key" not in flattened
    assert "dump" not in flattened


def test_production_server_requires_mtls_and_disables_access_logs(
    monkeypatch: pytest.MonkeyPatch,
):
    settings = AgentSettings(
        auth_token=AUTH_TOKEN,
        client_subnet=IPv4Network("10.77.0.0/16"),
        gateway=IPv4Interface("10.77.0.1/16"),
    )
    captured: dict[str, Any] = {}

    def fake_run(app: object, **options: object) -> None:
        captured.update(options)

    monkeypatch.setattr(
        agent_main.AgentSettings,
        "from_environment",
        staticmethod(lambda: settings),
    )
    monkeypatch.setattr(agent_main.uvicorn, "run", fake_run)

    agent_main.main()

    assert captured["ssl_cert_reqs"] == ssl.CERT_REQUIRED
    assert captured["ssl_certfile"] == str(settings.tls_certificate)
    assert captured["ssl_keyfile"] == str(settings.tls_private_key)
    assert captured["ssl_ca_certs"] == str(settings.tls_client_ca)
    assert captured["access_log"] is False
