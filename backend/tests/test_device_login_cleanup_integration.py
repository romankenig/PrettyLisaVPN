"""Device login timestamps and account revocation against real PostgreSQL."""

import asyncio
import json
import os
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from legacy_data import clean_up, create_dependencies
from sqlalchemy.exc import SQLAlchemyError

from prettylisavpn.auth.service import InvalidOtpError, LoginService
from prettylisavpn.auth.session_service import AccessIdentity, AuthenticatedSessionService
from prettylisavpn.config import Settings
from prettylisavpn.connections import Postgres
from prettylisavpn.devices.domain import DevicePlatform
from prettylisavpn.devices.management import DeviceManagementService
from prettylisavpn.devices.repository import DeviceRepository
from prettylisavpn.devices.service import DeviceService
from prettylisavpn.main import create_app
from prettylisavpn.users.model import UserRecord

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.getenv("RUN_INTEGRATION_TESTS") != "1", reason="Needs PostgreSQL"),
]


@pytest.fixture
async def state():
    config = Settings(_env_file=None)
    postgres = Postgres(config)
    user_id, current_id, node_id = await create_dependencies(postgres)
    async with postgres.session() as session:
        target = await DeviceService(DeviceRepository(session)).register(
            user_id, uuid4(), DevicePlatform.ANDROID, "Target"
        )
        await session.commit()
    auth = AsyncMock()
    auth.authenticate.return_value = AccessIdentity(user_id, current_id, uuid4())
    agent = AsyncMock()
    agent.peer_exists.return_value = True
    events = AsyncMock()
    management = DeviceManagementService(postgres, auth, events, config)
    try:
        yield (
            postgres,
            config,
            user_id,
            current_id,
            node_id,
            target,
            auth,
            agent,
            events,
            management,
        )
    finally:
        await clean_up(postgres, user_id, node_id)
        await postgres.close()


async def test_record_device_api_evidence_with_simulated_otp(state):
    """Capture actual HTTP responses; only the CI runner may export the test email."""
    postgres, config, user_id, current_id, _, target, _, agent, _, _ = state
    evidence_path = os.getenv("DEVICE_BACKEND_EVIDENCE_PATH")
    if evidence_path:
        assert os.getenv("GITHUB_ACTIONS") == "true"
        assert "127.0.0.1" in config.postgres_url.get_secret_value()
    email = "kenromka@yandex.com" if evidence_path else f"evidence-{uuid4()}@example.com"
    async with postgres.session() as session:
        user = await session.get(UserRecord, user_id)
        user.email = email
        devices = DeviceService(DeviceRepository(session))
        current = await DeviceRepository(session).get(current_id)
        await devices.register(user_id, target.installation_id, target.platform, "Android phone")
        await session.commit()
    otp = AsyncMock()
    otp.verify.return_value = True
    cache = AsyncMock()
    app = create_app(
        config,
        postgres=postgres,
        valkey=cache,
        otp_service=otp,
        product_events=AsyncMock(),
    )
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            body = {
                "email": email,
                "code": "123456",
                "installation_id": str(current.installation_id),
                "platform": "WINDOWS",
                "device_name": "Windows device",
            }
            first = await client.post("/auth/verify-otp", json=body)
            second = await client.post("/auth/verify-otp", json=body)
            assert first.status_code == second.status_code == 200
            assert (
                second.json()["device"]["last_login_at"] > first.json()["device"]["last_login_at"]
            )
            headers = {"Authorization": "Bearer " + second.json()["access_token"]}
            before = await client.get("/devices", headers=headers)
            assert before.status_code == 200
            rows = before.json()
            assert next(row for row in rows if row["is_current"])["last_login_at"] is not None
            assert next(row for row in rows if not row["is_current"])["last_login_at"] is None
            revoked = await client.delete(f"/devices/{target.id}", headers=headers)
            repeat = await client.delete(f"/devices/{target.id}", headers=headers)
            assert revoked.status_code == repeat.status_code == 200
            assert revoked.json() == repeat.json()
            after = await client.get("/devices", headers=headers)
            version = await client.get("/version")
            assert after.status_code == version.status_code == 200
            if evidence_path:
                path = Path(evidence_path)
                await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
                await asyncio.to_thread(
                    path.write_text,
                    json.dumps(
                        {
                            "source_sha": os.getenv("PR_HEAD_SHA", os.getenv("GITHUB_SHA")),
                            "provenance": (
                                "Actual ASGI HTTP responses and PostgreSQL "
                                "in disposable CI database"
                            ),
                            "auth_simulated": True,
                            "vpn_implementation": "removed",
                            "live_account_accessed": False,
                            "account_email": email,
                            "user_id": str(user_id),
                            "devices": rows,
                            "revoked_response": revoked.json(),
                            "after_revoke": after.json(),
                            "version": version.json(),
                        },
                        indent=2,
                    ),
                    encoding="utf-8",
                )


async def test_successful_otp_is_the_only_login_timestamp_update(state):
    postgres, config, user_id, _, _, target, _, _, _, _ = state
    async with postgres.session() as session:
        from prettylisavpn.users.repository import UserRepository

        user = await UserRepository(session).get_by_id(user_id)
    otp = AsyncMock()
    otp.verify.return_value = True
    login = LoginService(otp, postgres, AsyncMock(), config)
    first = await login.verify_otp(
        user.email, "123456", target.installation_id, target.platform, target.device_name
    )
    assert first.device.last_login_at == first.auth_session.session.created_at
    second = await login.verify_otp(
        user.email, "123456", target.installation_id, target.platform, target.device_name
    )
    assert second.device.last_login_at > first.device.last_login_at
    assert second.device.created_at == target.created_at
    auth = AuthenticatedSessionService(postgres, AsyncMock(), config)
    await auth.refresh(second.auth_session.session.id, second.auth_session.refresh_token)
    otp.verify.return_value = False
    with pytest.raises(InvalidOtpError):
        await login.verify_otp(
            user.email, "000000", target.installation_id, target.platform, "Rename attempt"
        )
    async with postgres.session() as session:
        devices = DeviceService(DeviceRepository(session))
        renamed = await devices.register(
            user_id, target.installation_id, target.platform, "Renamed"
        )
        await session.commit()
    assert renamed.last_login_at == second.device.last_login_at


async def test_login_timestamp_rolls_back_if_transaction_cannot_commit(state, monkeypatch):
    postgres, config, user_id, _, _, target, _, _, _, _ = state
    from prettylisavpn.auth.service import LoginPersistenceError
    from prettylisavpn.users.repository import UserRepository

    async with postgres.session() as session:
        user = await UserRepository(session).get_by_id(user_id)
    original = DeviceRepository.update

    async def fail_after_update(self, device):
        await original(self, device)
        raise SQLAlchemyError("simulated persistence failure")

    monkeypatch.setattr(DeviceRepository, "update", fail_after_update)
    otp = AsyncMock()
    otp.verify.return_value = True
    with pytest.raises(LoginPersistenceError):
        await LoginService(otp, postgres, AsyncMock(), config).verify_otp(
            user.email, "123456", target.installation_id, target.platform, target.device_name
        )
    async with postgres.session() as session:
        device = await DeviceRepository(session).get(target.id)
    assert device.last_login_at is None
