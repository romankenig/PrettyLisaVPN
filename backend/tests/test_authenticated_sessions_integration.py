"""Authenticated endpoint tests against real PostgreSQL."""

import asyncio
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, update

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
from prettylisavpn.devices.service import DeviceService
from prettylisavpn.main import create_app
from prettylisavpn.subscriptions.repository import SubscriptionRepository
from prettylisavpn.users.domain import User, UserStatus, normalize_email
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
class AuthState:
    user: User
    devices: list[Device]
    issued: IssuedAuthSession
    access_token: str


def settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "otp_hmac_secret": f"authenticated-integration-secret-{uuid4().hex}",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


async def create_auth_state(
    postgres: Postgres,
    config: Settings,
    email: str,
    *,
    device_count: int = 1,
) -> AuthState:
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
                    f"Device {number}",
                )
                for number in range(device_count)
            ]
            issued = await AuthSessionService(
                AuthSessionRepository(session),
                timedelta(seconds=config.refresh_token_ttl_seconds),
            ).issue(user.id, devices[0].id)
    access_token = AccessTokenService(config).issue(user.id, devices[0].id, issued.session.id).token
    return AuthState(user, devices, issued, access_token)


async def cleanup_user(postgres: Postgres, email: str) -> None:
    async with postgres.session() as session:
        await session.execute(delete(UserRecord).where(UserRecord.email == normalize_email(email)))
        await session.commit()


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_refresh_rotates_hash_and_rejects_replayed_token():
    config = settings()
    postgres = Postgres(config)
    email = f"refresh-endpoint-{uuid4()}@example.com"
    state = await create_auth_state(postgres, config, email)
    events = AsyncMock()
    app = create_app(config, postgres=postgres, valkey=FakeDependency(), product_events=events)

    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            body = {
                "session_id": str(state.issued.session.id),
                "refresh_token": state.issued.refresh_token,
            }
            rotated = await client.post("/auth/refresh", json=body)
            replayed = await client.post("/auth/refresh", json=body)

        assert rotated.status_code == 200
        assert replayed.status_code == 401
        assert replayed.json() == {"error": {"code": "invalid_refresh_token"}}
        assert rotated.json()["refresh_token"] != state.issued.refresh_token
        async with postgres.session() as session:
            record = await session.get(AuthSessionRecord, state.issued.session.id)
            assert record is not None
            assert record.refresh_token_hash == AuthSessionService.hash_refresh_token(
                rotated.json()["refresh_token"]
            )
            assert rotated.json()["refresh_token"].encode() not in record.refresh_token_hash
        await cleanup_user(postgres, email)


async def test_concurrent_refresh_allows_old_token_once():
    config = settings()
    postgres = Postgres(config)
    email = f"refresh-concurrent-{uuid4()}@example.com"
    state = await create_auth_state(postgres, config, email)
    app = create_app(config, postgres=postgres, valkey=FakeDependency(), product_events=AsyncMock())
    body = {
        "session_id": str(state.issued.session.id),
        "refresh_token": state.issued.refresh_token,
    }

    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            responses = await asyncio.gather(
                client.post("/auth/refresh", json=body),
                client.post("/auth/refresh", json=body),
            )
        assert sorted(response.status_code for response in responses) == [200, 401]
        await cleanup_user(postgres, email)


@pytest.mark.parametrize("state_kind", ["expired", "revoked"])
async def test_refresh_and_me_reject_expired_or_revoked_session(state_kind: str):
    config = settings()
    postgres = Postgres(config)
    email = f"session-{state_kind}-{uuid4()}@example.com"
    state = await create_auth_state(postgres, config, email)
    async with postgres.session() as session:
        values = (
            {"expires_at": datetime.now(UTC) - timedelta(seconds=1)}
            if state_kind == "expired"
            else {"revoked_at": datetime.now(UTC)}
        )
        await session.execute(
            update(AuthSessionRecord)
            .where(AuthSessionRecord.id == state.issued.session.id)
            .values(**values)
        )
        await session.commit()
    app = create_app(config, postgres=postgres, valkey=FakeDependency(), product_events=AsyncMock())

    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            refreshed = await client.post(
                "/auth/refresh",
                json={
                    "session_id": str(state.issued.session.id),
                    "refresh_token": state.issued.refresh_token,
                },
            )
            me = await client.get("/me", headers=auth_headers(state.access_token))
        assert refreshed.status_code == 401
        assert refreshed.json() == {"error": {"code": "invalid_refresh_token"}}
        assert me.status_code == 401
        assert me.json() == {"error": {"code": "invalid_session"}}
        await cleanup_user(postgres, email)


