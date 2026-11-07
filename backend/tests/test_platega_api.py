"""Platega wire contract with a fake HTTP transport; no merchant or banking calls."""

import json
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import httpx
import pytest
from pydantic import SecretStr

from prettylisavpn.billing.platega_api import (
    PlategaAPI,
    PlategaUnavailable,
    description_for,
    minor_units,
    subscription_url,
)

MERCHANT = UUID("11111111-1111-4111-8111-111111111111")
SUBSCRIPTION = UUID("22222222-2222-4222-8222-222222222222")
SECRET = "test-only-platega-secret-never-real"


def test_live_provider_cannot_start_with_placeholder_or_missing_secret():
    from prettylisavpn.config import Settings

    with pytest.raises(ValueError, match="merchant placeholder"):
        Settings(_env_file=None, billing_provider="platega", platega_secret=SECRET)
    with pytest.raises(ValueError, match="merchant placeholder"):
        Settings(_env_file=None, billing_provider="platega", platega_merchant_id=MERCHANT)
    configured = Settings(
        _env_file=None,
        billing_provider="platega",
        platega_merchant_id=MERCHANT,
        platega_secret=SECRET,
    )
    assert configured.billing_provider == "platega"
    assert SECRET not in repr(configured)


def api(handler):
    return PlategaAPI(MERCHANT, SecretStr(SECRET), transport=httpx.MockTransport(handler))


def subscription(operation_id):
    return {
        "id": str(SUBSCRIPTION),
        "status": "Active",
        "amount": 199,
        "currencyCode": "RUB",
        "intervalUnit": "Month",
        "intervalCount": 1,
        "nextChargeAt": "2026-12-06T10:00:00Z",
        "lastChargeAt": "2026-11-06T10:00:00Z",
        "description": description_for(operation_id),
        "createdAt": "2026-11-06T09:59:00Z",
        "chargeMetrics": {"chargesSuccess": 1},
    }


@pytest.mark.parametrize("matching", [True, False])
async def test_export_recovery_requires_merchant_and_exact_order_description_twice(matching):
    operation, payment = uuid4(), uuid4()

    def handler(request):
        if request.url.path.endswith("/export/json"):
            assert json.loads(request.content)["timeZoneId"] == "UTC"
            return httpx.Response(
                200,
                json=[
                    {
                        "recordId": str(payment),
                        "description": description_for(operation),
                        "amount": 199,
                        "currencyCode": "RUB",
                    }
                ],
            )
        return httpx.Response(
            200,
            json={
                "id": str(payment),
                "mechantId": str(MERCHANT),
                "status": "CONFIRMED",
                "paymentDetails": {"amount": 199, "currency": "RUB"},
                "description": description_for(operation) if matching else "other order",
            },
        )

    if matching:
        assert (await api(handler).recover_payments(operation, datetime.now(UTC)))[0].id == payment
    else:
        with pytest.raises(PlategaUnavailable):
            await api(handler).recover_payments(operation, datetime.now(UTC))


async def test_create_uses_monthly_sbp_and_database_quote_not_client_money():
    operation = uuid4()
    calls = []

    def handler(request):
        calls.append(request)
        assert str(request.url) == "https://app.platega.io/transaction/process"
        assert request.headers["X-MerchantId"] == str(MERCHANT)
        assert request.headers["X-Secret"] == SECRET
        assert json.loads(request.content) == {
            "paymentMethod": 6,
            "paymentDetails": {"amount": 199, "currency": "RUB", "interval": 3, "intervalCount": 1},
            "description": description_for(operation),
            "metadata": {"user_email": "payer@example.com"},
        }
        return httpx.Response(
            200,
            json={
                "transactionId": str(SUBSCRIPTION),
                "merchantId": str(MERCHANT),
                "paymentMethod": "Subscription",
                "status": "PENDING",
                "redirect": subscription_url(SUBSCRIPTION),
            },
        )

    result = await api(handler).create(operation, 19900, "payer@example.com")
    assert result.id == SUBSCRIPTION and len(calls) == 1
    assert SECRET not in repr(result)


