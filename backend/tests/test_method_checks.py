"""Fixed-method sampling, relay lifecycle, browser proxy profiles and private reports."""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from test_fleet import ADMIN, MONITOR, NOW, PUBKEY, healthy, node, settings

from prettylisavpn.fleet.daily_checks import finish_attempt
from prettylisavpn.fleet.domain import FleetError
from prettylisavpn.fleet.managed import ManagedVpnMethod
from prettylisavpn.fleet.method_checks import MethodAnalytics, choose_route
from prettylisavpn.fleet.wireguard import WireGuardMethod
from prettylisavpn.main import create_app


def test_method_routes_exhaust_unique_pairs_and_prefer_another_exit():
    a, b, relay, other = uuid4(), uuid4(), uuid4(), uuid4()
    roster = [(a, relay), (a, other), (b, relay)]
    attempts = [{"node": str(a), "relay": str(relay)}]
    assert choose_route(roster, attempts) == (b, relay)
    attempts.append({"node": str(b), "relay": str(relay)})
    assert choose_route(roster, attempts) == (a, other)
    attempts.append({"node": str(a), "relay": str(other)})
    assert choose_route(roster, attempts) is None
    assert choose_route([(a, None)], [{"node": str(a), "relay": None}]) is None


@pytest.mark.parametrize("offset,score", [(0, 100), (60, 96.7), (900, 50), (1800, 0)])
def test_method_score_uses_first_success_time_and_hard_deadline(offset, score):
    row = SimpleNamespace(started_at=NOW, attempts=[{"tested": False}], finished_at=None)
    result = healthy().model_copy(update={"code": "SERVICE_CHECK_PASSED"})
    finish_attempt(
        row,
        result,
        result.code,
        NOW + timedelta(seconds=offset),
        NOW + timedelta(seconds=offset + 1),
        NOW + timedelta(minutes=30),
    )
    assert row.score == score and row.finished_at is not None


@pytest.mark.parametrize(
    "result,expected",
    [
        (None, None),
        (healthy(), None),
        (healthy().model_copy(update={"code": "SERVICE_HTTP_FAILED", "status": "FAILED"}), 0),
    ],
)
def test_unmeasured_exhaustion_is_not_a_zero_or_generic_success(result, expected):
    row = SimpleNamespace(started_at=NOW, attempts=[{"tested": False}] * 30, finished_at=None)
    finish_attempt(
        row,
        result,
        result.code if result else "SERVICE_SAMPLE_UNAVAILABLE",
        NOW,
        NOW,
        NOW + timedelta(minutes=30),
    )
    assert row.score == expected and row.finished_at == NOW


@pytest.mark.parametrize(
    "method", ["wireguard", "amneziawg", "vless", "shadowsocks2022", "https_proxy"]
)
@pytest.mark.parametrize("relayed", [False, True])
async def test_actual_method_probe_uses_relay_endpoint_and_revokes_both(method, relayed):
    if method == "https_proxy" and relayed:
        return  # Browser proxy has no advertised relay variant.
    source, target, relay = node(), node(), node(group="INTERMEDIATE")
    token = uuid4()
    transport = AsyncMock()
    responses = {
        "inspect": {
            "installed": True,
            "public_key": PUBKEY,
            "configuration": {"address": "10.88.0.1/24", "listen_port": 51820, "mtu": 1380},
        },
        "managed-inspect": {
            "installed": True,
            "public_key": PUBKEY,
            "configuration": {
                "server_name": "vpn.example.org",
                "certificate_pin": "a" * 64,
                "proxy_host": "proxy.example.org",
            },
        },
        "prepare": {"public_key": PUBKEY},
        "grant": {},
        "managed-grant": {"granted": True},
        "grant-relay": {"granted": True},
        "revoke-relay": {"removed": True},
        "revoke": {"removed": True},
        "managed-revoke": {"removed": True},
        "dispose": {"removed": True},
        "probe": healthy().model_copy(update={"code": "SERVICE_CHECK_PASSED"}).model_dump(),
        "managed-probe": healthy().model_copy(update={"code": "SERVICE_CHECK_PASSED"}).model_dump(),
    }

    async def call(_node, action, *args, **kwargs):
        return responses[action]

    transport.call.side_effect = call
    adapter = (
        WireGuardMethod(transport)
        if method == "wireguard"
        else ManagedVpnMethod(transport, SecretStr("k" * 32))
    )
    route = {"relay": relay, "relay_port": 29999} if relayed else {}
    args = [source, target, token, "https://example.org/news/recent", ["example.org"]]
    if method != "wireguard":
        args.append(method + ("_relay" if relayed else ""))
    result = await adapter.probe(*args, **route)
    assert result.code == "SERVICE_CHECK_PASSED" and result.cleanup_confirmed
    calls = {call.args[1]: call for call in transport.call.await_args_list}
    request = calls["probe" if method == "wireguard" else "managed-probe"].args[2]
    if method == "wireguard":
        assert request["endpoint"] == (relay.host if relayed else target.host)
        assert request["listen_port"] == (29999 if relayed else 51820)
    else:
        profile = request["profile"]
        assert profile["port"] == (29999 if relayed else 49900 + token.int % 100)
        if method == "https_proxy":
            assert profile["method"] == "HTTPS_PROXY" and profile["server"] == "proxy.example.org"
            assert profile["username"] == str(token)
    if relayed:
        forward = calls["grant-relay"].args[2]["access"]
        assert forward["target_host"] == target.host and forward["listen_port"] == 29999
        assert forward["protocol"] == (
            "both" if method == "shadowsocks2022" else "tcp" if method == "vless" else "udp"
        )
        assert "revoke-relay" in calls
        # Uncertain relay removal must never be counted as a healthy check.
        responses["revoke-relay"] = {"removed": False}
        result = await adapter.probe(*args, **route)
        assert result.code == "CLEANUP_UNCONFIRMED" and not result.cleanup_confirmed


async def test_relay_method_cannot_silently_fall_back_to_direct():
    adapter = ManagedVpnMethod(AsyncMock(), SecretStr("k" * 32))
    adapter.inspect = AsyncMock(return_value=SimpleNamespace(installed=True, public_key=PUBKEY))
    with pytest.raises(FleetError, match="VPN_METHOD_UNSUPPORTED"):
        await adapter.probe(node(), node(), uuid4(), selected_method="amneziawg_relay")


@pytest.mark.parametrize(
    "token,status", [(None, 401), ("user-token", 401), (MONITOR, 200), (ADMIN, 200)]
)
async def test_method_report_requires_monitor_credentials(token, status, monkeypatch):
    report = AsyncMock(
        return_value={"methods": [], "selection": {"active_sessions": 0, "items": []}}
    )
    monkeypatch.setattr(MethodAnalytics, "report", report)
    app = create_app(settings(), postgres=AsyncMock(), valkey=AsyncMock())
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client,
    ):
        response = await client.get(
            "/admin/monitoring/connection-methods",
            headers={"Authorization": "Bearer " + token} if token else {},
        )
        assert response.status_code == status
        assert report.await_count == (1 if status == 200 else 0)
        assert (await client.post("/admin/monitoring/connection-methods")).status_code == 405
