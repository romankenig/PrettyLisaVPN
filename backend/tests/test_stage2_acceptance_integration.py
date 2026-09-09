"""Stage 2 authentication lifecycle against real PostgreSQL and Valkey."""

import os
import re
from collections.abc import Mapping
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select

from prettylisavpn.auth_sessions.model import AuthSessionRecord
from prettylisavpn.config import Settings
from prettylisavpn.connections import Postgres, Valkey
from prettylisavpn.devices.model import DeviceRecord
from prettylisavpn.emailing.domain import OutboundEmail
from prettylisavpn.main import create_app
from prettylisavpn.product_events.domain import ProductEventName
from prettylisavpn.subscriptions.model import SubscriptionRecord
from prettylisavpn.users.domain import normalize_email
from prettylisavpn.users.model import UserRecord

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1",
        reason="Set RUN_INTEGRATION_TESTS=1 with PostgreSQL and Valkey running",
    ),
]

OTP_KEY_PATTERN = re.compile(r"otp:(?:challenge|cooldown|rate:email|rate:ip):[0-9a-f]{64}")


class CapturingEmailProvider:
    def __init__(self) -> None:
        self.sent: list[OutboundEmail] = []

    async def send(self, email: OutboundEmail) -> None:
        self.sent.append(email)

    def latest_code(self) -> str:
        return self.sent[-1].text_body.split("\n")[2]


class CapturingEvents:
    def __init__(self) -> None:
        self.names: list[ProductEventName] = []

    async def record(
        self,
        event_name: ProductEventName,
        *,
        user_id: UUID | None = None,
        device_id: UUID | None = None,
        properties: Mapping[str, object] | None = None,
    ) -> None:
        self.names.append(event_name)


async def otp_keys(valkey: Valkey) -> set[str]:
    return {key async for key in valkey.client.scan_iter(match="otp:*")}


