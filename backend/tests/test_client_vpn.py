"""Customer API boundaries, entitlement accounting and isolated node lease safety."""

import base64
import json
import time
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from test_fleet import settings
from test_fleet_node import helper  # noqa: F401

from prettylisavpn.auth.session_service import InvalidSessionError
from prettylisavpn.client_vpn.domain import (
    ConnectRequest,
    allocate_address,
    deadline,
    reserved_seconds,
)
from prettylisavpn.fleet.domain import FleetError
from prettylisavpn.fleet.ubuntu import node
from prettylisavpn.main import create_app
from prettylisavpn.subscriptions.domain import Subscription, SubscriptionPlan

KEY = base64.b64encode(bytes(range(32))).decode()
NOW = datetime(2026, 10, 27, 23, 59, 45, tzinfo=UTC)


def test_customer_key_is_canonical_nonzero_and_input_has_no_private_key():
    assert ConnectRequest(public_key=KEY).country == "AUTO"
    for value in ("A" * 43 + "=", KEY[:-2] + "B=", "private", KEY + "\n"):
        with pytest.raises(ValidationError):
            ConnectRequest(public_key=value)
    with pytest.raises(ValidationError):
        ConnectRequest(public_key=KEY, private_key=KEY)


def test_free_deadline_midnight_and_paid_parity():
    free = Subscription.new_free(uuid4(), NOW)
    assert deadline(free, NOW, 3600) == (True, NOW + timedelta(seconds=15))
    assert deadline(free, NOW, 3) == (True, NOW + timedelta(seconds=3))
    with pytest.raises(FleetError, match="FREE_QUOTA_EXHAUSTED"):
        deadline(free, NOW, 0)
    for plan in (SubscriptionPlan.PREMIUM, SubscriptionPlan.PLATINUM):
        paid = replace(free, plan=plan, current_period_end=NOW + timedelta(days=7))
        assert deadline(paid, NOW, 0) == (False, paid.current_period_end)
        assert deadline(paid, paid.current_period_end, 20)[0] is True


def test_quota_only_returns_unused_time_after_confirmed_removal():
    expiry = NOW + timedelta(seconds=3600)
    assert reserved_seconds(NOW, expiry, None, None) == 3600
    assert reserved_seconds(NOW, expiry, NOW, None) == 3600
    assert reserved_seconds(NOW, expiry, None, NOW + timedelta(seconds=5)) == 0
    assert reserved_seconds(NOW, expiry, NOW, NOW + timedelta(seconds=5.1)) == 6
    assert reserved_seconds(NOW, expiry, NOW, expiry + timedelta(days=1)) == 3600


def test_allocator_never_uses_server_monitor_or_broadcast_addresses():
    config = {"address": "10.88.1.1/28"}
    used = set()
    for offset in range(2, 14):
        address = allocate_address(config, used)
        assert address == f"10.88.1.{offset}/32"
        used.add(address)
    with pytest.raises(FleetError, match="VPN_NODE_FULL"):
        allocate_address(config, used)


@pytest.mark.parametrize(
    "method,path",
    [
        ("POST", ""),
        ("GET", "/current"),
        ("GET", "/{id}"),
        ("POST", "/{id}/heartbeat"),
        ("DELETE", "/{id}"),
        ("GET", "/{id}/probe"),
    ],
)
async def test_all_customer_endpoints_are_private_and_delegate(method, path):
    identifier, request_id = uuid4(), uuid4()
    path = "/vpn/wireguard/sessions" + path.format(id=identifier)
    backend = SimpleNamespace(
        connect=AsyncMock(return_value={"status": "PROVISIONING"}),
        get=AsyncMock(return_value={"status": "READY"}),
    )
    dependency = SimpleNamespace(ping=AsyncMock(return_value=True), close=AsyncMock())
    app = create_app(
        settings(client_vpn_enabled=True),
        postgres=dependency,
        valkey=dependency,
        client_vpn=backend,
        otp_service=SimpleNamespace(),
    )
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client,
    ):
        kwargs = {"headers": {"Idempotency-Key": str(request_id)}}
        if method == "POST" and path.endswith("/sessions"):
            kwargs["json"] = {"public_key": KEY}
        response = await client.request(method, path, **kwargs)
        assert response.status_code == 401 and response.headers["Cache-Control"] == "no-store"
        kwargs["headers"]["Authorization"] = "Bearer access"
        response = await client.request(method, path, **kwargs)
        assert response.status_code in (200, 202)
        assert response.headers["Cache-Control"] == "no-store"
        assert response.headers["Vary"] == "Authorization"
        action = backend.connect if path.endswith("/sessions") else backend.get
        assert action.await_args.args[0] == "access"
        action.side_effect = InvalidSessionError
        assert (await client.request(method, path, **kwargs)).status_code == 401


