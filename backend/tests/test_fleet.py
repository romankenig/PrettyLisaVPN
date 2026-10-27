"""Network proof, scheduling, credentials and administrative API boundaries."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from prettylisavpn.config import Settings
from prettylisavpn.fleet.domain import (
    FleetError,
    MethodState,
    Node,
    NodeInput,
    Observation,
    WireGuardConfig,
    hourly_slot,
    server_quality,
    source_order,
)
from prettylisavpn.fleet.ssh import Credential, SshTransport
from prettylisavpn.fleet.wireguard import WireGuardMethod
from prettylisavpn.fleet.worker import Claim, FleetWorker
from prettylisavpn.main import create_app
from prettylisavpn.subscriptions.domain import SubscriptionPlan

ADMIN, MONITOR = "admin-" + "a" * 40, "reader-" + "b" * 40
NOW = datetime(2026, 10, 27, 12, tzinfo=UTC)
PUBKEY = "A" * 43 + "="


def settings(**kwargs):
    return Settings(
        _env_file=None,
        fleet_enabled=True,
        fleet_admin_token=ADMIN,
        fleet_monitor_token=MONITOR,
        **kwargs,
    )


def node(**kwargs):
    return Node(
        id=uuid4(),
        name="Test node",
        country_code="DE",
        host="1.1.1.1",
        credential_ref="test",
        expected_egress_ips=["1.1.1.1"],
        capacity=100,
        is_available_for_free=True,
        enabled=True,
        **kwargs,
    )


def healthy(at=NOW, **kwargs):
    return Observation(
        status="HEALTHY",
        mode="SYNTHETIC",
        code="FULL_CHECK_PASSED",
        observed_at=at,
        handshake_ok=True,
        dns_ok=True,
        https_ok=True,
        egress_ok=True,
        **kwargs,
    )


def test_method_configuration_and_inventory_do_not_accept_arbitrary_networks():
    for address in (
        "8.8.8.1/24",
        "100.64.0.1/24",
        "172.32.0.1/24",
        "10.2.0.2/24",
        "10.0.0.1/8",
        "::1/128",
    ):
        with pytest.raises(ValidationError):
            WireGuardConfig(address=address)
    assert str(WireGuardConfig(address="172.31.0.1/24").address) == "172.31.0.1/24"
    with pytest.raises(ValidationError):
        NodeInput(
            name="Node",
            country_code="DE",
            host="127.0.0.1",
            credential_ref="test",
            expected_egress_ips=["1.1.1.1"],
        )
    with pytest.raises(FleetError, match="NODE_CREDENTIAL_NOT_ENROLLED"):
        SshTransport(
            {"test": Credential(host="8.8.8.8", user="root", key_file="/key", known_hosts="/hosts")}
        ).credential(node())


def test_fleet_secrets_must_be_distinct_and_quality_weights_valid():
    for values in (
        {"fleet_enabled": True},
        {"fleet_enabled": True, "fleet_admin_token": ADMIN, "fleet_monitor_token": ADMIN},
        {"fleet_quality_weights": [1, 1, 1, 1]},
    ):
        with pytest.raises(ValidationError):
            Settings(_env_file=None, **values)


def test_every_new_node_becomes_source_and_target_with_spread_slots():
    roster = [UUID(int=index) for index in range(1, 21)]
    slots = sorted(hourly_slot(item, NOW, roster) for item in roster)
    assert all(NOW < slot < NOW + timedelta(hours=1) for slot in slots)
    assert min((b - a).total_seconds() for a, b in zip(slots, slots[1:], strict=False)) >= 90
    for target in roster:
        selected = {
            source_order(target, NOW + timedelta(hours=hour), roster)[0] for hour in range(19)
        }
        assert selected == set(roster) - {target}
    assert source_order(roster[0], NOW, roster[:1]) == []
    assert hourly_slot(roster[0], NOW + timedelta(days=3), roster) > NOW + timedelta(days=3)


def test_success_requires_every_network_stage_and_confirmed_cleanup():
    for key in ("handshake_ok", "dns_ok", "https_ok", "egress_ok", "cleanup_confirmed"):
        data = healthy().model_dump()
        data[key] = False
        with pytest.raises(ValidationError):
            Observation.model_validate(data)
    with pytest.raises(ValidationError):
        Observation(status="HEALTHY", mode="PASSIVE", code="TRAFFIC", observed_at=NOW, dns_ok=True)


def test_rating_penalizes_failure_load_latency_bandwidth_and_staleness():
    fast = healthy(connection_ms=200, download_mbps=150, upload_mbps=110)
    assert server_quality([fast], 100, NOW)["quality"] == 100
    assert (
        server_quality(
            [fast.model_copy(update={"authorized_connections": 90, "active_connections": 90})],
            100,
            NOW,
        )["quality"]
        == 82
    )
    assert (
        server_quality([healthy(connection_ms=5000, download_mbps=10, upload_mbps=5)], 100, NOW)[
            "quality"
        ]
        < 80
    )
    assert server_quality([healthy()], 100, NOW)["quality"] == 70
    assert not server_quality([fast], 100, NOW + timedelta(minutes=76))["available"]
    assert not server_quality([fast.model_copy(update={"authorized_connections": 100})], 100, NOW)[
        "available"
    ]
    failed = Observation(
        status="FAILED",
        mode="SYNTHETIC",
        code="HANDSHAKE_FAILED",
        observed_at=NOW + timedelta(seconds=1),
    )
    assert server_quality([fast, failed], 100, NOW + timedelta(seconds=2))["quality"] == 0
    passive = Observation(status="HEALTHY", mode="PASSIVE", code="ACTIVE_TRAFFIC", observed_at=NOW)
    assert server_quality([passive], 100, NOW)["confidence"] == "PASSIVE"
    assert server_quality([passive], 100, NOW)["quality"] == 70


@pytest.mark.parametrize(
    "token,status", [(None, 401), ("ordinary-user-session", 401), (MONITOR, 403)]
)
async def test_admin_endpoints_require_scoped_administrator(token, status):
    fleet = AsyncMock()
    app = create_app(settings(), postgres=AsyncMock(), valkey=AsyncMock(), fleet=fleet)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client,
    ):
        response = await client.get(
            "/admin/nodes", headers={"Authorization": "Bearer " + token} if token else {}
        )
    assert response.status_code == status
    fleet.nodes.assert_not_called()


async def test_all_fleet_routes_delegate_and_monitoring_is_read_only():
    fleet = AsyncMock()
    fleet.register.return_value = {"id": str(uuid4())}
    fleet.nodes.return_value = []
    fleet.enqueue.return_value = {"status": "QUEUED"}
    fleet.operation.return_value = {"status": "SUCCEEDED"}
    fleet.monitoring.return_value = {"nodes": [], "overall": {}}
    app = create_app(settings(), postgres=AsyncMock(), valkey=AsyncMock(), fleet=fleet)
    identifier = str(uuid4())
    async with (
        app.router.lifespan_context(app),
        AsyncClient(
            transport=ASGITransport(app=app),
            base_url="https://test",
            headers={"Authorization": "Bearer " + ADMIN, "Idempotency-Key": str(uuid4())},
        ) as client,
    ):
        assert (
            await client.post(
                "/admin/nodes",
                json={
                    "name": "DE1",
                    "country_code": "DE",
                    "host": "1.1.1.1",
                    "credential_ref": "de1",
                    "expected_egress_ips": ["1.1.1.1"],
                },
            )
        ).status_code == 201
        assert (await client.get("/admin/nodes")).json() == []
        base = f"/admin/nodes/{identifier}/methods/wireguard"
        assert (
            await client.post(base + "/configuration", json={"address": "10.88.0.1/24"})
        ).status_code == 202
        assert (await client.post(base + "/checks")).status_code == 202
        assert (await client.get("/admin/operations/" + identifier)).status_code == 200
        client.headers["Authorization"] = "Bearer " + MONITOR
        assert (await client.get("/admin/monitoring/availability?days=7")).status_code == 200
        assert (await client.get("/admin/monitoring/availability?days=8")).status_code == 422
        assert (await client.post(base + "/checks")).status_code == 403
    assert fleet.enqueue.await_count == 2
    fleet.monitoring.assert_awaited_once_with(None, 7)


@pytest.mark.parametrize(
    "plan,free_only",
    [
        (SubscriptionPlan.FREE, True),
        (SubscriptionPlan.PREMIUM, False),
        (SubscriptionPlan.PLATINUM, False),
    ],
)
async def test_country_ratings_respect_effective_plan(plan, free_only):
    fleet, auth = AsyncMock(), AsyncMock()
    auth.me.return_value = SimpleNamespace(plan=plan)
    fleet.countries.return_value = {
        "autopilot": {"quality": 90, "available": True},
        "countries": [{"country_code": "DE", "quality": 90, "available": True}],
    }
    app = create_app(
        settings(),
        postgres=AsyncMock(),
        valkey=AsyncMock(),
        fleet=fleet,
        authenticated_sessions=auth,
    )
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client,
    ):
        assert (
            await client.get("/vpn/countries", headers={"Authorization": "Bearer user"})
        ).json()["autopilot"]["quality"] == 90
    fleet.countries.assert_awaited_once_with(free_only=free_only)


async def test_active_users_skip_synthetic_probe():
    method = AsyncMock()
    method.inspect.return_value = MethodState(installed=True, authorized_connections=1)
    method.observe.return_value = Observation(
        status="UNKNOWN", mode="PASSIVE", code="PASSIVE_EVIDENCE_INSUFFICIENT", observed_at=NOW
    )
    claim = Claim(uuid4(), uuid4(), node(), node(), "wireguard", "CHECK", {})
    _, observed = await FleetWorker(AsyncMock(), {"wireguard": method}).execute(claim)
    assert observed.mode == "PASSIVE"
    method.probe.assert_not_called()


@pytest.mark.parametrize("failure", ["HANDSHAKE_FAILED", "DNS_FAILED", "EGRESS_IP_MISMATCH"])
async def test_failed_probe_always_revokes_access_and_disposes_namespace(failure):
    transport = AsyncMock()

    async def call(target, action, payload=None, **kwargs):
        return {
            "inspect": MethodState(
                installed=True,
                public_key=PUBKEY,
                configuration={"address": "10.88.0.1/24", "listen_port": 51820, "mtu": 1380},
            ).model_dump(),
            "prepare": {"public_key": PUBKEY},
            "grant": {},
            "revoke": {"removed": True},
            "dispose": {"removed": True},
            "probe": Observation(
                status="FAILED", mode="SYNTHETIC", code=failure, observed_at=NOW
            ).model_dump(mode="json"),
        }[action]

    transport.call.side_effect = call
    result = await WireGuardMethod(transport).probe(node(), node(), uuid4())
    assert result.code == failure
    assert [call.args[1] for call in transport.call.await_args_list][-2:] == ["revoke", "dispose"]


async def test_unknown_cleanup_cannot_report_healthy():
    transport = AsyncMock()

    async def call(target, action, payload=None, **kwargs):
        return {
            "inspect": MethodState(
                installed=True,
                public_key=PUBKEY,
                configuration={"address": "10.88.0.1/24", "listen_port": 51820, "mtu": 1380},
            ).model_dump(),
            "prepare": {"public_key": PUBKEY},
            "grant": {},
            "probe": healthy().model_dump(mode="json"),
            "revoke": {"removed": False},
            "dispose": {"removed": True},
        }[action]

    transport.call.side_effect = call
    result = await WireGuardMethod(transport).probe(node(), node(), uuid4())
    assert result.status == "UNKNOWN" and result.cleanup_confirmed is False
