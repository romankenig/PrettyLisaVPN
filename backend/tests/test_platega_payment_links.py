"""One-off link API probe. Links do not create recurring billing authorities."""

import json
from uuid import uuid4

import httpx
import pytest
from test_platega_api import MERCHANT, api

from prettylisavpn.billing.platega_api import PlategaUnavailable


def link_response(operation, identity):
    return {
        "id": str(identity),
        "url": "https://pay.platega.io/link/" + str(identity),
        "usageMode": 1,
        "paymentMode": 0,
        "currency": "RUB",
        "minAmount": "199.99",
        "maxAmount": "199.99",
        "orderId": str(operation),
        "payload": str(operation),
        "active": True,
    }


@pytest.mark.parametrize("status", [200, 201])
async def test_link_is_single_use_fixed_amount_and_same_idempotency_key(status):
    operation, identity = uuid4(), uuid4()

    def handler(request):
        assert request.url.path == "/v2/payment-links"
        assert request.headers["Idempotency-Key"] == str(operation)
        body = json.loads(request.content)
        assert body["minAmount"] == body["maxAmount"] == "199.99"
        assert body["usageMode"] == 1 and body["paymentMode"] == 0
        assert body["payload"] == body["orderId"] == str(operation)
        assert "paymentMethod" not in body and "metadata" not in body
        assert body["return"] == "https://prettylisavpn.com/account/success/"
        return httpx.Response(status, json=link_response(operation, identity))

    value = await api(handler).create_payment_link(operation, 19999)
    assert value.id == identity and value.amount_minor == 19999


@pytest.mark.parametrize(
    "field,value",
    [
        ("usageMode", 0),
        ("minAmount", "1"),
        ("currency", "USD"),
        ("payload", "someone-else"),
        ("url", "https://evil.example/pay"),
    ],
)
async def test_inconsistent_link_or_external_redirect_is_rejected(field, value):
    operation, identity = uuid4(), uuid4()
    response = link_response(operation, identity) | {field: value}
    with pytest.raises(PlategaUnavailable):
        await api(lambda _: httpx.Response(201, json=response)).create_payment_link(
            operation, 19999
        )


async def test_link_consumption_does_not_prove_payment_and_ledger_rechecks_merchant():
    operation, identity, payment = uuid4(), uuid4(), uuid4()

    def handler(request):
        if request.url.path.endswith("/transactions"):
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": str(payment),
                            "paymentLinkId": str(identity),
                            "amount": 199.99,
                            "currency": "RUB",
                            "status": "CONFIRMED",
                        }
                    ],
                    "totalCount": 1,
                },
            )
        if request.url.path.startswith("/transaction/"):
            return httpx.Response(
                200,
                json={
                    "id": str(payment),
                    "mechantId": str(MERCHANT),
                    "status": "PENDING",
                    "paymentDetails": {"amount": 199.99, "currency": "RUB"},
                },
            )
        return httpx.Response(
            200,
            json=link_response(operation, identity)
            | {"consumedTransactionId": str(payment), "active": False},
        )

    provider = api(handler)
    link = await provider.payment_link(identity, operation, 19999)
    assert not link.active
    assert (await provider.payment_link_payments(link))[0].status == "PENDING"