async def test_complete_stage2_backend_lifecycle_and_storage_boundaries():
    config = Settings(
        _env_file=None,
        otp_hmac_secret=f"stage2-acceptance-secret-{uuid4().hex}",
        otp_request_cooldown_seconds=0,
        otp_email_request_limit=50,
        otp_ip_request_limit=50,
    )
    postgres, valkey = Postgres(config), Valkey(config)
    provider, events = CapturingEmailProvider(), CapturingEvents()
    email = f"stage2-{uuid4()}@example.com"
    normalized_email = normalize_email(email)
    installation_id = uuid4()
    keys_before = await otp_keys(valkey)
    created_keys: set[str] = set()
    app = create_app(
        config,
        postgres=postgres,
        valkey=valkey,
        email_provider=provider,
        product_events=events,
    )

    try:
        async with app.router.lifespan_context(app):
            transport = ASGITransport(app=app, client=("192.0.2.200", 12345))
            async with AsyncClient(transport=transport, base_url="https://test") as client:
                requested = await client.post("/auth/request-otp", json={"email": email.upper()})
                assert requested.status_code == 202
                assert requested.json() == {"status": "accepted"}
                assert len(provider.sent) == 1
                code = provider.latest_code()

                keys_after_request = await otp_keys(valkey)
                created_keys = keys_after_request - keys_before
                assert len(created_keys) == 3
                assert all(OTP_KEY_PATTERN.fullmatch(key) for key in created_keys)
                assert all(normalized_email not in key for key in created_keys)
                assert all(await valkey.client.ttl(key) > 0 for key in created_keys)
                challenge_key = next(
                    key for key in created_keys if key.startswith("otp:challenge:")
                )
                challenge = await valkey.client.hgetall(challenge_key)
                assert set(challenge) == {"verifier", "attempts"}
                assert challenge["attempts"] == "0"
                assert challenge["verifier"] != code

                verified = await client.post(
                    "/auth/verify-otp",
                    json={
                        "email": email,
                        "code": code,
                        "installation_id": str(installation_id),
                        "platform": "WINDOWS",
                        "device_name": "Stage 2 Windows",
                    },
                )
                assert verified.status_code == 200
                login = verified.json()
                assert login["subscription"] == {"plan": "FREE", "status": "ACTIVE"}
                assert login["device"]["installation_id"] == str(installation_id)

                replayed_otp = await client.post(
                    "/auth/verify-otp",
                    json={
                        "email": email,
                        "code": code,
                        "installation_id": str(uuid4()),
                        "platform": "WINDOWS",
                        "device_name": "Replay attempt",
                    },
                )
                assert replayed_otp.status_code == 401
                assert replayed_otp.json() == {"error": {"code": "otp_invalid_or_expired"}}

                headers = {"Authorization": f"Bearer {login['access_token']}"}
                me = await client.get("/me", headers=headers)
                assert me.status_code == 200
                assert me.json()["email"] == normalized_email
                assert me.json()["plan"] == "FREE"
                assert me.json()["active_device_count"] == 1

                devices = await client.get("/devices", headers=headers)
                assert devices.status_code == 200
                assert len(devices.json()) == 1
                assert devices.json()[0]["is_current"] is True

                refreshed = await client.post(
                    "/auth/refresh",
                    json={
                        "session_id": login["session_id"],
                        "refresh_token": login["refresh_token"],
                    },
                )
                assert refreshed.status_code == 200
                rotated = refreshed.json()
                assert rotated["refresh_token"] != login["refresh_token"]

                replayed_refresh = await client.post(
                    "/auth/refresh",
                    json={
                        "session_id": login["session_id"],
                        "refresh_token": login["refresh_token"],
                    },
                )
                assert replayed_refresh.status_code == 401
                assert replayed_refresh.json() == {"error": {"code": "invalid_refresh_token"}}

                rotated_headers = {"Authorization": f"Bearer {rotated['access_token']}"}
                logged_out = await client.post("/auth/logout", headers=rotated_headers)
                assert logged_out.status_code == 200
                assert logged_out.json() == {"status": "logged_out"}
                assert (await client.get("/me", headers=rotated_headers)).status_code == 401
                assert (
                    await client.post(
                        "/auth/refresh",
                        json={
                            "session_id": rotated["session_id"],
                            "refresh_token": rotated["refresh_token"],
                        },
                    )
                ).status_code == 401

                async with postgres.session() as session:
                    user = await session.scalar(
                        select(UserRecord).where(UserRecord.email == normalized_email)
                    )
                    assert user is not None
                    assert (
                        await session.scalar(
                            select(func.count(SubscriptionRecord.id)).where(
                                SubscriptionRecord.user_id == user.id
                            )
                        )
                        == 1
                    )
                    assert (
                        await session.scalar(
                            select(func.count(DeviceRecord.id)).where(
                                DeviceRecord.user_id == user.id
                            )
                        )
                        == 1
                    )
                    auth_session = await session.scalar(
                        select(AuthSessionRecord).where(AuthSessionRecord.user_id == user.id)
                    )
                    assert auth_session is not None
                    assert auth_session.revoked_at is not None
                    assert login["refresh_token"].encode() not in auth_session.refresh_token_hash
                    assert rotated["refresh_token"].encode() not in auth_session.refresh_token_hash

                keys_after_login = (await otp_keys(valkey)) - keys_before
                assert all(OTP_KEY_PATTERN.fullmatch(key) for key in keys_after_login)
                assert not any(key.startswith("otp:challenge:") for key in keys_after_login)
                assert all(await valkey.client.ttl(key) > 0 for key in keys_after_login)

        assert ProductEventName.OTP_REQUESTED in events.names
        assert ProductEventName.OTP_SENT in events.names
        assert ProductEventName.OTP_VERIFIED in events.names
        assert ProductEventName.LOGIN_SUCCEEDED in events.names
        assert ProductEventName.TOKEN_REFRESHED in events.names
        assert ProductEventName.LOGOUT in events.names
    finally:
        cleanup_postgres, cleanup_valkey = Postgres(config), Valkey(config)
        try:
            if created_keys:
                await cleanup_valkey.client.delete(*created_keys)
            async with cleanup_postgres.session() as session:
                await session.execute(
                    delete(UserRecord).where(UserRecord.email == normalized_email)
                )
                await session.commit()
        finally:
            await cleanup_valkey.close()
            await cleanup_postgres.close()
