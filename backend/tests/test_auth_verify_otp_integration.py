"""Complete passwordless-login tests against PostgreSQL and Valkey."""

import asyncio
import os
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select, update

from prettylisavpn.auth.tokens import AccessTokenService
from prettylisavpn.auth_sessions.model import AuthSessionRecord
from prettylisavpn.config import Settings
from prettylisavpn.connections import Postgres, Valkey
from prettylisavpn.devices.domain import DevicePlatform, DeviceStatus
from prettylisavpn.devices.model import DeviceRecord
from prettylisavpn.devices.repository import DeviceRepository
from prettylisavpn.devices.service import MAX_ACTIVE_DEVICES, DeviceService
from prettylisavpn.main import create_app
from prettylisavpn.subscriptions.domain import SubscriptionPlan
from prettylisavpn.subscriptions.model import SubscriptionRecord
from prettylisavpn.subscriptions.repository import SubscriptionRepository
from prettylisavpn.users.domain import UserStatus, normalize_email
from prettylisavpn.users.model import UserRecord
from prettylisavpn.users.repository import UserRepository
from prettylisavpn.users.service import UserService

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1",
        reason="Set RUN_INTEGRATION_TESTS=1 with PostgreSQL and Valkey running",
    ),
]


class CapturingEmailProvider:
    def __init__(self) -> None:
        self.sent = []

    async def send(self, email) -> None:
        self.sent.append(email)

    def latest_code(self) -> str:
        return self.sent[-1].text_body.split("\n")[2]


class AlwaysValidOtp:
    async def verify(self, email: str, code: str) -> bool:
        return True


class FakeValkey:
    async def ping(self) -> None:
        return None

    async def close(self) -> None:
        return None


def settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "otp_hmac_secret": f"verify-integration-secret-{uuid4().hex}",
        "otp_request_cooldown_seconds": 0,
        "otp_email_request_limit": 50,
        "otp_ip_request_limit": 50,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def verify_body(email: str, code: str, installation_id: UUID) -> dict[str, str]:
    return {
        "email": email,
        "code": code,
        "installation_id": str(installation_id),
        "platform": "WINDOWS",
        "device_name": "Laptop",
    }


async def request_code(client: AsyncClient, provider: CapturingEmailProvider, email: str) -> str:
    response = await client.post("/auth/request-otp", json={"email": email})
    assert response.status_code == 202
    return provider.latest_code()


async def cleanup_user(postgres: Postgres, email: str) -> None:
    async with postgres.session() as session:
        await session.execute(delete(UserRecord).where(UserRecord.email == normalize_email(email)))
        await session.commit()


async def test_new_user_login_creates_free_subscription_device_and_hashed_session():
    config = settings()
    postgres, valkey = Postgres(config), Valkey(config)
    provider = CapturingEmailProvider()
    email = f"new-login-{uuid4()}@example.com"
    installation_id = uuid4()
    app = create_app(config, postgres=postgres, valkey=valkey, email_provider=provider)

    async with app.router.lifespan_context(app):
        client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        async with client:
            code = await request_code(client, provider, email)
            response = await client.post(
                "/auth/verify-otp", json=verify_body(email, code, installation_id)
            )
        assert response.status_code == 200
        payload = response.json()
        assert payload["subscription"] == {"plan": "FREE", "status": "ACTIVE"}
        claims = AccessTokenService(config).decode(payload["access_token"])
        assert claims["sub"] == payload["user"]["id"]
        assert claims["device_id"] == payload["device"]["id"]
        assert claims["session_id"] == payload["session_id"]

        async with postgres.session() as session:
            subscription = await session.scalar(
                select(SubscriptionRecord).where(
                    SubscriptionRecord.user_id == UUID(payload["user"]["id"])
                )
            )
            auth_session = await session.get(AuthSessionRecord, UUID(payload["session_id"]))
            assert subscription is not None and subscription.plan is SubscriptionPlan.FREE
            assert auth_session is not None
            assert payload["refresh_token"].encode() not in auth_session.refresh_token_hash
        await cleanup_user(postgres, email)


async def test_existing_user_and_installation_are_reused_without_duplicates():
    config = settings()
    postgres, valkey = Postgres(config), Valkey(config)
    provider = CapturingEmailProvider()
    email = f"existing-login-{uuid4()}@example.com"
    installation_id = uuid4()
    app = create_app(config, postgres=postgres, valkey=valkey, email_provider=provider)

    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            first_code = await request_code(client, provider, email)
            first = await client.post(
                "/auth/verify-otp", json=verify_body(email, first_code, installation_id)
            )
            second_code = await request_code(client, provider, email)
            second = await client.post(
                "/auth/verify-otp", json=verify_body(email, second_code, installation_id)
            )

        assert first.status_code == second.status_code == 200
        assert first.json()["user"]["id"] == second.json()["user"]["id"]
        assert first.json()["device"]["id"] == second.json()["device"]["id"]
        async with postgres.session() as session:
            assert (
                await session.scalar(
                    select(func.count(UserRecord.id)).where(UserRecord.email == email)
                )
                == 1
            )
            assert (
                await session.scalar(
                    select(func.count(DeviceRecord.id)).where(
                        DeviceRecord.user_id == UUID(first.json()["user"]["id"])
                    )
                )
                == 1
            )
        await cleanup_user(postgres, email)


