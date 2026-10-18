"""Transport shapes and provider policies; no simulated monetary result is a real charge."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from billing_fake import TestBillingProvider
from pydantic import ValidationError

from prettylisavpn.billing.operations_domain import (
    BillingCommand,
    ProviderMandate,
    ProviderRequest,
    ProviderResult,
    next_month,
    safe_redirect,
)
from prettylisavpn.billing.provider import validate_provider
from prettylisavpn.billing.worker import BillingWorker


def command(**updates):
    data = {
        "action": "SUBSCRIBE",
        "payment_route": "MIR",
        "request_id": str(uuid4()),
        "expected_revision": "revision",
        "offer_id": str(uuid4()),
        "currency": "RUB",
    }
    return {**data, **updates}


@pytest.mark.parametrize(
    "updates",
    [
        {"amount_minor": 1},
        {"currency": "EUR"},
        {"request_id": "bad"},
        {"expected_revision": ""},
        {"payment_route": None},
        {"offer_id": None},
        {"action": "CANCEL"},
        {"action": "PLATINUM"},
        {"provider_url": "https://evil.example"},
    ],
)
def test_invalid_commands_are_not_admitted(updates):
    with pytest.raises(ValidationError):
        BillingCommand.model_validate(command(**updates))


def test_canonical_fingerprint_covers_revision_route_currency_and_action():
    data = command()
    parsed = BillingCommand.model_validate(data)
    assert (
        parsed.fingerprint()
        == BillingCommand.model_validate(dict(reversed(list(data.items())))).fingerprint()
    )
    for name, value in [
        ("expected_revision", "new"),
        ("currency", "USD"),
        ("payment_route", "CRYPTO"),
        ("offer_id", str(uuid4())),
    ]:
        assert (
            BillingCommand.model_validate({**data, name: value}).fingerprint()
            != parsed.fingerprint()
        )
    BillingCommand.model_validate(command(action="CANCEL", payment_route=None, offer_id=None))


@pytest.mark.parametrize(
    "url",
    [
        "http://payments.example.test/pay",
        "https://evil.example/pay",
        "https://payments.example.test.evil/pay",
        "https://user@payments.example.test/pay",
        "https://payments.example.test:444/pay",
        "https://payments.example.test/#f",
        "https://payments.example.test/\nsecret",
    ],
)
def test_provider_redirect_is_not_arbitrary_navigation(url):
    with pytest.raises(ValueError):
        safe_redirect(url, frozenset({"payments.example.test"}))


@pytest.mark.parametrize(
    "date,expected",
    [("2026-01-31", "2026-02-28"), ("2028-01-31", "2028-02-29"), ("2026-12-31", "2027-01-31")],
)
def test_month_is_calendar_month_with_clamped_day(date, expected):
    assert (
        next_month(datetime.fromisoformat(date).replace(tzinfo=UTC)).date().isoformat() == expected
    )


def test_cancellation_requires_both_authoritative_confirmations():
    request = ProviderRequest(
        operation_id=uuid4(),
        account_id=uuid4(),
        action="CANCEL",
        payment_route=None,
        amount_minor=None,
        currency="RUB",
        previous_mandate_reference="old",
    )
    result = ProviderResult(operation_id=request.operation_id, status="SUCCEEDED")
    for receipt in [
        result,
        result.model_copy(update={"recurring_stopped": True}),
        result.model_copy(update={"previous_mandate_revoked": True}),
    ]:
        with pytest.raises(ValueError):
            BillingWorker._validate_confirmation(request, receipt)
    BillingWorker._validate_confirmation(
        request,
        result.model_copy(update={"recurring_stopped": True, "previous_mandate_revoked": True}),
    )


def test_price_currency_and_nonrecurring_route_must_match_confirmation():
    request = ProviderRequest(
        operation_id=uuid4(),
        account_id=uuid4(),
        action="SUBSCRIBE",
        payment_route="CRYPTO",
        amount_minor=100,
        currency="USD",
    )
    result = ProviderResult(
        operation_id=request.operation_id, status="SUCCEEDED", amount_minor=100, currency="USD"
    )
    for updates in [
        {"amount_minor": 99},
        {"currency": "RUB"},
        {"mandate": ProviderMandate(reference="ref", label="test")},
    ]:
        with pytest.raises(ValueError):
            BillingWorker._validate_confirmation(request, result.model_copy(update=updates))
    BillingWorker._validate_confirmation(request, result)


def test_live_adapter_cannot_be_enabled_in_this_release():
    provider = TestBillingProvider()
    provider.sandbox = False
    with pytest.raises(ValueError):
        validate_provider(provider)
