from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from prettylisavpn.auth.service import BlockedUserError
from prettylisavpn.auth.session_service import (
    AuthenticatedSessionService,
    AuthServiceUnavailableError,
    InvalidRefreshTokenError,
    InvalidSessionError,
    MeSummary,
    RefreshedTokens,
    RevokedDeviceError,
)
from prettylisavpn.auth.tokens import InvalidAccessTokenError, IssuedAccessToken
from prettylisavpn.auth_sessions.domain import AuthSession, IssuedAuthSession
from prettylisavpn.config import Settings
from prettylisavpn.main import create_app
from prettylisavpn.subscriptions.domain import SubscriptionPlan


def settings() -> Settings:
    return Settings(
        _env_file=None,
        otp_hmac_secret="authenticated-session-test-secret-at-least-32-characters",
    )


def dependency() -> AsyncMock:
    result = AsyncMock()
    result.ping.return_value = True
    return result


def api_client(service: AsyncMock) -> TestClient:
    return TestClient(
        create_app(
            settings(),
            postgres=dependency(),
            valkey=dependency(),
            otp_service=AsyncMock(),
            product_events=AsyncMock(),
            authenticated_sessions=service,
        )
    )


def refreshed_tokens() -> RefreshedTokens:
    now = datetime.now(UTC)
    auth_session = AuthSession(
        id=uuid4(),
        user_id=uuid4(),
        device_id=uuid4(),
        refresh_token_hash=b"h" * 32,
        expires_at=now + timedelta(days=30),
        revoked_at=None,
        created_at=now,
        updated_at=now,
    )
    return RefreshedTokens(
        auth_session=IssuedAuthSession(auth_session, "new-refresh-token"),
        access_token=IssuedAccessToken("new-access-token", now + timedelta(minutes=15), 900),
    )


def test_refresh_returns_rotated_token_pair():
    service = AsyncMock()
    result = refreshed_tokens()
    service.refresh.return_value = result

    with api_client(service) as client:
        response = client.post(
            "/auth/refresh",
            json={"session_id": str(result.auth_session.session.id), "refresh_token": "old-token"},
        )

    assert response.status_code == 200
    assert response.json()["access_token"] == "new-access-token"
    assert response.json()["refresh_token"] == "new-refresh-token"
    assert response.json()["session_id"] == str(result.auth_session.session.id)
    service.refresh.assert_awaited_once_with(result.auth_session.session.id, "old-token")


@pytest.mark.parametrize(
    ("error", "status_code", "code"),
    [
        (InvalidRefreshTokenError(), 401, "invalid_refresh_token"),
        (BlockedUserError(), 403, "user_blocked"),
        (RevokedDeviceError(), 403, "device_revoked"),
        (AuthServiceUnavailableError(), 503, "auth_service_unavailable"),
    ],
)
def test_refresh_maps_stable_errors(error, status_code, code):
    service = AsyncMock()
    service.refresh.side_effect = error
    with api_client(service) as client:
        response = client.post(
            "/auth/refresh",
            json={"session_id": str(uuid4()), "refresh_token": "secret-token"},
        )
    assert response.status_code == status_code
    assert response.json() == {"error": {"code": code}}
    assert "secret-token" not in response.text


def test_logout_revokes_bearer_session():
    service = AsyncMock()
    with api_client(service) as client:
        response = client.post("/auth/logout", headers={"Authorization": "Bearer access-token"})
    assert response.status_code == 200
    assert response.json() == {"status": "logged_out"}
    service.logout.assert_awaited_once_with("access-token")


def test_me_returns_identity_plan_and_active_device_count():
    service = AsyncMock()
    summary = MeSummary(uuid4(), "user@example.com", SubscriptionPlan.PREMIUM, 3)
    service.me.return_value = summary
    with api_client(service) as client:
        response = client.get("/me", headers={"Authorization": "Bearer access-token"})
    assert response.status_code == 200
    assert response.json() == {
        "id": str(summary.user_id),
        "email": summary.email,
        "plan": "PREMIUM",
        "active_device_count": 3,
        "subscription": None,
        "entitlements": {
            "vpn_session_limit_seconds": None,
            "rewarded_ad_required": False,
            "country_selection_allowed": True,
            "free_nodes_only": False,
            "active_device_limit": 5,
            "daily_vpn_limit_seconds": None,
            "free_seconds_remaining": None,
            "free_seconds_usable": None,
            "free_running_sessions": None,
            "quota_observed_at": None,
            "free_quota_resets_at": None,
        },
    }


@pytest.mark.parametrize("path,method", [("/me", "get"), ("/auth/logout", "post")])
def test_authenticated_endpoints_require_bearer_token(path, method):
    service = AsyncMock()
    with api_client(service) as client:
        response = getattr(client, method)(path)
    assert response.status_code == 401
    assert response.json() == {"error": {"code": "authentication_required"}}
    service.me.assert_not_awaited()
    service.logout.assert_not_awaited()


@pytest.mark.parametrize(
    ("error", "status_code", "code"),
    [
        (InvalidAccessTokenError(), 401, "invalid_access_token"),
        (InvalidSessionError(), 401, "invalid_session"),
        (BlockedUserError(), 403, "user_blocked"),
        (RevokedDeviceError(), 403, "device_revoked"),
        (AuthServiceUnavailableError(), 503, "auth_service_unavailable"),
    ],
)
def test_me_maps_stable_authentication_errors(error, status_code, code):
    service = AsyncMock()
    service.me.side_effect = error
    with api_client(service) as client:
        response = client.get("/me", headers={"Authorization": "Bearer private-token"})
    assert response.status_code == status_code
    assert response.json() == {"error": {"code": code}}
    assert "private-token" not in response.text


async def test_invalid_access_token_is_rejected_before_database_access():
    postgres = AsyncMock()
    service = AuthenticatedSessionService(postgres, AsyncMock(), settings())

    with pytest.raises(InvalidAccessTokenError):
        await service.me("not-a-jwt")

    postgres.session.assert_not_called()
