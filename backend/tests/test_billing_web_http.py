"""Cookie/CSRF/ownership boundary. Redirects are never settlement evidence."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_billing import NOW, catalog, paid

from prettylisavpn.auth.session_service import AccessIdentity, InvalidSessionError
from prettylisavpn.billing.domain import overview_for
from prettylisavpn.billing.operations_domain import BillingOperation
from prettylisavpn.billing.web_routes import native_router, router
from prettylisavpn.billing.web_sessions import COOKIE, WEB_ORIGIN

HEADERS = {"Origin": WEB_ORIGIN, "X-PrettyLisa-Web": "1"}
TOKEN = "a" * 43


def test_legacy_clients_do_not_receive_unknown_sbp_route_or_purchase_action():
    from prettylisavpn.billing.domain import RouteCapability
    from prettylisavpn.billing.router import router as private_router

    app = FastAPI()
    app.include_router(private_router)
    value = overview_for(paid(), catalog(), uuid4(), NOW, actions=["SUBSCRIBE", "CANCEL"])
    value = value.model_copy(
        update={
            "payment_routes": [
                *value.payment_routes,
                RouteCapability(id="SBP", currencies=("RUB",), recurring_currencies=("RUB",)),
            ]
        }
    )
    app.state.billing = SimpleNamespace(overview=AsyncMock(return_value=value))
    with TestClient(app) as client:
        old = client.get("/billing/overview", headers={"Authorization": "Bearer native"}).json()
        new = client.get(
            "/billing/overview",
            headers={"Authorization": "Bearer native", "X-PrettyLisa-Billing-Version": "2"},
        ).json()
    assert len(old["payment_routes"]) == 4 and old["actions"] == ["CANCEL"]
    assert len(new["payment_routes"]) == 5 and "SUBSCRIBE" in new["actions"]
    assert old["revision"] == new["revision"]


@pytest.fixture
def web():
    app = FastAPI()
    app.include_router(router)
    app.include_router(native_router)
    account = uuid4()
    sessions = SimpleNamespace(
        authenticate=AsyncMock(return_value=account),
        email=AsyncMock(return_value="me@example.com"),
        login=AsyncMock(return_value=TOKEN),
        exchange=AsyncMock(return_value=TOKEN),
        handoff=AsyncMock(return_value=WEB_ORIGIN + "/account/#handoff=" + TOKEN),
        tokens=SimpleNamespace(revoke=AsyncMock()),
    )
    app.state.billing_web_sessions = sessions
    app.state.billing = SimpleNamespace(
        overview_for_account=AsyncMock(return_value=overview_for(paid(), catalog(), uuid4(), NOW))
    )
    operation = BillingOperation(id=uuid4(), status="PENDING")
    app.state.billing_operations = SimpleNamespace(
        start_for_account=AsyncMock(return_value=operation),
        get_for_account=AsyncMock(return_value=operation),
    )
    app.state.authenticated_sessions = SimpleNamespace(
        authenticate=AsyncMock(return_value=AccessIdentity(account, uuid4(), uuid4()))
    )
    with TestClient(app, base_url=WEB_ORIGIN) as client:
        yield client, app, sessions, account, operation


@pytest.mark.parametrize(
    "headers",
    [{}, {"Origin": "https://evil.example", "X-PrettyLisa-Web": "1"}, {"Origin": WEB_ORIGIN}],
)
@pytest.mark.parametrize("path", ["/login", "/exchange", "/operations", "/logout", "/request-otp"])
def test_writes_require_exact_origin_and_custom_header(web, headers, path):
    client, _, sessions, _, _ = web
    response = client.post("/api/web/billing" + path, headers=headers, json={})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "WEB_ORIGIN_INVALID"
    assert response.headers["cache-control"] == "no-store"
    sessions.authenticate.assert_not_awaited()
    sessions.login.assert_not_awaited()


@pytest.mark.parametrize(
    "path,body",
    [("login", {"email": "me@example.com", "code": "123456"}), ("exchange", {"token": TOKEN})],
)
def test_login_and_exchange_only_issue_secure_httponly_cookie(web, path, body):
    client, _, _, _, _ = web
    response = client.post("/api/web/billing/" + path, headers=HEADERS, json=body)
    assert response.status_code == 200
    assert TOKEN not in response.text
    cookie = response.headers["set-cookie"]
    assert COOKIE in cookie and "HttpOnly" in cookie and "Secure" in cookie
    assert "SameSite=strict" in cookie and "Path=/" in cookie and "Domain" not in cookie


def test_web_read_and_command_use_authenticated_account_only(web):
    client, app, sessions, account, operation = web
    client.cookies.set(COOKIE, TOKEN)
    response = client.get("/api/web/billing/overview?user_id=" + str(uuid4()))
    assert response.status_code == 200 and response.json()["account_id"] == str(account)
    sessions.authenticate.assert_awaited_with(TOKEN)
    app.state.billing.overview_for_account.assert_awaited_with(account)
    command = dict(
        action="CANCEL",
        payment_route=None,
        offer_id=None,
        currency="RUB",
        request_id=str(uuid4()),
        expected_revision="revision",
    )
    response = client.post("/api/web/billing/operations", headers=HEADERS, json=command)
    assert response.status_code == 200 and response.json()["status"] == "PENDING"
    assert app.state.billing_operations.start_for_account.await_args.args[0] == account
    assert client.get("/api/web/billing/operations/" + str(operation.id)).status_code == 200
    app.state.billing_operations.get_for_account.assert_awaited_with(account, operation.id)


def test_invalid_cookie_and_provider_return_do_not_authenticate(web):
    client, _, sessions, _, _ = web
    sessions.authenticate.side_effect = InvalidSessionError
    response = client.get("/api/web/billing/overview?status=CONFIRMED")
    assert response.status_code == 401
    assert "private" not in response.text


def test_logout_revokes_cookie_and_native_handoff_requires_bearer(web):
    client, app, sessions, account, _ = web
    assert client.post("/billing/portal", json={}).status_code == 401
    response = client.post("/billing/portal", headers={"Authorization": "Bearer native"}, json={})
    assert response.status_code == 200
    app.state.authenticated_sessions.authenticate.assert_awaited_once_with("native")
    sessions.handoff.assert_awaited_once_with(account)
    client.cookies.set(COOKIE, TOKEN)
    response = client.post("/api/web/billing/logout", headers=HEADERS, json={})
    assert response.status_code == 200 and "Max-Age=0" in response.headers["set-cookie"]
    sessions.tokens.revoke.assert_awaited_with(TOKEN)


def test_web_otp_uses_existing_rate_limited_issuer(web, monkeypatch):
    client, _, _, _, _ = web
    from starlette.responses import JSONResponse

    send = AsyncMock(return_value=JSONResponse({"status": "accepted"}, 202))
    monkeypatch.setattr("prettylisavpn.billing.web_routes.request_otp", send)
    response = client.post(
        "/api/web/billing/request-otp", headers=HEADERS, json={"email": "me@example.com"}
    )
    assert response.status_code == 202
    assert str(send.await_args.args[0].email) == "me@example.com"


def test_platega_callback_auth_body_limit_and_disabled():
    from prettylisavpn.billing.platega_routes import router as callbacks

    app = FastAPI()
    app.include_router(callbacks)
    handler = SimpleNamespace(authenticated=Mock(return_value=False), accept=AsyncMock())
    with TestClient(app) as client:
        path = "/api/payments/platega/callback"
        assert client.post(path, json={}).status_code == 503
        app.state.platega_callbacks = handler
        assert client.post(path, json={}).status_code == 401
        handler.accept.assert_not_awaited()
        handler.authenticated.return_value = True
        assert client.post(path, content="{}").status_code == 415
        assert (
            client.post(
                path, content="a" * 16385, headers={"content-type": "application/json"}
            ).status_code
            == 413
        )
        assert client.post(path, json={}).status_code == 200
        handler.accept.assert_awaited_once()
