"""Real PostgreSQL: reservations, concurrency, fencing, revocation and quota release."""

import asyncio
import os
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select, update
from test_auth_sessions_integration import create_device, create_user
from test_client_vpn import KEY
from test_fleet import settings
from test_fleet_integration import configured, fleet_state  # noqa: F401

from prettylisavpn.auth.session_service import AccessIdentity
from prettylisavpn.auth_sessions.model import AuthSessionRecord
from prettylisavpn.auth_sessions.repository import AuthSessionRepository
from prettylisavpn.auth_sessions.service import AuthSessionService
from prettylisavpn.client_vpn.domain import ConnectRequest
from prettylisavpn.client_vpn.model import ClientLeaseRecord
from prettylisavpn.client_vpn.quota import ClientQuotaRepository
from prettylisavpn.client_vpn.service import ClientVpnService
from prettylisavpn.client_vpn.worker import ClientVpnWorker
from prettylisavpn.fleet.domain import FleetError
from prettylisavpn.fleet.model import FleetMethodRecord, FleetNodeRecord, FleetOperationRecord
from prettylisavpn.fleet.worker import FleetWorker
from prettylisavpn.subscriptions.domain import SubscriptionPlan
from prettylisavpn.subscriptions.model import SubscriptionRecord
from prettylisavpn.users.model import UserRecord

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1", reason="Requires disposable PostgreSQL"
    ),
]


@pytest.fixture
async def vpn_state(fleet_state):  # noqa: F811
    postgres, _, nodes = fleet_state
    await configured(postgres, nodes)
    user = await create_user(postgres, f"client-{uuid4()}@example.com")
    device = await create_device(postgres, user.id)
    async with postgres.session() as session, session.begin():
        auth = await AuthSessionService(AuthSessionRepository(session), timedelta(days=30)).issue(
            user.id, device.id
        )
        await session.execute(
            update(FleetMethodRecord)
            .where(FleetMethodRecord.node_id.in_(nodes))
            .values(public_key=KEY)
        )
    identity = AccessIdentity(user.id, device.id, auth.session.id)
    authentication = SimpleNamespace(authenticate=AsyncMock(return_value=identity))
    fleet = SimpleNamespace(
        monitoring=AsyncMock(
            return_value={
                "nodes": [{"id": str(node), "available": True, "quality": 100} for node in nodes]
            }
        )
    )
    service = ClientVpnService(postgres, authentication, settings(client_vpn_enabled=True), fleet)
    provider = SimpleNamespace(grant_access=AsyncMock(), revoke_access=AsyncMock(return_value=True))
    worker = ClientVpnWorker(postgres, provider)
    try:
        yield postgres, service, worker, provider, identity
    finally:
        async with postgres.session() as session, session.begin():
            await session.execute(
                delete(ClientLeaseRecord).where(ClientLeaseRecord.user_id == user.id)
            )
            await session.execute(delete(UserRecord).where(UserRecord.id == user.id))


async def connect(service, **kwargs):
    return await service.connect("token", ConnectRequest(public_key=KEY, **kwargs), uuid4())


async def test_grant_probe_scope_idempotency_and_confirmed_quota_release(vpn_state):
    postgres, service, worker, provider, identity = vpn_state
    key = uuid4()
    data = ConnectRequest(public_key=KEY, country="DE")
    first = await service.connect("token", data, key)
    assert first["status"] == "PROVISIONING" and "configuration" not in first
    assert (await service.connect("token", data, key))["id"] == first["id"]
    identifier = UUID(first["id"])
    assert await worker.tick()
    ready = await service.get("token", identifier)
    assert ready["status"] == "READY"
    assert ready["heartbeat_required"] is False
    assert ready["configuration"]["address"].endswith(".2/32")
    assert provider.grant_access.await_args.args[1].purpose == "client"
    assert not (await service.get("token", identifier, "probe", "2.2.2.2"))["verified"]
    assert (await service.get("token", identifier, "probe", "1.1.1.1"))["verified"]
    async with postgres.session() as session:
        assert (
            await ClientQuotaRepository(session).remaining_free_seconds(
                identity.user_id, datetime.now(UTC)
            )
            == 0
        )
    await service.get("token", identifier, "revoke")
    assert await worker.tick()
    assert (await service.get("token", identifier))["status"] == "CLOSED"
    assert await service.get("token") is None
    async with postgres.session() as session:
        assert (
            await ClientQuotaRepository(session).remaining_free_seconds(
                identity.user_id, datetime.now(UTC)
            )
            >= 3590
        )
    service.auth.authenticate.return_value = AccessIdentity(
        identity.user_id, uuid4(), identity.session_id
    )
    with pytest.raises(FleetError, match="VPN_SESSION_NOT_FOUND"):
        await service.get("token", identifier)


