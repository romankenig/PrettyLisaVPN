"""Authenticated VPN session targeting endpoint tests."""

from datetime import UTC, datetime, timedelta
from ipaddress import IPv4Address, IPv4Network
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from prettylisavpn.config import Settings
from prettylisavpn.main import create_app
from prettylisavpn.vpn_nodes.selection import NodeSelectionRequest
from prettylisavpn.vpn_sessions.connection import (
    ActiveVpnTransport,
    CountryUnavailableError,
    VpnSetupFailedError,
    VpnUnavailableError,
)
from prettylisavpn.vpn_sessions.domain import VpnSessionStatus
from prettylisavpn.vpn_sessions.termination import (
    OwnedVpnSessionNotFoundError,
    TerminatedVpnSession,
)

PUBLIC_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="


def dependency() -> AsyncMock:
    result = AsyncMock()
    result.ping.return_value = True
    return result


def api_client(service: AsyncMock) -> TestClient:
    return TestClient(
        create_app(
            Settings(_env_file=None),
            postgres=dependency(),
            valkey=dependency(),
            otp_service=AsyncMock(),
            product_events=AsyncMock(),
            authenticated_sessions=AsyncMock(),
            vpn_connection=service,
        )
    )


@pytest.mark.parametrize(
    ("body", "expected_request"),
    [
        (
            {"mode": "AUTO", "public_key": PUBLIC_KEY},
            NodeSelectionRequest.auto(),
        ),
        (
            {"mode": "COUNTRY", "country_code": "de", "public_key": PUBLIC_KEY},
            NodeSelectionRequest.country("DE"),
        ),
    ],
)
def test_create_session_supports_auto_and_country_without_client_node_target(
    body: dict[str, str], expected_request: NodeSelectionRequest
):
    service = AsyncMock()
    expires_at = datetime.now(UTC) + timedelta(minutes=15)
    session_id = uuid4()
    service.connect.return_value = ActiveVpnTransport(
        session_id=session_id,
        country_code="DE",
        endpoint_ipv4=IPv4Address("204.48.17.50"),
        endpoint_port=51820,
        server_public_key=PUBLIC_KEY,
        client_ipv4=IPv4Address("10.77.0.2"),
        dns=(IPv4Address("1.1.1.1"), IPv4Address("1.0.0.1")),
        allowed_ips=(IPv4Network("0.0.0.0/0"),),
        expires_at=expires_at,
    )

    with api_client(service) as client:
        response = client.post(
            "/vpn/sessions",
            headers={"Authorization": "Bearer access-token"},
            json=body,
        )

    assert response.status_code == 200
    assert response.json() == {
        "session_id": str(session_id),
        "status": "ACTIVE",
        "country_code": "DE",
        "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
        "transport": {
            "endpoint": {"ipv4": "204.48.17.50", "port": 51820},
            "server_public_key": PUBLIC_KEY,
            "client_address": "10.77.0.2/32",
            "dns": ["1.1.1.1", "1.0.0.1"],
            "allowed_ips": ["0.0.0.0/0"],
        },
    }
    service.connect.assert_awaited_once_with("access-token", expected_request, PUBLIC_KEY)


@pytest.mark.parametrize("forbidden", ["node_id", "provider", "node_ip"])
def test_request_rejects_internal_target_fields(forbidden: str):
    service = AsyncMock()
    with api_client(service) as client:
        response = client.post(
            "/vpn/sessions",
            headers={"Authorization": "Bearer token"},
            json={"mode": "AUTO", "public_key": PUBLIC_KEY, forbidden: "internal"},
        )
    assert response.status_code == 422
    service.connect.assert_not_awaited()


@pytest.mark.parametrize(
    ("body", "error", "code"),
    [
        (
            {"mode": "COUNTRY", "country_code": "DE", "public_key": PUBLIC_KEY},
            CountryUnavailableError(),
            "COUNTRY_UNAVAILABLE",
        ),
        (
            {"mode": "AUTO", "public_key": PUBLIC_KEY},
            VpnUnavailableError(),
            "VPN_UNAVAILABLE",
        ),
        (
            {"mode": "AUTO", "public_key": PUBLIC_KEY},
            VpnSetupFailedError(),
            "VPN_SETUP_FAILED",
        ),
    ],
)
def test_target_and_setup_failures_use_stable_codes(
    body: dict[str, str], error: Exception, code: str
):
    service = AsyncMock()
    service.connect.side_effect = error
    with api_client(service) as client:
        response = client.post(
            "/vpn/sessions", headers={"Authorization": "Bearer token"}, json=body
        )
    assert response.status_code == (503 if code == "VPN_SETUP_FAILED" else 409)
    assert response.json() == {"error": {"code": code}}


def test_endpoint_requires_authentication_and_valid_target_shape():
    service = AsyncMock()
    with api_client(service) as client:
        unauthenticated = client.post(
            "/vpn/sessions", json={"mode": "AUTO", "public_key": PUBLIC_KEY}
        )
        invalid_country = client.post(
            "/vpn/sessions",
            headers={"Authorization": "Bearer token"},
            json={"mode": "COUNTRY", "public_key": PUBLIC_KEY},
        )
    assert unauthenticated.status_code == 401
    assert invalid_country.status_code == 422


def test_disconnect_endpoint_returns_terminal_state_and_is_transport_free():
    service = AsyncMock()
    session_id = uuid4()
    service.disconnect.return_value = TerminatedVpnSession(
        session_id, VpnSessionStatus.DISCONNECTED
    )
    with api_client(AsyncMock()) as client:
        client.app.state.vpn_termination = service
        response = client.delete(
            f"/vpn/sessions/{session_id}",
            headers={"Authorization": "Bearer token"},
        )

    assert response.status_code == 200
    assert response.json() == {"session_id": str(session_id), "status": "DISCONNECTED"}
    service.disconnect.assert_awaited_once_with("token", session_id)


def test_disconnect_enforces_owned_session_lookup():
    service = AsyncMock()
    service.disconnect.side_effect = OwnedVpnSessionNotFoundError
    with api_client(AsyncMock()) as client:
        client.app.state.vpn_termination = service
        response = client.delete(
            f"/vpn/sessions/{uuid4()}", headers={"Authorization": "Bearer token"}
        )

    assert response.status_code == 404
    assert response.json() == {"error": {"code": "VPN_SESSION_NOT_FOUND"}}
