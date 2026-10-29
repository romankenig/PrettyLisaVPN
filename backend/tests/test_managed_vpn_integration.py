"""Managed leases use real PostgreSQL admission, quotas, fencing and cleanup."""

import os
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from pydantic import SecretStr
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from test_client_vpn_integration import connect, vpn_state  # noqa: F401
from test_fleet_integration import fleet_state  # noqa: F401

from prettylisavpn.client_vpn.methods import MANAGED_METHODS
from prettylisavpn.client_vpn.model import ClientLeaseRecord
from prettylisavpn.client_vpn.quota import ClientQuotaRepository
from prettylisavpn.fleet.domain import FleetError, ManagedAccess
from prettylisavpn.fleet.model import FleetMethodRecord, FleetNodeRecord

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1", reason="Requires disposable PostgreSQL"
    ),
]


async def test_database_rejects_an_unknown_transport(managed_state):
    postgres, service, _, _, _, _ = managed_state
    created = await connect(service, method="vless", country="DE")
    async with postgres.session() as session, session.begin():
        with pytest.raises(IntegrityError, match="ck_client_lease_method"):
            async with session.begin_nested():
                await session.execute(
                    update(ClientLeaseRecord)
                    .where(ClientLeaseRecord.id == UUID(created["id"]))
                    .values(method="unknown_transport")
                )


@pytest.fixture
async def managed_state(vpn_state):  # noqa: F811
    postgres, service, worker, wireguard, identity = vpn_state
    service.settings.managed_vpn_secret = SecretStr("test-only-managed-key-" + "a" * 32)
    service.settings.managed_vpn_enabled = True
    managed = SimpleNamespace(
        grant_access=AsyncMock(),
        revoke_access=AsyncMock(return_value=True),
        grant_relay=AsyncMock(),
        revoke_relay=AsyncMock(return_value=True),
    )
    worker.managed_method, worker.managed_enabled = managed, True
    async with postgres.session() as session, session.begin():
        nodes = (await session.scalars(select(FleetNodeRecord))).all()
        for node in nodes:
            if node.host == "9.9.9.9":
                node.group = "INTERMEDIATE"
            session.add(
                FleetMethodRecord(
                    node_id=node.id,
                    method="managed",
                    state="READY",
                    configured_at=datetime.now(UTC),
                    public_key="AQ" + "A" * 41,
                    configuration={
                        "server_name": "vpn.example.com",
                        "short_id": "0102030405060708",
                        "certificate_pin": "ab" * 32,
                    },
                )
            )
    yield postgres, service, worker, managed, wireguard, identity


@pytest.mark.parametrize("method", tuple(MANAGED_METHODS))
@pytest.mark.parametrize("relay", [False, True])
async def test_managed_grant_probe_relay_and_confirmed_cleanup(managed_state, method, relay):
    postgres, service, worker, managed, wireguard, identity = managed_state
    selected = method + ("_relay" if relay else "")
    created = await connect(service, method=selected, country="DE")
    identifier = UUID(created["id"])
    assert "configuration" not in created
    assert await worker.tick()
    ready = await service.get("token", identifier)
    assert ready["status"] == "READY" and ready["method"] == selected
    profile = ready["configuration"]["engine_profile"]
    assert profile["method"] == MANAGED_METHODS[method].engine
    assert profile["server"] == ("9.9.9.9" if relay else "1.1.1.1")
    assert profile["session"] == str(identifier)
    access = managed.grant_access.await_args.args[1]
    assert isinstance(access, ManagedAccess) and access.address == ""
    assert 40000 <= access.listen_port <= 49899 and access.method == selected
    wireguard.grant_access.assert_not_awaited()
    if relay:
        forwarded = managed.grant_relay.await_args.args[1]
        assert forwarded.protocol == MANAGED_METHODS[method].network
        assert forwarded.target_port == access.listen_port
        assert 20000 <= profile["port"] <= 29999
    assert not (await service.get("token", identifier, "probe", "9.9.9.9"))["verified"]
    assert (await service.get("token", identifier, "probe", "1.1.1.1"))["verified"]
    await service.get("token", identifier, "revoke")
    assert await worker.tick()
    assert (await service.get("token", identifier))["status"] == "CLOSED"
    managed.revoke_access.assert_awaited_once()
    if relay:
        managed.revoke_relay.assert_awaited_once()
    async with postgres.session() as session:
        assert (
            await ClientQuotaRepository(session).remaining_free_seconds(
                identity.user_id, datetime.now(UTC)
            )
            >= 3590
        )


async def test_disable_blocks_new_access_but_keeps_durable_managed_revocation(managed_state):
    postgres, service, worker, managed, _, _ = managed_state
    identifier = UUID((await connect(service, method="vmess"))["id"])
    assert await worker.tick()
    service.settings.managed_vpn_enabled = False
    with pytest.raises(FleetError, match="VPN_METHOD_UNAVAILABLE"):
        await connect(service, method="vless")
    worker.managed_enabled = False
    managed.revoke_access.return_value = False
    async with postgres.session() as session, session.begin():
        await session.execute(
            update(ClientLeaseRecord)
            .where(ClientLeaseRecord.id == identifier)
            .values(next_attempt_at=datetime.now(UTC))
        )
    assert await worker.tick()
    pending = await service.get("token", identifier)
    assert pending["status"] == "REVOKING" and pending["removed_at"] is None
    managed.revoke_access.return_value = True
    async with postgres.session() as session, session.begin():
        await session.execute(
            update(ClientLeaseRecord)
            .where(ClientLeaseRecord.id == identifier)
            .values(next_attempt_at=datetime.now(UTC))
        )
    assert await worker.tick()
    assert (await service.get("token", identifier))["status"] == "CLOSED"
