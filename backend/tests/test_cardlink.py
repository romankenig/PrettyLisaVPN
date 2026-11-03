"""Contract and adversarial tests; no real bills, credentials or money are used."""

import hashlib
from dataclasses import replace
from unittest.mock import AsyncMock
from urllib.parse import urlencode
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from prettylisavpn.billing.cardlink import (
    MAX_CALLBACK_BYTES,
    CardlinkAPI,
    CardlinkCallbacks,
    CardlinkError,
    ExpectedBill,
    Notification,
    VerifiedBill,
    authenticate_notification,
)
from prettylisavpn.config import Settings
from prettylisavpn.main import create_app

TOKEN = SecretStr("test-only-not-a-real-cardlink-api-token")
ORDER = uuid4()
BILL = "test-bill-123"


def payload(**changes):
    data = {
        "InvId": str(ORDER),
        "OutSum": "199.00",
        "TrsId": BILL,
        "Status": "SUCCESS",
        "CurrencyIn": "RUB",
        "Commission": "0.00",
        "SignatureValue": hashlib.md5(
            f"199.00:{ORDER}:{TOKEN.get_secret_value()}".encode(), usedforsecurity=False
        )
        .hexdigest()
        .upper(),
    }
    data.update(changes)
    return urlencode(data).encode()


def bill(**changes):
    data = dict(
        id=BILL,
        order_id=str(ORDER),
        status="SUCCESS",
        type="NORMAL",
        amount="199.00",
        currency_in="RUB",
        success=True,
    )
    data.update(changes)
    return VerifiedBill.model_validate(data)


@pytest.fixture
def service():
    api, store = AsyncMock(), AsyncMock()
    api.lookup.return_value = bill()
    store.expected.return_value = ExpectedBill(ORDER, BILL, 19900, "RUB")
    return CardlinkCallbacks(TOKEN, api, store)


def test_signature_uses_original_decimal_spelling_and_is_not_logged(caplog):
    assert authenticate_notification(payload(), TOKEN) == Notification(ORDER, BILL)
    with pytest.raises(CardlinkError, match="CARDLINK_SIGNATURE_INVALID"):
        authenticate_notification(payload(OutSum="199"), TOKEN)
    assert TOKEN.get_secret_value() not in caplog.text


@pytest.mark.parametrize(
    "body",
    [
        b"%ff=x",
        b"InvId=%QQ",
        b"no-equals",
        b"",
        b"a=" * 50,
        payload() + b"&OutSum=199.00",
        payload(OutSum="NaN"),
        payload(OutSum="1e2"),
        payload(OutSum="-1"),
        payload(OutSum="199.001"),
        payload(InvId="not-uuid"),
        payload(TrsId="https://evil.invalid"),
        payload(SignatureValue="bad"),
    ],
)
def test_malformed_notifications_rejected(body):
    with pytest.raises(CardlinkError):
        authenticate_notification(body, TOKEN)


async def test_verification_ignores_unsigned_claims_and_optional_personal_data(service):
    service.api.lookup.return_value = bill(status="UNDERPAID")
    await service.receive(payload(Status="SUCCESS", CurrencyIn="USD", PayerEmail="private-marker"))
    service.store.record.assert_awaited_once_with(service.store.expected.return_value, "UNDERPAID")


@pytest.mark.parametrize(
    "changes",
    [
        {"id": "wrong"},
        {"order_id": str(uuid4())},
        {"amount": "1.00"},
        {"currency_in": "USD"},
        {"type": "MULTI"},
        {"amount": "199.001"},
    ],
)
async def test_authoritative_invoice_mismatch_cannot_enter_inbox(service, changes):
    service.api.lookup.return_value = bill(**changes)
    with pytest.raises(CardlinkError, match="CARDLINK_BILL_MISMATCH"):
        await service.receive(payload())
    service.store.record.assert_not_awaited()


@pytest.mark.parametrize("status", ["NEW", "PROCESS"])
async def test_pending_provider_state_is_retryable(service, status):
    service.api.lookup.return_value = bill(status=status)
    with pytest.raises(CardlinkError, match="CARDLINK_VERIFICATION_PENDING"):
        await service.receive(payload())
    service.store.record.assert_not_awaited()