async def test_timeout_does_not_retry_create_or_expose_provider_error():
    calls = []

    def handler(request):
        calls.append(request)
        raise httpx.ReadTimeout(SECRET, request=request)

    with pytest.raises(PlategaUnavailable) as caught:
        await api(handler).create(uuid4(), 19900, "payer@example.com")
    assert len(calls) == 1 and SECRET not in str(caught.value)


@pytest.mark.parametrize("value", [True, "199", Decimal("1.234"), Decimal("NaN"), -1, 0])
def test_untrusted_or_fractional_kopeck_amounts_are_rejected(value):
    with pytest.raises(ValueError):
        minor_units(value)


def test_decimal_money_is_exact_and_placeholder_cannot_contact_provider():
    assert minor_units(Decimal("199.99")) == 19999
    with pytest.raises(ValueError):
        PlategaAPI(UUID(int=0), SecretStr(SECRET))


async def test_subscription_schedule_is_authoritative_and_separate_from_paid_confirmation():
    value = await api(lambda _: httpx.Response(200, json=subscription(uuid4()))).subscription(
        SUBSCRIPTION
    )
    assert value.status == "Active" and value.amount_minor == 19900
    assert value.next_charge_at == datetime(2026, 12, 6, 10, tzinfo=UTC)
    assert not hasattr(value, "payment_confirmed")  # Active alone must never grant Premium.


@pytest.mark.parametrize(
    "mutation",
    [
        {"merchantId": str(uuid4())},
        {"redirect": "https://evil.example/collect"},
        {"redirect": "https://pay.platega.io/subscription/" + str(uuid4())},
    ],
)
async def test_create_rejects_cross_merchant_or_changed_redirect(mutation):
    value = {
        "transactionId": str(SUBSCRIPTION),
        "merchantId": str(MERCHANT),
        "paymentMethod": "Subscription",
        "status": "pending",
        "redirect": subscription_url(SUBSCRIPTION),
        **mutation,
    }
    with pytest.raises(PlategaUnavailable):
        await api(lambda _: httpx.Response(200, json=value)).create(
            uuid4(), 19900, "payer@example.com"
        )


async def test_recovery_searches_all_pages_and_never_posts_another_subscription():
    operation, calls = uuid4(), []

    def handler(request):
        calls.append(request)
        assert request.method == "GET"
        if request.url.path == "/subscription":
            page = int(request.url.params["page"])
            items = (
                [{"description": "another operation"}]
                if page == 1
                else [{"id": str(SUBSCRIPTION), "description": description_for(operation)}]
            )
            return httpx.Response(
                200, json={"items": items, "total": 101, "page": page, "size": 100}
            )
        return httpx.Response(200, json=subscription(operation))

    found = await api(handler).recover(operation, datetime(2026, 11, 6, tzinfo=UTC))
    assert len(calls) == 3 and [item.id for item in found] == [SUBSCRIPTION]


async def test_charge_verification_checks_merchant_identity_and_exact_amount():
    payment = uuid4()
    value = {
        "id": str(payment),
        "mechantId": str(MERCHANT),
        "status": "CONFIRMED",
        "paymentDetails": {"amount": 199, "currency": "RUB"},
    }
    result = await api(lambda _: httpx.Response(200, json=value)).payment(payment)
    assert result.amount_minor == 19900 and result.status == "CONFIRMED"
    value["mechantId"] = str(uuid4())
    with pytest.raises(PlategaUnavailable):
        await api(lambda _: httpx.Response(200, json=value)).payment(payment)


async def test_provider_redirect_is_not_followed_with_merchant_secret():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(307, headers={"Location": "https://evil.example"})

    with pytest.raises(PlategaUnavailable):
        await api(handler).subscription(SUBSCRIPTION)
    assert len(calls) == 1