async def test_account_serialization_prevents_double_reservation(vpn_state):
    _, service, _, _, _ = vpn_state
    results = await asyncio.gather(connect(service), connect(service), return_exceptions=True)
    assert sum(isinstance(value, dict) for value in results) == 1
    error = next(value for value in results if isinstance(value, FleetError))
    assert error.code == "VPN_CLEANUP_PENDING"


async def test_free_only_nodes_and_disabled_service(vpn_state):
    _, service, _, _, _ = vpn_state
    with pytest.raises(FleetError, match="VPN_NO_AVAILABLE_NODE"):
        await connect(service, country="US")
    service.settings.client_vpn_enabled = False
    with pytest.raises(FleetError, match="VPN_UNAVAILABLE"):
        await connect(service)


async def test_cancel_during_grant_keeps_revoke_and_stale_finish_is_fenced(vpn_state):
    _, service, worker, _, _ = vpn_state
    identifier = UUID((await connect(service))["id"])
    claim = await worker.claim(datetime.now(UTC))
    assert claim and not claim.revoke
    await service.get("token", identifier, "revoke")
    assert await worker.finish(claim, True)
    assert (await service.get("token", identifier))["status"] == "REVOKING"
    assert await worker.tick()
    assert not await worker.finish(claim, True)
    assert (await service.get("token", identifier))["status"] == "CLOSED"


async def test_unknown_removal_retains_quota_address_and_device(vpn_state):
    postgres, service, worker, provider, identity = vpn_state
    identifier = UUID((await connect(service))["id"])
    await worker.tick()
    await service.get("token", identifier, "revoke")
    provider.revoke_access.return_value = False
    await worker.tick()
    result = await service.get("token", identifier)
    assert result["status"] == "REVOKING" and result["removed_at"] is None
    async with postgres.session() as session:
        assert (
            await ClientQuotaRepository(session).remaining_free_seconds(
                identity.user_id, datetime.now(UTC)
            )
            == 0
        )
    with pytest.raises(FleetError, match="VPN_CLEANUP_PENDING"):
        await connect(service)


@pytest.mark.parametrize("reason", ["logout", "auth_expiry", "expiry", "node_disabled"])
async def test_worker_revokes_lost_or_expired_access(vpn_state, reason):
    postgres, service, worker, _, identity = vpn_state
    identifier = UUID((await connect(service))["id"])
    await worker.tick()
    now = datetime.now(UTC)
    async with postgres.session() as session, session.begin():
        row = await session.get(ClientLeaseRecord, identifier)
        row.next_attempt_at = now
        if reason == "logout":
            auth = await session.get(AuthSessionRecord, identity.session_id)
            auth.revoked_at = now
        elif reason == "auth_expiry":
            auth = await session.get(AuthSessionRecord, identity.session_id)
            auth.expires_at = now - timedelta(seconds=1)
        elif reason == "node_disabled":
            node = await session.get(FleetNodeRecord, row.node_id)
            node.enabled = False
        else:
            row.expires_at = now - timedelta(seconds=1)
    assert await worker.tick()
    assert (await service.get("token", identifier))["status"] == "CLOSED"


