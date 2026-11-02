from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from prettylisavpn.config import Settings
from prettylisavpn.main import create_app


@pytest.fixture
def client():
    # These public routes must work without touching accounts or billing state.
    app = create_app(Settings(_env_file=None, environment="test"))
    app.state.billing_operations = AsyncMock()
    return TestClient(app)


@pytest.mark.parametrize("page", ["success", "failure"])
def test_returns_are_public_static_and_ignore_payment_claims(client, page):
    response = client.get(
        f"/payment/{page}",
        params={"status": "paid", "user_id": "secret-marker", "next": "https://evil.invalid"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert 'lang="ru"' in response.text
    assert "PrettyLisaVPN" in response.text
    assert "secret-marker" not in response.text
    assert "evil.invalid" not in response.text
    assert "noindex" in response.text
    assert "<script" not in response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    client.app.state.billing_operations.start.assert_not_called()
    client.app.state.billing_operations.get.assert_not_called()


@pytest.mark.parametrize("asset,mime", [("style.css", "text/css"), ("logo.svg", "image/svg+xml")])
def test_payment_assets_are_packaged_and_have_expected_types(client, asset, mime):
    response = client.get(f"/payment/assets/{asset}")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith(mime)
    assert response.headers["x-content-type-options"] == "nosniff"
    assert len(response.content) > 100


@pytest.mark.parametrize(
    "content_type,body",
    [
        ("application/json", b'{"status":"success","signature":"private-marker"}'),
        ("application/x-www-form-urlencoded", b"status=success&secret=private-marker"),
        ("application/json", b"invalid-json"),
    ],
)
def test_unconfigured_callback_never_acknowledges_a_payment(client, caplog, content_type, body):
    response = client.post(
        "/api/payments/1plat/callback", content=body, headers={"Content-Type": content_type}
    )
    assert response.status_code == 503
    assert response.json() == {"error": {"code": "BILLING_NOT_CONFIGURED"}}
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["retry-after"] == "60"
    assert "private-marker" not in response.text + caplog.text
    client.app.state.billing_operations.start.assert_not_called()
    client.app.state.billing_operations.get.assert_not_called()


def test_callback_is_post_only_and_cannot_be_activated_by_browser_navigation(client):
    response = client.get("/api/payments/1plat/callback?status=success")
    assert response.status_code == 405
    assert client.get("/payment/assets/unknown.txt").status_code == 404


def test_public_domain_does_not_expose_private_dashboard_or_account_api():
    caddy = Path("../infra/deployment/Caddyfile").read_text()
    public = caddy.split("prettylisavpn.com {", 1)[1].split("{$API_DOMAIN}", 1)[0]
    assert "/payment/success /payment/failure" in public
    assert "/api/payments/1plat/callback" in public
    assert "max_size 64KB" in public
    assert 'respond "Not found" 404' in public
    assert "/dashboard" not in public
    assert "\n\tlog {" not in public