async def test_invalid_signature_does_not_query_storage_or_provider(service):
    with pytest.raises(CardlinkError):
        await service.receive(payload(SignatureValue="0" * 32))
    service.store.expected.assert_not_awaited()
    service.api.lookup.assert_not_awaited()


async def test_unknown_or_unbound_order_does_not_contact_provider(service):
    service.store.expected.side_effect = CardlinkError("CARDLINK_ORDER_NOT_FOUND", 404)
    with pytest.raises(CardlinkError):
        await service.receive(payload())
    service.api.lookup.assert_not_awaited()


async def test_signed_gross_amount_is_not_mistaken_for_invoice_amount(service):
    # A payer commission can be included in OutSum; quote must match the API bill amount.
    service.store.expected.return_value = replace(
        service.store.expected.return_value, amount_minor=19500
    )
    service.api.lookup.return_value = bill(amount="195.00")
    await service.receive(payload())
    service.store.record.assert_awaited_once()


async def test_api_uses_fixed_https_host_and_token_and_discards_extra_fields():
    def respond(request):
        assert str(request.url) == f"https://cardlink.link/api/v1/bill/status?id={BILL}"
        assert request.headers["Authorization"] == f"Bearer {TOKEN.get_secret_value()}"
        return httpx.Response(200, json={**bill().model_dump(mode="json"), "PayerEmail": "private"})

    api = CardlinkAPI(TOKEN, transport=httpx.MockTransport(respond))
    assert (await api.lookup(BILL)) == bill()


@pytest.mark.parametrize("kind", ["timeout", "redirect", "denied", "bad-json", "missing", "large"])
async def test_api_failure_does_not_become_payment_evidence(kind):
    def respond(request):
        if kind == "timeout":
            raise httpx.ReadTimeout("private-marker", request=request)
        if kind == "redirect":
            return httpx.Response(302, headers={"location": "https://evil.invalid"})
        if kind == "denied":
            return httpx.Response(403)
        if kind == "missing":
            return httpx.Response(200, json={"success": True})
        return httpx.Response(
            200, content=b"x" * (MAX_CALLBACK_BYTES + 1) if kind == "large" else b"bad"
        )

    with pytest.raises(CardlinkError, match="CARDLINK_VERIFICATION_UNAVAILABLE"):
        await CardlinkAPI(TOKEN, transport=httpx.MockTransport(respond)).lookup(BILL)


@pytest.fixture
def client(service):
    return TestClient(
        create_app(Settings(_env_file=None, environment="test"), cardlink_callbacks=service)
    )


def test_public_discovery_does_not_confirm_a_payment():
    client = TestClient(create_app(Settings(_env_file=None, environment="test")))
    for method in ("GET", "HEAD"):
        response = client.request(method, "/api/payments/cardlink/callback")
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
    response = client.post("/api/payments/cardlink/callback", content=payload())
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "CARDLINK_NOT_CONFIGURED"


def test_callback_requires_form_and_bounded_body(client, service):
    assert client.post("/api/payments/cardlink/callback", json={}).status_code == 415
    assert (
        client.post(
            "/api/payments/cardlink/callback",
            content=b"x" * (MAX_CALLBACK_BYTES + 1),
            headers={"content-type": "application/x-www-form-urlencoded"},
        ).status_code
        == 413
    )
    service.store.record.assert_not_awaited()


def test_http_receipt_only_after_durable_commit(client, service, caplog):
    response = client.post(
        "/api/payments/cardlink/callback",
        content=payload(),
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 200
    assert response.json() == {"status": "received"}
    service.store.record.side_effect = RuntimeError("private-marker")
    response = client.post(
        "/api/payments/cardlink/callback",
        content=payload(),
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 503
    assert response.headers["retry-after"] == "10"
    assert "private-marker" not in response.text + caplog.text
    assert TOKEN.get_secret_value() not in response.text + caplog.text


def test_secret_is_redacted_and_does_not_enable_billing():
    config = Settings(_env_file=None, cardlink_api_token=TOKEN)
    assert TOKEN.get_secret_value() not in repr(config)
    assert config.billing_provider == "disabled"