async def test_invalid_expired_and_replayed_otps_are_rejected():
    config = settings(otp_ttl_seconds=1)
    postgres, valkey = Postgres(config), Valkey(config)
    provider = CapturingEmailProvider()
    app = create_app(config, postgres=postgres, valkey=valkey, email_provider=provider)

    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            invalid_email = f"invalid-{uuid4()}@example.com"
            valid_code = await request_code(client, provider, invalid_email)
            wrong_code = "000000" if valid_code != "000000" else "999999"
            invalid = await client.post(
                "/auth/verify-otp", json=verify_body(invalid_email, wrong_code, uuid4())
            )

            expired_email = f"expired-{uuid4()}@example.com"
            expired_code = await request_code(client, provider, expired_email)
            await asyncio.sleep(1.1)
            expired = await client.post(
                "/auth/verify-otp", json=verify_body(expired_email, expired_code, uuid4())
            )

            replay_email = f"replay-{uuid4()}@example.com"
            replay_code = await request_code(client, provider, replay_email)
            body = verify_body(replay_email, replay_code, uuid4())
            accepted = await client.post("/auth/verify-otp", json=body)
            replayed = await client.post("/auth/verify-otp", json=body)

        assert invalid.status_code == 401
        assert expired.status_code == 401
        assert accepted.status_code == 200
        assert replayed.status_code == 401
        expected = {"error": {"code": "otp_invalid_or_expired"}}
        assert invalid.json() == expired.json() == replayed.json() == expected
        await cleanup_user(postgres, replay_email)


async def test_blocked_user_cannot_log_in():
    config = settings()
    postgres, valkey = Postgres(config), Valkey(config)
    provider = CapturingEmailProvider()
    email = f"blocked-{uuid4()}@example.com"
    app = create_app(config, postgres=postgres, valkey=valkey, email_provider=provider)

    async with app.router.lifespan_context(app):
        async with postgres.session() as session:
            user = await UserService(
                UserRepository(session), SubscriptionRepository(session)
            ).create(email)
            await session.execute(
                update(UserRecord).where(UserRecord.id == user.id).values(status=UserStatus.BLOCKED)
            )
            await session.commit()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            code = await request_code(client, provider, email)
            response = await client.post("/auth/verify-otp", json=verify_body(email, code, uuid4()))

        assert response.status_code == 403
        assert response.json() == {"error": {"code": "user_blocked"}}
        async with postgres.session() as session:
            assert (
                await session.scalar(
                    select(func.count(DeviceRecord.id)).where(DeviceRecord.user_id == user.id)
                )
                == 0
            )
            assert (
                await session.scalar(
                    select(func.count(AuthSessionRecord.id)).where(
                        AuthSessionRecord.user_id == user.id
                    )
                )
                == 0
            )
        await cleanup_user(postgres, email)


async def test_sixth_active_device_is_rejected_without_creating_session():
    config = settings()
    postgres, valkey = Postgres(config), Valkey(config)
    provider = CapturingEmailProvider()
    email = f"device-limit-login-{uuid4()}@example.com"
    app = create_app(config, postgres=postgres, valkey=valkey, email_provider=provider)

    async with app.router.lifespan_context(app):
        async with postgres.session() as session:
            user = await UserService(
                UserRepository(session), SubscriptionRepository(session)
            ).create(email)
            service = DeviceService(DeviceRepository(session))
            for number in range(MAX_ACTIVE_DEVICES):
                await service.register(user.id, uuid4(), DevicePlatform.ANDROID, f"Phone {number}")
            await session.commit()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            code = await request_code(client, provider, email)
            response = await client.post("/auth/verify-otp", json=verify_body(email, code, uuid4()))

        assert response.status_code == 409
        assert response.json() == {"error": {"code": "device_limit_reached"}}
        async with postgres.session() as session:
            assert (
                await session.scalar(
                    select(func.count(DeviceRecord.id)).where(
                        DeviceRecord.user_id == user.id,
                        DeviceRecord.status == DeviceStatus.ACTIVE,
                    )
                )
                == MAX_ACTIVE_DEVICES
            )
            assert (
                await session.scalar(
                    select(func.count(AuthSessionRecord.id)).where(
                        AuthSessionRecord.user_id == user.id
                    )
                )
                == 0
            )
        await cleanup_user(postgres, email)


async def test_concurrent_logins_do_not_duplicate_user_or_device():
    config = settings()
    postgres = Postgres(config)
    email = f"concurrent-login-{uuid4()}@example.com"
    installation_id = uuid4()
    app = create_app(
        config,
        postgres=postgres,
        valkey=FakeValkey(),
        otp_service=AlwaysValidOtp(),
    )
    body = verify_body(email, "123456", installation_id)

    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            first, second = await asyncio.gather(
                client.post("/auth/verify-otp", json=body),
                client.post("/auth/verify-otp", json=body),
            )

        assert first.status_code == second.status_code == 200
        assert first.json()["user"]["id"] == second.json()["user"]["id"]
        assert first.json()["device"]["id"] == second.json()["device"]["id"]
        async with postgres.session() as session:
            user_id = UUID(first.json()["user"]["id"])
            assert (
                await session.scalar(
                    select(func.count(UserRecord.id)).where(UserRecord.email == email)
                )
                == 1
            )
            assert (
                await session.scalar(
                    select(func.count(DeviceRecord.id)).where(DeviceRecord.user_id == user_id)
                )
                == 1
            )
            assert (
                await session.scalar(
                    select(func.count(AuthSessionRecord.id)).where(
                        AuthSessionRecord.user_id == user_id
                    )
                )
                == 2
            )
        await cleanup_user(postgres, email)
