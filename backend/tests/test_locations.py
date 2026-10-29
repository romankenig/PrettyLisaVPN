"""Authenticated metadata survives removal; no VPN issuance routes remain."""

from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from prettylisavpn.auth.service import BlockedUserError
from prettylisavpn.auth.session_service import (
    AuthServiceUnavailableError,
    InvalidSessionError,
    RevokedDeviceError,
)
from prettylisavpn.auth.tokens import InvalidAccessTokenError
from prettylisavpn.config import Settings
from prettylisavpn.main import create_app


@pytest.mark.parametrize(
    ("failure", "status", "code"),
    [
        (None, 200, None),
        (InvalidAccessTokenError(), 401, "invalid_access_token"),
        (InvalidSessionError(), 401, "invalid_session"),
        (RevokedDeviceError(), 403, "device_revoked"),
        (BlockedUserError(), 403, "user_blocked"),
        (AuthServiceUnavailableError(), 503, "auth_service_unavailable"),
    ],
)
async def test_locations_are_authenticated_metadata_with_no_live_availability(
    failure, status, code
):
    auth = AsyncMock()
    auth.authenticate.side_effect = failure
    app = create_app(
        Settings(_env_file=None),
        postgres=AsyncMock(),
        valkey=AsyncMock(),
        authenticated_sessions=auth,
    )
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            missing = await client.get("/vpn/countries")
            assert missing.status_code == 401
            auth.authenticate.assert_not_called()
            response = await client.get("/vpn/countries", headers={"Authorization": "Bearer test"})
    assert response.status_code == status
    auth.authenticate.assert_awaited_once_with("test")
    if failure is not None:
        assert response.json()["error"]["code"] == code
    else:
        assert response.json() == {
            "autopilot": {"quality": 0, "available": False},
            "countries": [
                {"country_code": "DE", "quality": 0, "available": False},
                {"country_code": "US", "quality": 0, "available": False},
            ],
        }


async def test_common_sessions_and_wireguard_compatibility_exclude_legacy_engine_paths():
    app = create_app(Settings(_env_file=None), postgres=AsyncMock(), valkey=AsyncMock())
    assert set(path for path in app.openapi()["paths"] if path.startswith("/vpn/")) == {
        "/vpn/countries",
        "/vpn/sessions",
        "/vpn/sessions/current",
        "/vpn/sessions/{identifier}",
        "/vpn/sessions/{identifier}/heartbeat",
        "/vpn/sessions/{identifier}/probe",
        "/vpn/wireguard/sessions",
        "/vpn/wireguard/sessions/current",
        "/vpn/wireguard/sessions/{identifier}",
        "/vpn/wireguard/sessions/{identifier}/heartbeat",
        "/vpn/wireguard/sessions/{identifier}/probe",
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for method, path in [
            ("POST", "/vpn/sessions/00000000-0000-0000-0000-000000000001/managed"),
            ("POST", "/vpn/sessions/00000000-0000-0000-0000-000000000001/managed-plan"),
        ]:
            assert (await client.request(method, path)).status_code == 404