async def test_logout_revokes_current_session_and_invalidates_both_tokens():
    config = settings()
    postgres = Postgres(config)
    email = f"logout-endpoint-{uuid4()}@example.com"
    state = await create_auth_state(postgres, config, email)
    app = create_app(config, postgres=postgres, valkey=FakeDependency(), product_events=AsyncMock())

    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            logout = await client.post("/auth/logout", headers=auth_headers(state.access_token))
            me = await client.get("/me", headers=auth_headers(state.access_token))
            refresh = await client.post(
                "/auth/refresh",
                json={
                    "session_id": str(state.issued.session.id),
                    "refresh_token": state.issued.refresh_token,
                },
            )
        assert logout.status_code == 200
        assert logout.json() == {"status": "logged_out"}
        assert me.status_code == 401
        assert refresh.status_code == 401
        async with postgres.session() as session:
            record = await session.get(AuthSessionRecord, state.issued.session.id)
            assert record is not None and record.revoked_at is not None
        await cleanup_user(postgres, email)


async def test_me_returns_identity_plan_and_active_device_count():
    config = settings()
    postgres = Postgres(config)
    email = f"me-endpoint-{uuid4()}@example.com"
    state = await create_auth_state(postgres, config, email, device_count=3)
    app = create_app(config, postgres=postgres, valkey=FakeDependency(), product_events=AsyncMock())

    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/me", headers=auth_headers(state.access_token))
        assert response.status_code == 200
        assert response.json() == {
            "id": str(state.user.id),
            "email": email,
            "plan": "FREE",
            "active_device_count": 3,
            "subscription": {"plan": "FREE", "status": "ACTIVE", "auto_renew": False, "paid_until": None},
            "entitlements": {"vpn_session_limit_seconds": 3600, "rewarded_ad_required": False, "country_selection_allowed": True, "free_nodes_only": True, "active_device_limit": 5, "daily_vpn_limit_seconds": 3600, "free_seconds_remaining": 3600, "free_quota_resets_at": (datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)).isoformat().replace("+00:00", "Z")},
        }
        await cleanup_user(postgres, email)


@pytest.mark.parametrize("principal", ["blocked_user", "revoked_device"])
async def test_session_endpoints_reject_blocked_user_or_revoked_device(principal: str):
    config = settings()
    postgres = Postgres(config)
    email = f"principal-{principal}-{uuid4()}@example.com"
    state = await create_auth_state(postgres, config, email)
    async with postgres.session() as session:
        if principal == "blocked_user":
            await session.execute(
                update(UserRecord)
                .where(UserRecord.id == state.user.id)
                .values(status=UserStatus.BLOCKED)
            )
        else:
            now = datetime.now(UTC)
            await session.execute(
                update(DeviceRecord)
                .where(DeviceRecord.id == state.devices[0].id)
                .values(status=DeviceStatus.REVOKED, revoked_at=now, updated_at=now)
            )
        await session.commit()
    app = create_app(config, postgres=postgres, valkey=FakeDependency(), product_events=AsyncMock())

    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            me = await client.get("/me", headers=auth_headers(state.access_token))
            refresh = await client.post(
                "/auth/refresh",
                json={
                    "session_id": str(state.issued.session.id),
                    "refresh_token": state.issued.refresh_token,
                },
            )
        expected = "user_blocked" if principal == "blocked_user" else "device_revoked"
        assert me.status_code == refresh.status_code == 403
        assert me.json() == refresh.json() == {"error": {"code": expected}}
        await cleanup_user(postgres, email)

