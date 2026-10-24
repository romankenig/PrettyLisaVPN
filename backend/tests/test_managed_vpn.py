"""Closed managed-profile API and bounded, purpose-separated credentials."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError
from test_vpn_session_api import api_client

from prettylisavpn.config import Settings
from prettylisavpn.vpn_sessions.managed import (
    ManagedProfileResponse,
    ManagedVpnNotFound,
    ManagedVpnResponse,
    ManagedVpnUnavailable,
    credential,
    lease_deadline,
)


def test_credential_is_stable_and_scoped_to_session_node_and_secret():
    session, node = uuid4(), uuid4()
    first = credential("a" * 32, session, node)
    assert first == credential("a" * 32, session, node)
    assert (
        len(
            {
                first,
                credential("b" * 32, session, node),
                credential("a" * 32, uuid4(), node),
                credential("a" * 32, session, uuid4()),
            }
        )
        == 4
    )


def test_lease_never_extends_existing_deadline_and_preview_is_opt_in():
    now = datetime.now(UTC)
    assert lease_deadline(now, None) == now + timedelta(minutes=15)
    assert lease_deadline(now, now + timedelta(seconds=10)) == now + timedelta(seconds=10)
    assert not Settings(_env_file=None).vpn_managed_nodes
    assert Settings(_env_file=None, vpn_managed_secret="").vpn_managed_secret is None
    for environment, secret in (("production", "x" * 32), ("development", None)):
        with pytest.raises(ValidationError):
            Settings(
                _env_file=None,
                environment=environment,
                vpn_managed_nodes=[uuid4()],
                vpn_managed_secret=secret,
            )


@pytest.mark.parametrize(
    "outcome,status,code",
    [
        (None, 200, None),
        (ManagedVpnNotFound(), 404, "VPN_SESSION_NOT_FOUND"),
        (ManagedVpnUnavailable(), 503, "VPN_MANAGED_UNAVAILABLE"),
    ],
)
def test_managed_endpoint_auth_scoping_and_no_store(outcome, status, code):
    identifier, password = uuid4(), str(uuid4())
    now = datetime.now(UTC)
    service = AsyncMock()
    service.issue.return_value = ManagedVpnResponse(
        profile=ManagedProfileResponse(
            session=identifier,
            country="DE",
            server="203.0.113.30",
            port=18443,
            secret=password,
            server_name="api.prettylisavpn.com",
            public_key="a" * 43,
            short_id="ab",
        ),
        expires_at=now + timedelta(minutes=15),
        server_time=now,
    )
    assert password not in repr(service.issue.return_value)
    service.issue.side_effect = outcome
    with api_client(AsyncMock()) as client:
        client.app.state.managed_vpn = service
        path = f"/vpn/sessions/{identifier}/managed"
        assert client.post(path).status_code == 401
        service.issue.assert_not_awaited()
        response = client.post(path, headers={"Authorization": "Bearer access-token"})
    service.issue.assert_awaited_once_with("access-token", identifier)
    assert response.status_code == status
    if code is None:
        assert response.headers["Cache-Control"] == "no-store"
        assert response.json()["profile"]["session"] == str(identifier)
    else:
        assert response.json()["error"]["code"] == code
        assert password not in response.text
