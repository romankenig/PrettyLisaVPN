import os
from dataclasses import dataclass
from datetime import timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from prettylisavpn.auth.tokens import AccessTokenService
from prettylisavpn.auth_sessions.domain import IssuedAuthSession
from prettylisavpn.auth_sessions.model import AuthSessionRecord
from prettylisavpn.auth_sessions.repository import AuthSessionRepository
from prettylisavpn.auth_sessions.service import AuthSessionService
from prettylisavpn.config import Settings
from prettylisavpn.connections import Postgres
from prettylisavpn.devices.domain import Device, DevicePlatform, DeviceStatus
from prettylisavpn.devices.model import DeviceRecord
from prettylisavpn.devices.repository import DeviceRepository
from prettylisavpn.devices.service import MAX_ACTIVE_DEVICES, DeviceService
from prettylisavpn.main import create_app
from prettylisavpn.product_events.domain import ProductEventName
from prettylisavpn.subscriptions.repository import SubscriptionRepository
from prettylisavpn.users.domain import User, normalize_email
from prettylisavpn.users.model import UserRecord
from prettylisavpn.users.repository import UserRepository
from prettylisavpn.users.service import UserService

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1",
        reason="Set RUN_INTEGRATION_TESTS=1 with PostgreSQL running",
    ),
]


class FakeDependency:
    def __init__(self) -> None:
        self.otp = AsyncMock()

    async def ping(self) -> None:
        return None

    async def close(self) -> None:
        return None


@dataclass(frozen=True)
class DeviceState:
    user: User
    devices: list[Device]
    sessions: list[IssuedAuthSession]
    access_token: str


def settings() -> Settings:
    return Settings(
        _env_file=None,
        otp_hmac_secret=f"device-management-integration-secret-{uuid4().hex}",
    )


async def create_state(
    postgres: Postgres,
    config: Settings,
    email: str,
    *,
    device_count: int = 1,
    extra_current_session: bool = False,
) -> DeviceState:
    async with postgres.session() as session:
        async with session.begin():
            user = await UserService(
                UserRepository(session), SubscriptionRepository(session)
            ).create(email)
            device_service = DeviceService(DeviceRepository(session))
            devices = [
                await device_service.register(
                    user.id,
                    uuid4(),
                    DevicePlatform.WINDOWS,
                    f"Device {index}",
                )
                for index in range(device_count)
            ]
            session_service = AuthSessionService(
                AuthSessionRepository(session),
                timedelta(seconds=config.refresh_token_ttl_seconds),
            )
            sessions = [await session_service.issue(user.id, device.id) for device in devices]
            if extra_current_session:
                sessions.append(await session_service.issue(user.id, devices[0].id))
    access_token = (
        AccessTokenService(config).issue(user.id, devices[0].id, sessions[0].session.id).token
    )
    return DeviceState(user, devices, sessions, access_token)


async def cleanup_users(postgres: Postgres, *emails: str) -> None:
    async with postgres.session() as session:
        await session.execute(
            delete(UserRecord).where(
                UserRecord.email.in_([normalize_email(email) for email in emails])
            )
        )
        await session.commit()


def headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_list_returns_only_owned_devices_and_marks_current():
    config = settings()
    postgres = Postgres(config)
    own_email = f"devices-own-{uuid4()}@example.com"
    other_email = f"devices-other-{uuid4()}@example.com"
    own = await create_state(postgres, config, own_email, device_count=2)
    other = await create_state(postgres, config, other_email)
    app = create_app(config, postgres=postgres, valkey=FakeDependency(), product_events=AsyncMock())

    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/devices", headers=headers(own.access_token))
        assert response.status_code == 200
        payload = response.json()
        assert {item["id"] for item in payload} == {str(device.id) for device in own.devices}
        assert str(other.devices[0].id) not in {item["id"] for item in payload}
        assert [item["is_current"] for item in payload] == [True, False]
        assert all(
            {"device_name", "platform", "status", "created_at", "updated_at", "revoked_at"}
            <= item.keys()
            for item in payload
        )
        await cleanup_users(postgres, own_email, other_email)


