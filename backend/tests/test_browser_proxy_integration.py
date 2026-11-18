"""Proxy leases share real PostgreSQL quota, device ownership and cleanup."""

import os
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, update
from test_client_vpn import KEY
from test_client_vpn_integration import connect, vpn_state  # noqa: F401
from test_fleet_integration import fleet_state  # noqa: F401
from test_managed_vpn_integration import managed_state  # noqa: F401

from prettylisavpn.client_vpn.domain import ConnectRequest
from prettylisavpn.client_vpn.model import ClientLeaseRecord
from prettylisavpn.client_vpn.quota import ClientQuotaRepository
from prettylisavpn.devices.domain import DevicePlatform
from prettylisavpn.devices.model import DeviceRecord
from prettylisavpn.fleet.domain import FleetError
from prettylisavpn.fleet.model import FleetMethodRecord, FleetNodeRecord
from prettylisavpn.fleet.service import FleetService

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1", reason="Requires disposable PostgreSQL"
    ),
]


@pytest.fixture
async def browser_state(managed_state):  # noqa: F811
    postgres, service, worker, managed, wireguard, identity = managed_state
    async with postgres.session() as session, session.begin():
        await session.execute(
            update(DeviceRecord)
            .where(DeviceRecord.id == identity.device_id)
            .values(platform=DevicePlatform.CHROME_EXTENSION)
        )
        for method in await session.scalars(
            select(FleetMethodRecord).where(FleetMethodRecord.method == "managed")
        ):
            method.configuration = {
                **method.configuration,
                "proxy_host": "proxy-de.prettylisavpn.com",
            }
    return postgres, service, worker, managed, wireguard, identity


async def test_browser_cannot_create_system_tunnel_and_native_cannot_create_proxy(browser_state):
    postgres, service, _, _, _, identity = browser_state
    with pytest.raises(FleetError, match="ACCOUNT_UNAVAILABLE"):
        await connect(service, method="wireguard")
    with pytest.raises(FleetError, match="ACCOUNT_UNAVAILABLE"):
        await connect(service, method="vless")
    async with postgres.session() as session, session.begin():
        await session.execute(
            update(DeviceRecord)
            .where(DeviceRecord.id == identity.device_id)
            .values(platform=DevicePlatform.WINDOWS)
        )
    with pytest.raises(FleetError, match="ACCOUNT_UNAVAILABLE"):
        await connect(service, method="https_proxy")


async def test_proxy_lifecycle_and_missed_heartbeat_revoke(browser_state):
    postgres, service, worker, managed, wireguard, _ = browser_state
    created = await connect(service, method="https_proxy", country="DE")
    identifier = UUID(created["id"])
    assert created["heartbeat_required"] is True
    assert await worker.tick()
    ready = await service.get("token", identifier)
    proxy = ready["configuration"]["proxy"]
    assert proxy["scheme"] == "https"
    assert proxy["host"] == "proxy-de.prettylisavpn.com"
    assert proxy["username"] == str(identifier) and UUID(proxy["password"])
    assert "engine_profile" not in ready["configuration"]
    assert ready["configuration"]["dns"] == "remote"
    assert managed.grant_access.await_args.args[1].method == "https_proxy"
    wireguard.grant_access.assert_not_called()
    assert not (await service.get("token", identifier, "probe", "8.8.8.8"))["verified"]
    assert (await service.get("token", identifier, "probe", "1.1.1.1"))["verified"]
    await service.get("token", identifier, "heartbeat")
    async with postgres.session() as session, session.begin():
        await session.execute(
            update(ClientLeaseRecord)
            .where(ClientLeaseRecord.id == identifier)
            .values(
                heartbeat_at=datetime.now(UTC) - timedelta(seconds=91),
                next_attempt_at=datetime.now(UTC),
            )
        )
    assert await worker.tick()
    assert (await service.get("token", identifier))["status"] == "CLOSED"
    managed.revoke_access.assert_awaited_once()


async def test_unconfigured_proxy_node_is_not_allocated(browser_state):
    postgres, service, _, _, _, _ = browser_state
    async with postgres.session() as session, session.begin():
        for method in await session.scalars(
            select(FleetMethodRecord).where(FleetMethodRecord.method == "managed")
        ):
            method.configuration = {}
    with pytest.raises(FleetError, match="VPN_NO_AVAILABLE_NODE"):
        await connect(service, method="https_proxy")


