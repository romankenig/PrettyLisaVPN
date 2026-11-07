"""Actual PostgreSQL: reinstall identity, admission fencing and independent FREE time."""
# ruff: noqa: F811

import asyncio
import sys
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy import delete, select
from test_client_vpn import KEY
from test_client_vpn_integration import pytestmark, vpn_state  # noqa: F401
from test_fleet import settings
from test_fleet_integration import fleet_state  # noqa: F401
from test_short_quota_integration import freeze

from prettylisavpn.auth.router import account_router
from prettylisavpn.auth.session_service import AuthenticatedSessionService, InvalidSessionError
from prettylisavpn.auth_sessions.model import AuthSessionRecord
from prettylisavpn.billing.operations import BillingOperationsService
from prettylisavpn.client_vpn.domain import ConnectRequest
from prettylisavpn.client_vpn.model import ClientLeaseRecord, FreeQuotaResetRecord
from prettylisavpn.client_vpn.quota import ClientQuotaRepository
from prettylisavpn.demo import service as demo_service_module
from prettylisavpn.demo.domain import DemoRateLimitedError, RegistrationRequiredError
from prettylisavpn.demo.model import DemoDeviceRecord
from prettylisavpn.demo.router import router
from prettylisavpn.demo.service import DemoService, RedisAdmissionLimit
from prettylisavpn.devices.management import DeviceManagementService
from prettylisavpn.devices.model import DeviceRecord
from prettylisavpn.devices.router import router as devices_router
from prettylisavpn.fleet.domain import FleetError
from prettylisavpn.users.model import UserRecord


@pytest.fixture
async def guest(vpn_state):
    pg, vpn, worker, provider, registered = vpn_state
    config = settings(
        client_vpn_enabled=True,
        demo_enabled=True,
        demo_identity_secret="isolated-demo-key-not-a-live-secret",
    )
    auth = AuthenticatedSessionService(pg, AsyncMock(), config)
    service = DemoService(pg, config, SimpleNamespace(admit=AsyncMock()))
    key = uuid4().hex * 2
    result = await service.login(key, "192.0.2.1")
    vpn.auth = auth
    try:
        yield pg, vpn, worker, provider, registered, service, key, result, auth
    finally:
        async with pg.session() as session, session.begin():
            await session.execute(
                delete(ClientLeaseRecord).where(ClientLeaseRecord.user_id == result.user.id)
            )
            await session.execute(
                delete(DemoDeviceRecord).where(DemoDeviceRecord.user_id == result.user.id)
            )
            await session.execute(delete(UserRecord).where(UserRecord.id == result.user.id))


async def test_guest_endpoint_profile_and_successful_reinstallation_keep_one_device(guest):
    pg, _, _, _, _, service, key, result, auth = guest
    app = FastAPI()
    app.include_router(router)
    app.include_router(account_router)
    app.state.demo, app.state.authenticated_sessions = service, auth
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
        response = await client.post("/auth/demo", json={"device_key": key})
        assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
        login = response.json()
        assert login["user"]["id"] == str(result.user.id)
        assert login["device"]["id"] == str(result.device.id)
        assert login["subscription"]["plan"] == "DEMO"
        me = (
            await client.get("/me", headers={"Authorization": "Bearer " + login["access_token"]})
        ).json()
        assert me["email"] is None and me["entitlements"]["free_seconds_usable"] == 900
        assert me["active_device_count"] == 1
    with pytest.raises(InvalidSessionError):
        await auth.authenticate(result.access_token.token)
    async with pg.session() as session:
        assert (
            len(
                (
                    await session.scalars(
                        select(DeviceRecord).where(DeviceRecord.user_id == result.user.id)
                    )
                ).all()
            )
            == 1
        )


