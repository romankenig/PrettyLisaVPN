"""Network proof, scheduling, credentials and administrative API boundaries."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from prettylisavpn.config import Settings
from prettylisavpn.fleet.acceptance import assess
from prettylisavpn.fleet.domain import (
    FleetError,
    MethodState,
    Node,
    NodeInput,
    NodeUpdate,
    Observation,
    WireGuardConfig,
    hourly_slot,
    monitoring_slot,
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


@pytest.mark.parametrize("token,status", [(None, 401), (MONITOR, 403), (ADMIN, 200)])
async def test_node_group_update_is_admin_only(token, status):
    fleet = AsyncMock()
    fleet.update_node.return_value = {"name": "timeweb-rus-001", "group": "INTERMEDIATE"}
    app = create_app(settings(), postgres=AsyncMock(), valkey=AsyncMock(), fleet=fleet)
    identifier = uuid4()
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client,
    ):
        response = await client.patch(
            f"/admin/nodes/{identifier}",
            headers={"Authorization": "Bearer " + token} if token else {},
            json={"name": "timeweb-rus-001", "group": "INTERMEDIATE"},
        )
        assert response.status_code == status
        if status == 200:
            assert response.json()["group"] == "INTERMEDIATE"
            assert fleet.update_node.await_args.args[0] == identifier
            invalid = await client.patch(
                f"/admin/nodes/{identifier}",
                headers={"Authorization": "Bearer " + token},
                json={"name": "node", "group": "UNKNOWN"},
            )
            assert invalid.status_code == 422
            fleet.update_node.assert_awaited_once()
        else:
            fleet.update_node.assert_not_called()


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


def test_zero_rating_slots_repeat_every_three_minutes_without_synchronizing_nodes():
    roster = [UUID(int=index) for index in range(1, 4)]
    slots = [monitoring_slot(item, NOW, roster, rapid=True) for item in roster]
    assert all(NOW < slot <= NOW + timedelta(minutes=3) for slot in slots)
    assert len(set(slots)) == 3
    assert min(abs((a - b).total_seconds()) for a in slots for b in slots if a != b) >= 30
    for identifier, slot in zip(roster, slots, strict=True):
        assert monitoring_slot(identifier, slot, roster, rapid=True) == slot + timedelta(minutes=3)
        assert monitoring_slot(identifier, NOW, roster, rapid=False) == hourly_slot(
            identifier, NOW, roster
        )


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


def test_default_capacity_and_speed_target_match_operator_policy():
    assert (
        NodeInput(
            name="new-node",
            country_code="DE",
            host="1.1.1.1",
            credential_ref="test",
            expected_egress_ips=["1.1.1.1"],
        ).capacity
        == 20
    )
    assert settings().fleet_speed_target_mbps == 30
    full = healthy(connection_ms=500, download_mbps=30, upload_mbps=30)
    assert server_quality([full], 20, NOW)["quality"] == 100
    loaded = full.model_copy(update={"active_connections": 10})
    assert server_quality([loaded], 20, NOW)["quality"] == 90
    assert server_quality([full.model_copy(update={"upload_mbps": 12})], 20, NOW)["quality"] == 91
    with pytest.raises(ValidationError):
        NodeUpdate(name="new-node", group="FREE", capacity=0)


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


async def test_active_users_still_receive_full_synthetic_probe():
    method = AsyncMock()
    method.inspect.return_value = MethodState(installed=True, authorized_connections=1)
    method.probe.return_value = healthy(active_connections=1, authorized_connections=1)
    claim = Claim(uuid4(), uuid4(), node(), node(), "wireguard", "CHECK", {})
    _, observed = await FleetWorker(AsyncMock(), {"wireguard": method}).execute(claim)
    assert observed.mode == "SYNTHETIC"
    method.probe.assert_awaited_once_with(claim.source, claim.target, claim.id)
    method.observe.assert_not_called()


async def test_probe_preserves_customer_load_for_weighted_score():
    transport = AsyncMock()
    state = MethodState(
        installed=True,
        public_key=PUBKEY,
        configuration={"address": "10.88.0.1/24", "listen_port": 51820, "mtu": 1380},
        active_connections=25,
        authorized_connections=30,
    )

    async def call(target, action, payload=None, **kwargs):
        return {
            "inspect": state.model_dump(),
            "prepare": {"public_key": PUBKEY},
            "grant": {},
            "revoke": {"removed": True},
            "dispose": {"removed": True},
            "probe": healthy(connection_ms=200, download_mbps=150, upload_mbps=150).model_dump(
                mode="json"
            ),
        }[action]

    transport.call.side_effect = call
    observed = await WireGuardMethod(transport).probe(node(), node(), uuid4())
    assert observed.mode == "SYNTHETIC" and observed.active_connections == 25
    assert observed.authorized_connections == 30
    result = server_quality([observed], 100, NOW)
    assert result["available"] and result["quality"] == 95
    assert "observe" not in [item.args[1] for item in transport.call.await_args_list]


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


async def test_ssh_reuses_connection_without_weakening_host_validation(tmp_path, monkeypatch):
    key, hosts = tmp_path / "key", tmp_path / "hosts"
    key.write_text("test fixture, not a private key")
    hosts.write_text("test fixture")
    command = AsyncMock(return_value=b'{"installed": false}')
    monkeypatch.setattr("prettylisavpn.fleet.ssh.process", command)
    transport = SshTransport(
        {"test": Credential(host="1.1.1.1", user="root", key_file=str(key), known_hosts=str(hosts))}
    )
    target = node()
    await transport.call(target, "inspect")
    await transport.call(target, "observe")
    first, second = (item.args[0] for item in command.await_args_list)
    assert first == second
    assert "ControlMaster=auto" in first and "ControlPersist=60" in first
    assert "StrictHostKeyChecking=yes" in first and "IdentitiesOnly=yes" in first
    assert f"UserKnownHostsFile={hosts}" in first
    await transport.close()
    assert command.await_args.args[0][-3:-1] == ["-O", "exit"]


def test_acceptance_report_requires_complete_evidence_not_elapsed_time():
    good = healthy().model_dump(mode="json")
    assert assess(24, [good] * 24, 0)["passed"]
    assert not assess(24, [good] * 23, 0)["passed"]
    assert not assess(24, [good] * 24, 1)["passed"]
    failed = {
        **good,
        "status": "UNKNOWN",
        "code": "CLEANUP_UNCONFIRMED",
        "cleanup_confirmed": False,
    }
    result = assess(24, [good] * 23 + [failed], 0)
    assert not result["passed"] and result["failure_codes"] == ["CLEANUP_UNCONFIRMED"]
    assert not assess(0, [], 0)["passed"]