async def test_chrome_demo_proxy_uses_900_second_budget_auto_and_confirmed_cleanup(browser_state):
    from types import SimpleNamespace

    from pydantic import SecretStr
    from sqlalchemy import delete

    from prettylisavpn.auth.session_service import AuthenticatedSessionService
    from prettylisavpn.demo.model import DemoDeviceRecord
    from prettylisavpn.demo.service import DemoService
    from prettylisavpn.users.model import UserRecord

    postgres, service, worker, managed, _, _ = browser_state
    config = service.settings.model_copy(
        update={
            "demo_enabled": True,
            "demo_identity_secret": SecretStr("chrome-demo-integration-secret-" + "a" * 32),
        }
    )
    guest = await DemoService(postgres, config, SimpleNamespace(admit=AsyncMock())).login(
        uuid4().hex * 2, "192.0.2.1", DevicePlatform.CHROME_EXTENSION
    )
    service.auth = AuthenticatedSessionService(postgres, AsyncMock(), config)
    token = guest.access_token.token
    try:
        for options in [
            {"country": "DE"},
            {"traffic_mode": "include"},
            {"traffic_mode": "exclude"},
        ]:
            with pytest.raises(FleetError, match="REGISTRATION_REQUIRED"):
                await service.connect(
                    token, ConnectRequest(public_key=KEY, method="https_proxy", **options), uuid4()
                )
        with pytest.raises(FleetError, match="ACCOUNT_UNAVAILABLE"):
            await service.connect(token, ConnectRequest(public_key=KEY), uuid4())
        before = datetime.now(UTC)
        created = await service.connect(
            token, ConnectRequest(public_key=KEY, method="https_proxy"), uuid4()
        )
        identifier = UUID(created["id"])
        midnight = (before + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        assert created["expires_at"] <= min(before + timedelta(seconds=901), midnight)
        assert await worker.tick()
        assert (await service.get(token, identifier))["configuration"]["scope"] == "browser"
        assert (await service.get(token, identifier, "probe", "1.1.1.1"))["verified"]
        async with postgres.session() as session:
            assert (
                await ClientQuotaRepository(session).display(guest.user.id, datetime.now(UTC))
            ).daily_limit_seconds == 900
        await service.get(token, identifier, "revoke")
        assert await worker.tick()
        assert (await service.get(token, identifier))["status"] == "CLOSED"
        managed.revoke_access.assert_awaited_once()
    finally:
        async with postgres.session() as session, session.begin():
            await session.execute(
                delete(ClientLeaseRecord).where(ClientLeaseRecord.user_id == guest.user.id)
            )
            await session.execute(
                delete(DemoDeviceRecord).where(DemoDeviceRecord.user_id == guest.user.id)
            )
            await session.execute(delete(UserRecord).where(UserRecord.id == guest.user.id))


async def test_browser_country_selection_filters_proxy_capability_and_free_nodes(browser_state):
    postgres, service, _, _, _, _ = browser_state
    fleet = FleetService(postgres, service.settings)
    async with postgres.session() as session:
        nodes = list(await session.scalars(select(FleetNodeRecord)))
    fleet.monitoring = AsyncMock(
        return_value={
            "nodes": [
                {
                    "id": str(node.id),
                    "country_code": node.country_code,
                    "group": node.group,
                    "is_available_for_free": node.is_available_for_free,
                    "available": True,
                    "quality": 90,
                    "capacity": node.capacity,
                }
                for node in nodes
            ]
        }
    )
    assert (await fleet.countries(True, browser_proxy=True))["countries"]
    for node in fleet.monitoring.return_value["nodes"]:
        node["is_available_for_free"] = False
    assert not (await fleet.countries(True, browser_proxy=True))["countries"]
    assert (await fleet.countries(False, browser_proxy=True))["countries"]
    async with postgres.session() as session, session.begin():
        for method in await session.scalars(
            select(FleetMethodRecord).where(FleetMethodRecord.method == "managed")
        ):
            method.configuration = {}
    assert not (await fleet.countries(False, browser_proxy=True))["countries"]
    assert not (await fleet.countries(True, browser_proxy=True, include_locked=True))["countries"]
    assert (await fleet.countries(False))["countries"]


async def test_ip_proxy_requires_client_capability_for_countries_and_allocation(browser_state):
    postgres, service, worker, _, _, _ = browser_state
    async with postgres.session() as session, session.begin():
        for method in await session.scalars(
            select(FleetMethodRecord).where(FleetMethodRecord.method == "managed")
        ):
            method.configuration = {**method.configuration, "proxy_host": "1.1.1.1"}
    with pytest.raises(FleetError, match="VPN_NO_AVAILABLE_NODE"):
        await connect(service, method="https_proxy", country="DE")
    fleet = FleetService(postgres, service.settings)
    async with postgres.session() as session:
        nodes = list(await session.scalars(select(FleetNodeRecord)))
    fleet.monitoring = AsyncMock(
        return_value={
            "nodes": [
                {
                    "id": str(node.id),
                    "country_code": node.country_code,
                    "group": node.group,
                    "is_available_for_free": node.is_available_for_free,
                    "available": True,
                    "quality": 90,
                    "capacity": node.capacity,
                }
                for node in nodes
            ]
        }
    )
    assert not (await fleet.countries(True, browser_proxy=True))["countries"]
    assert (await fleet.countries(True, browser_proxy=True, allow_proxy_ip=True))["countries"]
    data = ConnectRequest(public_key=KEY, method="https_proxy", country="DE")
    key = uuid4()
    created = await service.connect("token", data, key, allow_proxy_ip=True)
    assert (await service.connect("token", data, key))["id"] == created["id"]
    assert await worker.tick()
    ready = await service.get("token", UUID(created["id"]))
    assert ready["configuration"]["proxy"]["host"] == "1.1.1.1"
    assert (await service.get("token", UUID(created["id"]), "probe", "1.1.1.1"))["verified"]
