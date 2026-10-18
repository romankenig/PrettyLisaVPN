from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from prettylisavpn.auth.service import (
    BlockedUserError,
    InvalidOtpError,
    LoginPersistenceError,
    LoginResult,
    LoginService,
    OtpStorageUnavailableError,
)
from prettylisavpn.auth.tokens import (
    AccessTokenService,
    InvalidAccessTokenError,
    IssuedAccessToken,
)
from prettylisavpn.auth_sessions.domain import AuthSession, IssuedAuthSession
from prettylisavpn.config import Settings
from prettylisavpn.devices.domain import (
    Device,
    DeviceLimitReachedError,
    DevicePlatform,
    DeviceStatus,
)
from prettylisavpn.main import create_app
from prettylisavpn.otp import OtpServiceUnavailableError
from prettylisavpn.product_events.domain import ProductEventName
from prettylisavpn.subscriptions.domain import Subscription
from prettylisavpn.users.domain import User, UserStatus


def settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "otp_hmac_secret": "verify-endpoint-test-secret-at-least-32-characters",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def login_result() -> LoginResult:
    now = datetime.now(UTC)
    user = User(uuid4(), "user@example.com", UserStatus.ACTIVE, now, now)
    subscription = Subscription.new_free(user.id, now)
    device = Device(
        uuid4(),
        user.id,
        uuid4(),
        DevicePlatform.WINDOWS,
        "Laptop",
        DeviceStatus.ACTIVE,
        now,
        now,
        None,
    )
    auth_session = AuthSession(
        uuid4(),
        user.id,
        device.id,
        b"h" * 32,
        now + timedelta(days=30),
        None,
        now,
        now,
    )
    return LoginResult(
        user=user,
        subscription=subscription,
        device=device,
        auth_session=IssuedAuthSession(auth_session, "refresh-token"),
        access_token=IssuedAccessToken("access-token", now + timedelta(minutes=15), 900),
    )


def api_client(login_service: AsyncMock) -> TestClient:
    dependency = AsyncMock()
    return TestClient(
        create_app(
            settings(),
            postgres=dependency,
            valkey=dependency,
            otp_service=AsyncMock(),
            product_events=AsyncMock(),
            login_service=login_service,
        )
    )


def valid_body() -> dict[str, str]:
    return {
        "email": "User@Example.COM",
        "code": "123456",
        "installation_id": str(uuid4()),
        "platform": "WINDOWS",
        "device_name": " Laptop ",
    }


def test_access_token_contains_scoped_identity_claims_and_rejects_tampering():
    service = AccessTokenService(settings(access_token_ttl_seconds=600))
    user_id, device_id, session_id = uuid4(), uuid4(), uuid4()

    issued = service.issue(user_id, device_id, session_id)
    claims = service.decode(issued.token)

    assert claims["sub"] == str(user_id)
    assert claims["device_id"] == str(device_id)
    assert claims["session_id"] == str(session_id)
    assert claims["type"] == "access"
    assert issued.expires_in_seconds == 600
    assert issued.token not in repr(issued)
    header, payload, signature = issued.token.split(".")
    replacement = "A" if signature[0] != "A" else "B"
    with pytest.raises(InvalidAccessTokenError):
        service.decode(f"{header}.{payload}.{replacement}{signature[1:]}")


@pytest.mark.parametrize(
    ("error", "status_code", "error_code"),
    [
        (InvalidOtpError(), 401, "otp_invalid_or_expired"),
        (BlockedUserError(), 403, "user_blocked"),
        (DeviceLimitReachedError(), 409, "device_limit_reached"),
        (OtpStorageUnavailableError(), 503, "otp_service_unavailable"),
        (LoginPersistenceError(), 503, "login_service_unavailable"),
    ],
)
def test_verify_endpoint_maps_stable_errors(error, status_code, error_code):
    login = AsyncMock()
    login.verify_otp.side_effect = error
    with api_client(login) as client:
        response = client.post("/auth/verify-otp", json=valid_body())

    assert response.status_code == status_code
    assert response.json() == {"error": {"code": error_code}}


def test_verify_endpoint_returns_tokens_and_login_context():
    login = AsyncMock()
    result = login_result()
    login.verify_otp.return_value = result
    body = valid_body()

    with api_client(login) as client:
        response = client.post("/auth/verify-otp", json=body)

    assert response.status_code == 200
    assert response.json() == {
        "token_type": "bearer",
        "access_token": "access-token",
        "access_token_expires_in": 900,
        "refresh_token": "refresh-token",
        "refresh_token_expires_at": result.auth_session.session.expires_at.isoformat().replace(
            "+00:00", "Z"
        ),
        "session_id": str(result.auth_session.session.id),
        "user": {"id": str(result.user.id)},
        "device": {
            "id": str(result.device.id),
            "installation_id": str(result.device.installation_id),
            "status": "ACTIVE",
            "last_login_at": None,
        },
        "subscription": {"plan": "FREE", "status": "ACTIVE"},
    }
    login.verify_otp.assert_awaited_once_with(
        "User@example.com",
        "123456",
        UUID(body["installation_id"]),
        DevicePlatform.WINDOWS,
        "Laptop",
    )


@pytest.mark.parametrize("code", ["12345", "1234567", "abcdef", "12 456"])
def test_verify_endpoint_rejects_non_six_digit_codes(code):
    login = AsyncMock()
    body = valid_body()
    body["code"] = code
    with api_client(login) as client:
        response = client.post("/auth/verify-otp", json=body)

    assert response.status_code == 422
    assert response.json() == {"error": {"code": "validation_error"}}
    login.verify_otp.assert_not_awaited()


async def test_login_service_rejects_invalid_or_unavailable_otp_before_database_access():
    postgres = AsyncMock()
    events = AsyncMock()
    otp = AsyncMock()
    service = LoginService(otp, postgres, events, settings())

    otp.verify.return_value = False
    with pytest.raises(InvalidOtpError):
        await service.verify_otp(
            "User@Example.COM", "123456", uuid4(), DevicePlatform.LINUX, "Laptop"
        )
    postgres.session.assert_not_called()
    events.record.assert_awaited_once_with(
        ProductEventName.LOGIN_FAILED, properties={"reason": "invalid_otp"}
    )

    otp.verify.side_effect = OtpServiceUnavailableError("private-valkey-detail")
    with pytest.raises(OtpStorageUnavailableError) as captured:
        await service.verify_otp(
            "user@example.com", "123456", uuid4(), DevicePlatform.LINUX, "Laptop"
        )
    assert "private-valkey-detail" not in str(captured.value)
    postgres.session.assert_not_called()
