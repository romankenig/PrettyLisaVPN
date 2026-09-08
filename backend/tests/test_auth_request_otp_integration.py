import os
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from prettylisavpn.config import Settings
from prettylisavpn.connections import Valkey
from prettylisavpn.main import create_app
from prettylisavpn.product_events.domain import ProductEventName

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1",
        reason="Set RUN_INTEGRATION_TESTS=1 with Valkey running",
    ),
]


class FakeDependency:
    async def ping(self) -> None:
        return None

    async def close(self) -> None:
        return None


class CapturingEmailProvider:
    def __init__(self) -> None:
        self.sent = []

    async def send(self, email) -> None:
        self.sent.append(email)


class CapturingEvents:
    def __init__(self) -> None:
        self.names: list[ProductEventName] = []

    async def record(self, event_name: ProductEventName) -> None:
        self.names.append(event_name)


def settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "otp_hmac_secret": f"request-endpoint-integration-secret-{uuid4().hex}",
        "otp_request_cooldown_seconds": 30,
        "otp_email_request_limit": 20,
        "otp_ip_request_limit": 20,
    }
    values.update(overrides)
    return Settings(**values)


async def test_request_endpoint_persists_verifiable_otp_in_real_valkey():
    config = settings()
    valkey = Valkey(config)
    email = CapturingEmailProvider()
    events = CapturingEvents()
    app = create_app(
        config,
        postgres=FakeDependency(),
        valkey=valkey,
        email_provider=email,
        product_events=events,
    )

    transport = ASGITransport(app=app, client=("192.0.2.10", 12345))
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/auth/request-otp", json={"email": "User@Example.COM"})
            assert response.status_code == 202
            assert len(email.sent) == 1
            code = email.sent[0].text_body.split("\n")[2]
            assert await valkey.otp.verify("user@example.com", code)

    assert events.names == [ProductEventName.OTP_REQUESTED, ProductEventName.OTP_SENT]


async def test_request_endpoint_enforces_real_valkey_cooldown():
    config = settings()
    valkey = Valkey(config)
    app = create_app(
        config,
        postgres=FakeDependency(),
        valkey=valkey,
        email_provider=CapturingEmailProvider(),
        product_events=CapturingEvents(),
    )

    transport = ASGITransport(app=app, client=("192.0.2.11", 12345))
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            first = await client.post("/auth/request-otp", json={"email": "cooldown@example.com"})
            second = await client.post("/auth/request-otp", json={"email": "cooldown@example.com"})

    assert first.status_code == 202
    assert second.status_code == 429