async def test_revoke_hides_foreign_device_identity_and_changes_nothing():
    config = settings()
    postgres = Postgres(config)
    own_email = f"revoke-own-{uuid4()}@example.com"
    other_email = f"revoke-other-{uuid4()}@example.com"
    own = await create_state(postgres, config, own_email)
    other = await create_state(postgres, config, other_email)
    events = AsyncMock()
    app = create_app(config, postgres=postgres, valkey=FakeDependency(), product_events=events)

    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.delete(
                f"/devices/{other.devices[0].id}", headers=headers(own.access_token)
            )
        assert response.status_code == 404
        assert response.json() == {"error": {"code": "device_not_found"}}
        async with postgres.session() as session:
            device = await session.get(DeviceRecord, other.devices[0].id)
            auth_session = await session.get(AuthSessionRecord, other.sessions[0].session.id)
            assert device is not None and device.status is DeviceStatus.ACTIVE
            assert auth_session is not None and auth_session.revoked_at is None
        events.record.assert_not_awaited()
        await cleanup_users(postgres, own_email, other_email)


async def test_revoke_device_invalidates_all_its_sessions_and_records_event():
    config = settings()
    postgres = Postgres(config)
    email = f"revoke-sessions-{uuid4()}@example.com"
    state = await create_state(postgres, config, email, device_count=2)
    events = AsyncMock()
    app = create_app(config, postgres=postgres, valkey=FakeDependency(), product_events=events)
    target = state.devices[1]
    target_session = state.sessions[1]

    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            revoked = await client.delete(
                f"/devices/{target.id}", headers=headers(state.access_token)
            )
            refresh = await client.post(
                "/auth/refresh",
                json={
                    "session_id": str(target_session.session.id),
                    "refresh_token": target_session.refresh_token,
                },
            )
        assert revoked.status_code == 200
        assert revoked.json()["device"]["status"] == "REVOKED"
        assert revoked.json()["device"]["is_current"] is False
        assert refresh.status_code == 401
        async with postgres.session() as session:
            revoked_session = await session.get(AuthSessionRecord, target_session.session.id)
            current_session = await session.get(AuthSessionRecord, state.sessions[0].session.id)
            assert revoked_session is not None and revoked_session.revoked_at is not None
            assert current_session is not None and current_session.revoked_at is None
        events.record.assert_awaited_once_with(
            ProductEventName.DEVICE_REVOKED,
            user_id=state.user.id,
            device_id=target.id,
        )
        await cleanup_users(postgres, email)


async def test_revoke_current_device_returns_success_then_invalidates_access():
    config = settings()
    postgres = Postgres(config)
    email = f"revoke-current-{uuid4()}@example.com"
    state = await create_state(postgres, config, email, extra_current_session=True)
    app = create_app(config, postgres=postgres, valkey=FakeDependency(), product_events=AsyncMock())

    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            revoked = await client.delete(
                f"/devices/{state.devices[0].id}", headers=headers(state.access_token)
            )
            after = await client.get("/devices", headers=headers(state.access_token))
        assert revoked.status_code == 200
        assert revoked.json()["device"]["is_current"] is True
        assert after.status_code == 401
        assert after.json() == {"error": {"code": "invalid_session"}}
        async with postgres.session() as session:
            records = [
                await session.get(AuthSessionRecord, issued.session.id) for issued in state.sessions
            ]
            assert all(record is not None and record.revoked_at is not None for record in records)
        await cleanup_users(postgres, email)


async def test_revocation_recovers_one_slot_from_five_device_limit():
    config = settings()
    postgres = Postgres(config)
    email = f"device-limit-recovery-{uuid4()}@example.com"
    state = await create_state(postgres, config, email, device_count=MAX_ACTIVE_DEVICES)
    app = create_app(config, postgres=postgres, valkey=FakeDependency(), product_events=AsyncMock())

    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.delete(
                f"/devices/{state.devices[-1].id}", headers=headers(state.access_token)
            )
        assert response.status_code == 200
        async with postgres.session() as session:
            async with session.begin():
                replacement = await DeviceService(DeviceRepository(session)).register(
                    state.user.id,
                    uuid4(),
                    DevicePlatform.ANDROID,
                    "Replacement",
                )
                assert replacement.status is DeviceStatus.ACTIVE
                assert await DeviceRepository(session).count_active(state.user.id) == 5
        await cleanup_users(postgres, email)