def client_access(**changes):
    return {
        "id": str(uuid4()),
        "public_key": KEY,
        "purpose": "client",
        "address": "10.88.0.2/32",
        "expires_at": (datetime.now(UTC) + timedelta(seconds=180)).isoformat(),
        **changes,
    }


def test_customer_journal_precedes_mutation_and_ttl_cleanup(helper, monkeypatch):  # noqa: F811
    root, _ = helper
    access = client_access()
    monkeypatch.setattr(node, "peers", lambda: [])

    def fail(args, **kwargs):
        raise node.Failure("NODE_COMMAND_FAILED")

    monkeypatch.setattr(node, "cmd", fail)
    with pytest.raises(node.Failure):
        node.grant(access)
    path = root / "clients" / (access["id"] + ".json")
    assert node.read(path)["public_key"] == KEY
    row = node.read(path)
    row["expires"] = time.time() - 1
    node.write(path, json.dumps(row))
    calls = []
    monkeypatch.setattr(
        node,
        "cmd",
        lambda args, **kwargs: calls.append(args) or ("present" if args[0] == "ip" else ""),
    )
    node.cleanup()
    assert not path.exists()
    assert ["wg", "set", node.WG, "peer", KEY, "remove"] in calls


def test_customer_kernel_deadline_is_utc_and_precedes_peer_grant(helper, monkeypatch):  # noqa: F811
    calls = []
    monkeypatch.setattr(node, "peers", lambda: [])
    monkeypatch.setattr(node, "cmd", lambda args, **kwargs: calls.append((args, kwargs)) or "")
    access = client_access()
    node.grant(access)
    firewall = next(index for index, (args, _) in enumerate(calls) if args[0] == "iptables-restore")
    grant = next(index for index, (args, _) in enumerate(calls) if args[:2] == ["wg", "set"])
    assert firewall < grant
    script = calls[firewall][1]["data"]
    assert "--datestop" in script and "--kerneltz" not in script and "-j DROP" in script


@pytest.mark.parametrize(
    "address", ["10.88.0.1/32", "10.88.0.254/32", "10.88.0.255/32", "10.89.0.2/32", "10.88.0.2/24"]
)
def test_customer_cannot_claim_reserved_addresses(helper, address):  # noqa: F811
    with pytest.raises(node.Failure, match="ACCESS_INVALID"):
        node.grant(client_access(address=address))


def test_customer_renewal_is_idempotent_and_cannot_take_another_peer(helper, monkeypatch):  # noqa: F811
    monkeypatch.setattr(node, "peers", lambda: [])
    monkeypatch.setattr(node, "cmd", lambda args, **kwargs: "")
    access = client_access()
    assert node.grant(access)["granted"]
    assert node.grant(access)["granted"]
    for changed in (
        {"id": str(uuid4())},
        {"address": "10.88.0.3/32"},
        {"public_key": "B" * 43 + "="},
    ):
        with pytest.raises(node.Failure, match="ACCESS_CONFLICT"):
            node.grant({**access, **changed})
    with pytest.raises(node.Failure, match="ACCESS_INVALID"):
        node.grant(client_access(expires_at=(datetime.now(UTC) + timedelta(hours=1)).isoformat()))