@pytest.mark.parametrize("plan", list(SubscriptionPlan))
async def test_ready_access_survives_sleep_but_node_grants_stay_short(vpn_state, plan):
    postgres, service, worker, provider, identity = vpn_state
    now = datetime.now(UTC)
    if plan != SubscriptionPlan.FREE:
        async with postgres.session() as session, session.begin():
            subscription = await session.scalar(
                select(SubscriptionRecord).where(SubscriptionRecord.user_id == identity.user_id)
            )
            subscription.plan = plan
            subscription.current_period_end = now + timedelta(days=2)
    identifier = UUID((await connect(service))["id"])
    await worker.tick()
    async with postgres.session() as session, session.begin():
        row = await session.get(ClientLeaseRecord, identifier)
        row.heartbeat_at = now - (timedelta(minutes=10) if row.is_free else timedelta(hours=12))
        row.next_attempt_at = now
    assert await worker.tick()
    assert (await service.get("token", identifier))["status"] == "READY"
    grant = provider.grant_access.await_args.args[1]
    assert now < grant.expires_at <= datetime.now(UTC) + timedelta(seconds=180)
    provider.revoke_access.assert_not_called()
    # Wake-up reconciliation keeps the same access; it never creates a second peer.
    assert (await service.get("token", identifier, "heartbeat"))["id"] == str(identifier)
    await service.get("token", identifier, "revoke")
    assert await worker.tick()
    assert (await service.get("token", identifier))["removed_at"] is not None


async def test_unfinished_setup_still_expires(vpn_state):
    postgres, service, worker, provider, _ = vpn_state
    identifier = UUID((await connect(service))["id"])
    async with postgres.session() as session, session.begin():
        row = await session.get(ClientLeaseRecord, identifier)
        row.created_at = datetime.now(UTC) - timedelta(seconds=91)
    assert await worker.tick()
    result = await service.get("token", identifier)
    assert result["status"] == "CLOSED" and result["code"] == "VPN_SETUP_TIMEOUT"
    provider.grant_access.assert_not_called()


@pytest.mark.parametrize("kind,allowed", [("CHECK", True), ("CONFIGURE", False)])
async def test_customer_renewal_shares_only_monitoring_lock(vpn_state, kind, allowed):
    postgres, service, worker, _, _ = vpn_state
    identifier = UUID((await connect(service))["id"])
    await worker.tick()
    now, token = datetime.now(UTC), uuid4()
    async with postgres.session() as session, session.begin():
        row = await session.get(ClientLeaseRecord, identifier)
        row.next_attempt_at = now
        node = await session.get(FleetNodeRecord, row.node_id)
        node.lock_owner, node.lock_until = token, now + timedelta(minutes=20)
        operation = FleetOperationRecord(
            node_id=node.id,
            method="wireguard",
            kind=kind,
            request_key=str(uuid4()),
            status="RUNNING",
            claim_token=token,
            lease_until=node.lock_until,
        )
        session.add(operation)
    claim = await worker.claim(now)
    assert (claim is not None) == allowed
    if claim:
        async with postgres.session() as session, session.begin():
            # Even if the check ends first, another fleet operation cannot race
            # the in-flight customer grant.
            node = await session.get(FleetNodeRecord, claim.node.id)
            assert node.lock_owner == token
            node.lock_owner, node.lock_until = None, None
            completed = await session.get(FleetOperationRecord, operation.id)
            completed.status, completed.lease_until = "SUCCEEDED", None
            pending = FleetOperationRecord(
                node_id=node.id,
                method="wireguard",
                kind="CONFIGURE",
                request_key=str(uuid4()),
                next_attempt_at=now,
            )
            session.add(pending)
        assert await FleetWorker(postgres, {}).claim(now) is None
        assert await worker.finish(claim, True)
        assert await FleetWorker(postgres, {}).claim(now + timedelta(seconds=16)) is not None
