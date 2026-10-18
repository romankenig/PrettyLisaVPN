"""Provider-declared route/currency/recurring capability policies."""

from unittest.mock import AsyncMock

import pytest
from billing_fake import TestBillingProvider
from pydantic import ValidationError

from prettylisavpn.billing.domain import PAYMENT_ROUTES, RouteCapability
from prettylisavpn.billing.provider import route_capabilities, validate_provider
from prettylisavpn.billing.sandbox import SandboxBillingProvider
from prettylisavpn.config import Settings


@pytest.mark.parametrize("action", ["SUBSCRIBE", "RENEW"])
@pytest.mark.parametrize("route,currencies,recurring", [
    ("MIR", ("RUB",), ("RUB",)),
    ("BANK_CARD", ("RUB", "USD"), ("RUB", "USD")),
    ("ALIPAY_WECHAT", ("USD",), ()),
    ("CRYPTO", ("USD",), ()),
])
def test_sandbox_matrix_is_exposed_and_enforced(action, route, currencies, recurring):
    provider = SandboxBillingProvider(AsyncMock(), Settings(_env_file=None))
    caps = route_capabilities(provider, action)
    assert tuple(cap.id for cap in caps) == PAYMENT_ROUTES
    cap = next(cap for cap in caps if cap.id == route)
    assert cap.currencies == currencies and cap.recurring_currencies == recurring
    for currency in ("RUB", "USD"):
        assert provider.supports(action, route, currency) == (currency in currencies)


def test_no_adapter_exposes_four_disabled_routes_without_inventing_currencies():
    assert [cap.model_dump(mode="json") for cap in route_capabilities(None, "SUBSCRIBE")] == [
        {"id": route, "currencies": [], "recurring_currencies": []} for route in PAYMENT_ROUTES
    ]


def test_dynamic_provider_support_and_contract_currency_filter_metadata():
    provider = TestBillingProvider()
    provider.unsupported.add(("MIR", "USD"))
    caps = route_capabilities(provider, "SUBSCRIBE")
    assert caps[0].currencies == caps[0].recurring_currencies == ("RUB",)
    locked = route_capabilities(provider, "RENEW", "RUB")
    assert all("USD" not in cap.currencies for cap in locked)


@pytest.mark.parametrize("changes", [
    {"currencies": ("RUB", "RUB")},
    {"recurring_currencies": ("RUB", "RUB")},
    {"currencies": ("RUB",), "recurring_currencies": ("USD",)},
    {"id": "CRYPTO", "currencies": ("USD",), "recurring_currencies": ("USD",)},
    {"id": "UNKNOWN"}, {"currencies": ("EUR",)},
])
def test_inconsistent_capabilities_are_rejected(changes):
    with pytest.raises(ValidationError):
        RouteCapability.model_validate({"id": "BANK_CARD", **changes})


def test_duplicate_provider_routes_are_rejected():
    provider = TestBillingProvider()
    provider.capabilities = (RouteCapability(id="MIR"), RouteCapability(id="MIR"))
    with pytest.raises(ValueError):
        validate_provider(provider)