async def test_concurrent_guest_logins_share_identity_and_only_last_session_survives(guest):
    pg, _, _, _, _, service, key, result, _ = guest
    results = await asyncio.gather(*(service.login(key, "192.0.2.1") for _ in range(3)))
    assert {value.user.id for value in results} == {result.user.id}
    assert {value.device.id for value in results} == {result.device.id}
    async with pg.session() as session:
        active = (
            await session.scalars(
                select(AuthSessionRecord).where(
                    AuthSessionRecord.user_id == result.user.id,
                    AuthSessionRecord.revoked_at.is_(None),
                )
            )
        ).all()
        assert len(active) == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"country": "DE"},
        {"traffic_mode": "include"},
        {"traffic_mode": "exclude"},
        {"method": "https_proxy"},
    ],
)
async def test_guest_cannot_request_paid_selection_or_split_or_browser_proxy(guest, changes):
    pg, vpn, _, provider, _, _, _, result, _ = guest
    with pytest.raises(FleetError, match="REGISTRATION_REQUIRED"):
        await vpn.connect(
            result.access_token.token, ConnectRequest(public_key=KEY, **changes), uuid4()
        )
    provider.grant_access.assert_not_awaited()
    async with pg.session() as session:
        assert (
            await session.scalar(
                select(ClientLeaseRecord.id).where(ClientLeaseRecord.user_id == result.user.id)
            )
            is None
        )


@pytest.mark.parametrize("start_hour", [0, 12, 23])
async def test_reinstall_preserves_spent_time_until_confirmed_removal_and_free_is_independent(
    guest, monkeypatch, start_hour
):
    pg, vpn, worker, provider, registered, service, key, result, auth = guest
    clock = freeze(monkeypatch)
    clock.value = clock.value.replace(hour=start_hour)
    monkeypatch.setattr(demo_service_module, "datetime", clock)
    token = result.access_token.token
    lease = await vpn.connect(token, ConnectRequest(public_key=KEY), uuid4())
    assert lease["expires_at"] == clock.value + timedelta(seconds=900)
    identifier = UUID(lease["id"])
    assert await worker.tick()
    await vpn.get(token, identifier, "probe", "1.1.1.1")
    clock.value += timedelta(seconds=100)
    fresh = await service.login(key, "192.0.2.1")
    async with pg.session() as session:
        row = await session.get(ClientLeaseRecord, identifier)
        assert row.next_attempt_at == clock.value
    provider.revoke_access.return_value = False
    assert await worker.tick()
    async with pg.session() as session:
        # No refund of the outstanding 180-second node grant on logout/reinstallation.
        assert (
            await ClientQuotaRepository(session).remaining_free_seconds(result.user.id, clock.value)
            == 720
        )
    provider.revoke_access.return_value = True
    clock.value += timedelta(seconds=11)
    assert await worker.tick()
    async with pg.session() as session:
        quota = ClientQuotaRepository(session)
        assert await quota.remaining_free_seconds(result.user.id, clock.value) == 789
        assert await quota.remaining_free_seconds(registered.user_id, clock.value) == 3600
        assert (await quota.display(result.user.id, clock.value)).daily_limit_seconds == 900
        assert (
            await quota.remaining_free_seconds(result.user.id, clock.value + timedelta(days=1))
            == 900
        )
    assert (await auth.authenticate(fresh.access_token.token)).is_demo


async def test_guest_quota_exhaustion_is_not_reset_by_free_admin_reset_or_relogin(
    guest, monkeypatch
):
    pg, vpn, _, _, _, service, key, result, _ = guest
    clock = freeze(monkeypatch)
    monkeypatch.setattr(demo_service_module, "datetime", clock)
    lease = await vpn.connect(result.access_token.token, ConnectRequest(public_key=KEY), uuid4())
    async with pg.session() as session, session.begin():
        row = await session.get(ClientLeaseRecord, UUID(lease["id"]))
        row.activated_at = clock.value
        row.quota_reserved_until = row.expires_at
        row.removed_at = row.expires_at
        row.status = "CLOSED"
        session.add(
            FreeQuotaResetRecord(
                id=uuid4(),
                user_id=result.user.id,
                day=clock.value.date(),
                reset_at=clock.value,
                allowance_seconds=3600,
            )
        )
    fresh = await service.login(key, "192.0.2.1")
    with pytest.raises(FleetError, match="DEMO_QUOTA_EXHAUSTED"):
        await vpn.connect(fresh.access_token.token, ConnectRequest(public_key=KEY), uuid4())


