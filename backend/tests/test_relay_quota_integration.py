"""Both-hop reservations, cleanup, group isolation and account-wide quota display."""

import os
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, update
from test_client_vpn_integration import connect, vpn_state  # noqa: F401
from test_fleet import settings
from test_fleet_integration import fleet_state  # noqa: F401

from prettylisavpn.client_vpn.model import ClientLeaseRecord, FreeQuotaResetRecord
from prettylisavpn.client_vpn.quota import ClientQuotaRepository
from prettylisavpn.client_vpn.reset_quota import reset
from prettylisavpn.fleet.domain import FleetError, NodeUpdate
from prettylisavpn.fleet.model import FleetNodeRecord
from prettylisavpn.fleet.service import FleetService
from prettylisavpn.users.model import UserRecord

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.getenv("RUN_INTEGRATION_TESTS") != "1", reason="Disposable PostgreSQL"),
]


async def prepare_relay(postgres, provider):
    async with postgres.session() as session, session.begin():
        relay = await session.scalar(
            select(FleetNodeRecord).where(FleetNodeRecord.host == "9.9.9.9")
        )
        relay.group, relay.country_code = "INTERMEDIATE", "RU"
        relay.is_available_for_free = False
        identifier = relay.id
    provider.grant_relay = AsyncMock()
    provider.revoke_relay = AsyncMock(return_value=True)
    return identifier


async def test_relay_uses_exit_keys_and_egress_but_intermediate_endpoint(vpn_state):  # noqa: F811
    postgres, service, worker, provider, _ = vpn_state
    relay_id = await prepare_relay(postgres, provider)
    with pytest.raises(FleetError, match="VPN_NO_AVAILABLE_NODE"):
        await connect(service, country="RU")
    created = await connect(service, country="DE", method="wireguard_relay")
    identifier = UUID(created["id"])
    assert await worker.tick()
    ready = await service.get("token", identifier)
    assert ready["status"] == "READY" and ready["method"] == "wireguard_relay"
    assert ready["configuration"]["endpoint"] == "9.9.9.9:20000"
    assert ready["configuration"]["expected_egress_ips"] == ["1.1.1.1"]
    assert ready["intermediate"]["country"] == "RU"
    assert provider.grant_relay.await_args.args[0].id == relay_id
    assert str(provider.grant_relay.await_args.args[1].target_host) == "1.1.1.1"
    assert provider.grant_relay.await_args.args[1].target_port == 51820
    assert provider.grant_access.await_args.args[0].id != relay_id
    assert not (await service.get("token", identifier, "probe", "9.9.9.9"))["verified"]
    assert (await service.get("token", identifier, "probe", "1.1.1.1"))["verified"]
    fleet = FleetService(postgres, settings())
    with pytest.raises(FleetError, match="fleet_node_has_active_access"):
        await fleet.update_node(relay_id, NodeUpdate(name="relay", group="FREE"))
    renamed = await fleet.update_node(relay_id, NodeUpdate(name="relay", group="INTERMEDIATE"))
    assert renamed["name"] == "relay" and not renamed["is_available_for_free"]


@pytest.mark.parametrize("broken_hop", ["relay", "exit"])
async def test_both_removals_required_before_port_and_quota_reuse(vpn_state, broken_hop):  # noqa: F811
    postgres, service, worker, provider, identity = vpn_state
    await prepare_relay(postgres, provider)
    identifier = UUID((await connect(service, method="wireguard_relay"))["id"])
    await worker.tick()
    await service.get("token", identifier, "revoke")
    failing = provider.revoke_relay if broken_hop == "relay" else provider.revoke_access
    failing.side_effect = TimeoutError()
    assert await worker.tick()
    provider.revoke_access.assert_awaited_once()
    provider.revoke_relay.assert_awaited_once()
    assert (await service.get("token", identifier))["status"] == "REVOKING"
    async with postgres.session() as session:
        assert (
            await ClientQuotaRepository(session).remaining_free_seconds(
                identity.user_id, datetime.now(UTC)
            )
            == 0
        )
    with pytest.raises(FleetError, match="VPN_CLEANUP_PENDING"):
        await connect(service, method="wireguard_relay")
    failing.side_effect = None
    failing.return_value = True
    await service.get("token", identifier, "revoke")
    assert await worker.tick()
    assert (await service.get("token", identifier))["status"] == "CLOSED"
    replacement = await connect(service, method="wireguard_relay")
    async with postgres.session() as session:
        row = await session.get(ClientLeaseRecord, UUID(replacement["id"]))
        assert row.relay_port == 20000


async def test_missing_intermediate_does_not_allocate_and_disabled_relay_revokes(vpn_state):  # noqa: F811
    postgres, service, worker, provider, _ = vpn_state
    with pytest.raises(FleetError, match="VPN_NO_AVAILABLE_RELAY"):
        await connect(service, method="wireguard_relay")
    relay_id = await prepare_relay(postgres, provider)
    identifier = UUID((await connect(service, method="wireguard_relay"))["id"])
    await worker.tick()
    async with postgres.session() as session, session.begin():
        await session.execute(
            update(FleetNodeRecord).where(FleetNodeRecord.id == relay_id).values(enabled=False)
        )
        await session.execute(
            update(ClientLeaseRecord)
            .where(ClientLeaseRecord.id == identifier)
            .values(next_attempt_at=datetime.now(UTC))
        )
    assert await worker.tick()
    assert (await service.get("token", identifier))["status"] == "CLOSED"
    provider.revoke_relay.assert_awaited_once()


async def test_display_includes_active_account_reservation_and_reset_preserves_history(vpn_state):  # noqa: F811
    postgres, service, worker, _, identity = vpn_state
    identifier = UUID((await connect(service))["id"])
    await worker.tick()
    now = datetime.now(UTC)
    async with postgres.session() as session:
        email = (await session.get(UserRecord, identity.user_id)).email
        balance = await ClientQuotaRepository(session).display(identity.user_id, now)
        assert balance.available_seconds == 0 and balance.running_sessions == 1
        assert 3500 < balance.usable_seconds <= 3600
        later = await ClientQuotaRepository(session).display(
            identity.user_id, now + timedelta(minutes=5)
        )
        assert 299 <= balance.usable_seconds - later.usable_seconds <= 301
    request_id = uuid4()
    with pytest.raises(FleetError, match="QUOTA_RESET_CLEANUP_REQUIRED"):
        await reset(postgres, email, request_id, now)
    await service.get("token", identifier, "revoke")
    await worker.tick()
    # Simulate earlier actual usage without altering its audit trail during reset.
    async with postgres.session() as session, session.begin():
        row = await session.get(ClientLeaseRecord, identifier)
        row.created_at = now - timedelta(minutes=30)
        row.activated_at = row.created_at
        row.removed_at = now - timedelta(minutes=10)
        row.expires_at = now + timedelta(minutes=30)
    result = await reset(postgres, email, request_id, datetime.now(UTC))
    assert result["available_seconds"] == 3600
    assert (await reset(postgres, email, request_id, datetime.now(UTC)))["repeated"]
    with pytest.raises(FleetError, match="QUOTA_RESET_ALREADY_APPLIED"):
        await reset(postgres, email, uuid4(), datetime.now(UTC))
    async with postgres.session() as session:
        assert await session.get(ClientLeaseRecord, identifier) is not None
        assert await session.get(FreeQuotaResetRecord, request_id) is not None
        quota = ClientQuotaRepository(session)
        assert (await quota.display(identity.user_id, datetime.now(UTC))).usable_seconds == 3600
        tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        assert await quota.remaining_free_seconds(identity.user_id, tomorrow) == 3600
