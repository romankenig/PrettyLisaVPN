import asyncio
import base64
import os
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from test_auth_verify_otp_integration import (
    AlwaysValidOtp,
    FakeValkey,
    cleanup_user,
    settings,
    verify_body,
)

from prettylisavpn.connections import Postgres
from prettylisavpn.devices.domain import DevicePlatform
from prettylisavpn.devices.repository import DeviceRepository
from prettylisavpn.devices.service import DeviceService
from prettylisavpn.main import create_app
from prettylisavpn.subscriptions.repository import SubscriptionRepository
from prettylisavpn.users.repository import UserRepository
from prettylisavpn.users.service import UserService

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1", reason="Requires test PostgreSQL"
    ),
]


@asynccontextmanager
async def full_account():
    config = settings(
        fleet_enabled=True,
        client_vpn_enabled=True,
        fleet_admin_token="pending-device-admin-" + "a" * 40,
        fleet_monitor_token="pending-device-monitor-" + "b" * 40,
    )
    postgres = Postgres(config)
    email = f"pending-device-{uuid4()}@example.com"
    app = create_app(config, postgres=postgres, valkey=FakeValkey(), otp_service=AlwaysValidOtp())
    async with app.router.lifespan_context(app):
        async with postgres.session() as session, session.begin():
            user = await UserService(
                UserRepository(session), SubscriptionRepository(session)
            ).create(email)
            devices = [
                await DeviceService(DeviceRepository(session)).register(
                    user.id, uuid4(), DevicePlatform.WINDOWS, f"Existing {index}"
                )
                for index in range(5)
            ]
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                yield client, email, devices
        finally:
            await cleanup_user(postgres, email)


async def pending_login(client, email, platform=DevicePlatform.WINDOWS):
    body = verify_body(email, "123456", uuid4())
    body.update(platform=platform.value, allow_device_management=True)
    result = await client.post("/auth/verify-otp", json=body)
    assert result.status_code == 200
    assert result.json()["device"]["status"] == "PENDING"
    return result.json()


@pytest.mark.parametrize("platform", list(DevicePlatform))
async def test_limit_management_and_release_slot_for_every_platform(platform):
    async with full_account() as (client, email, devices):
        login = await pending_login(client, email, platform)
        headers = {"Authorization": "Bearer " + login["access_token"]}
        me = (await client.get("/me", headers=headers)).json()
        assert me["device_limit_reached"] is True and me["active_device_count"] == 5
        listed = (await client.get("/devices", headers=headers)).json()
        assert len(listed) == 6
        assert next(row for row in listed if row["is_current"])["status"] == "PENDING"
        assert (await client.post("/devices/activate", headers=headers)).status_code == 409
        assert (await client.delete(f"/devices/{uuid4()}", headers=headers)).status_code == 404

        # The pending bearer cannot invoke any other private account capability,
        # even when called directly instead of through a disabled client control.
        for path in [
            "/vpn/countries",
            "/vpn/sessions/current",
            "/vpn/traffic/services",
            "/billing/overview",
            "/messages?platform=WINDOWS&app_version=0.30.0",
            f"/support/requests/{uuid4()}",
        ]:
            result = await client.get(path, headers=headers)
            assert result.status_code == 403, (path, result.text)
            assert result.json() == {"error": {"code": "device_limit_reached"}}
        result = await client.post("/billing/portal", headers=headers)
        assert result.status_code == 403
        result = await client.post(
            "/vpn/sessions",
            headers={**headers, "Idempotency-Key": str(uuid4())},
            json={"public_key": base64.b64encode(b"x" * 32).decode(), "country": "AUTO"},
        )
        assert result.status_code == 403

        # Existing admitted installations remain fully usable at five slots, and
        # old clients never receive another installation's new PENDING enum.
        old = await client.post(
            "/auth/verify-otp", json=verify_body(email, "123456", devices[0].installation_id)
        )
        assert old.status_code == 200 and old.json()["device"]["status"] == "ACTIVE"
        old_headers = {"Authorization": "Bearer " + old.json()["access_token"]}
        assert (await client.get("/me", headers=old_headers)).json()[
            "device_limit_reached"
        ] is False
        assert len((await client.get("/devices", headers=old_headers)).json()) == 5

        refreshed = await client.post(
            "/auth/refresh",
            json={
                "session_id": login["session_id"],
                "refresh_token": login["refresh_token"],
                "rotation_id": str(uuid4()),
            },
        )
        assert refreshed.status_code == 200
        headers = {"Authorization": "Bearer " + refreshed.json()["access_token"]}
        assert (await client.get("/me", headers=headers)).json()["device_limit_reached"] is True
        removed = await client.delete(f"/devices/{devices[0].id}", headers=headers)
        assert removed.status_code == 200
        activated = await client.post("/devices/activate", headers=headers)
        assert activated.status_code == 200 and activated.json()["status"] == "ACTIVE"
        assert activated.json()["last_login_at"] == login["device"]["last_login_at"]
        assert (await client.post("/devices/activate", headers=headers)).status_code == 200
        me = (await client.get("/me", headers=headers)).json()
        assert me["device_limit_reached"] is False and me["active_device_count"] == 5
        assert (await client.get("/vpn/countries", headers=headers)).status_code == 200


async def test_two_pending_devices_competing_for_one_slot_never_exceed_five():
    async with full_account() as (client, email, devices):
        first = await pending_login(client, email)
        second = await pending_login(client, email)
        headers = [
            {"Authorization": "Bearer " + login["access_token"]} for login in [first, second]
        ]
        assert (
            await client.delete(f"/devices/{devices[0].id}", headers=headers[0])
        ).status_code == 200
        results = await asyncio.gather(
            *[client.post("/devices/activate", headers=value) for value in headers]
        )
        assert sorted(result.status_code for result in results) == [200, 409]
        summaries = [(await client.get("/me", headers=value)).json() for value in headers]
        assert all(me["active_device_count"] == 5 for me in summaries)
        assert sum(me["device_limit_reached"] for me in summaries) == 1


@pytest.mark.parametrize("action", ["logout", "revoke"])
async def test_pending_logout_or_self_revoke_invalidates_tokens_without_claiming_slot(action):
    async with full_account() as (client, email, _):
        login = await pending_login(client, email)
        headers = {"Authorization": "Bearer " + login["access_token"]}
        if action == "logout":
            result = await client.post("/auth/logout", headers=headers)
        else:
            result = await client.delete(f"/devices/{login['device']['id']}", headers=headers)
        assert result.status_code == 200
        assert (await client.post("/devices/activate", headers=headers)).status_code in (401, 403)
        refreshed = await client.post(
            "/auth/refresh",
            json={
                "session_id": login["session_id"],
                "refresh_token": login["refresh_token"],
            },
        )
        assert refreshed.status_code in (401, 403)