async def test_guest_cannot_open_billing_operations(guest):
    pg, _, _, _, _, _, _, result, auth = guest
    identity = await auth.authenticate(result.access_token.token)
    with pytest.raises(RegistrationRequiredError):
        identity.require_registered()
    with pytest.raises(RegistrationRequiredError):
        await BillingOperationsService(pg, auth, None).get(result.access_token.token, uuid4())


async def test_guest_device_management_is_scoped_and_revocation_preserves_quota(guest, monkeypatch):
    pg, vpn, worker, provider, registered, service, key, result, auth = guest
    clock = freeze(monkeypatch)
    monkeypatch.setattr(demo_service_module, "datetime", clock)
    token = result.access_token.token
    lease = await vpn.connect(token, ConnectRequest(public_key=KEY), uuid4())
    assert await worker.tick()
    await vpn.get(token, UUID(lease["id"]), "probe", "1.1.1.1")
    clock.value += timedelta(seconds=100)
    app = FastAPI()
    app.include_router(devices_router)
    app.state.device_management = DeviceManagementService(pg, auth, AsyncMock(), settings())
    headers = {"Authorization": "Bearer " + token}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
        listing = await client.get("/devices", headers=headers)
        assert listing.status_code == 200
        assert [item["id"] for item in listing.json()] == [str(result.device.id)]
        assert listing.json()[0]["is_current"]
        foreign = await client.delete(f"/devices/{registered.device_id}", headers=headers)
        assert foreign.status_code == 404
        revoked = await client.delete(f"/devices/{result.device.id}", headers=headers)
        assert revoked.status_code == 200
        assert revoked.json()["device"]["status"] == "REVOKED"
        assert (await client.get("/devices", headers=headers)).status_code in (401, 403)
    # Device revocation also removes the active VPN grant before a new guest login.
    assert await worker.tick()
    provider.revoke_access.assert_awaited()
    async with pg.session() as session:
        remaining = await ClientQuotaRepository(session).remaining_free_seconds(
            result.user.id, clock.value
        )
        assert 0 < remaining < 900
    fresh = await service.login(key, "192.0.2.1")
    assert fresh.device.id == result.device.id and fresh.user.id == result.user.id
    assert (await auth.authenticate(fresh.access_token.token)).is_demo
    async with pg.session() as session:
        assert (
            await ClientQuotaRepository(session).remaining_free_seconds(result.user.id, clock.value)
            == remaining
        )


async def test_populated_demo_migration_cannot_be_dropped_to_reset_daily_quota(guest):
    pg, _, _, _, _, _, _, result, _ = guest
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "alembic",
        "downgrade",
        "0045_platega_subscriptions",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, errors = await asyncio.wait_for(process.communicate(), timeout=30)
    assert process.returncode != 0
    assert b"DEMO identity and quota data must be retained" in errors
    async with pg.session() as session:
        assert (
            await session.scalar(
                select(DemoDeviceRecord.user_id).where(DemoDeviceRecord.user_id == result.user.id)
            )
            == result.user.id
        )


async def test_real_redis_guest_admission_has_device_and_ip_limits_with_expiry():
    redis = Redis.from_url(settings().valkey_url.get_secret_value())
    limiter = RedisAdmissionLimit(redis)
    prefix = uuid4().hex
    keys = []
    try:
        ip, device = prefix + "-ip", prefix + "-device"
        keys += ["demo:ip:" + ip, "demo:device:" + device]
        for _ in range(10):
            await limiter.admit(ip, device)
        with pytest.raises(DemoRateLimitedError):
            await limiter.admit(ip, device)
        other_ip = prefix + "-shared-ip"
        keys.append("demo:ip:" + other_ip)
        for i in range(30):
            unique_device = prefix + "-" + str(i)
            keys.append("demo:device:" + unique_device)
            await limiter.admit(other_ip, unique_device)
        with pytest.raises(DemoRateLimitedError):
            await limiter.admit(other_ip, prefix + "-over-limit")
        for key in keys:
            assert 0 < await redis.ttl(key) <= 3600
    finally:
        await redis.delete(*keys)
        await redis.aclose()
