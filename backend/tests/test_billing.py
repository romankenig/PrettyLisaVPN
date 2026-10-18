"""Read-only billing policies, safe money and private HTTP boundaries."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from prettylisavpn.auth.session_service import InvalidSessionError
from prettylisavpn.billing.domain import Catalog, Price, DEFAULT_GROUP_ID, overview_for
from prettylisavpn.billing.service import BillingUnavailableError
from prettylisavpn.config import Settings
from prettylisavpn.main import create_app
from prettylisavpn.subscriptions.domain import Subscription, SubscriptionPlan, SubscriptionStatus

NOW = datetime(2026, 10, 18, 12, tzinfo=UTC)


def paid(**changes):
    return replace(Subscription(
        id=uuid4(), user_id=uuid4(), plan=SubscriptionPlan.PREMIUM,
        status=SubscriptionStatus.ACTIVE, current_period_start=NOW - timedelta(days=1),
        current_period_end=NOW + timedelta(days=20), auto_renew=False,
        created_at=NOW, updated_at=NOW,
    ), **changes)


def catalog():
    # Explicitly synthetic unit-test amounts; never a production fallback.
    return Catalog.model_validate({"entries": [{"group_id": str(DEFAULT_GROUP_ID), "valid_from": "2026-01-01T00:00:00Z", "offer": {"id": str(uuid4()), "prices": {
        "RUB": {"amount_minor": 12345, "original_amount_minor": 20000},
        "USD": {"amount_minor": 456, "original_amount_minor": None},
    }}}]})


@pytest.mark.parametrize("value", [0, -1, True, 1.5, "100", 1_000_000_000_001])
def test_price_rejects_invalid_minor_units(value):
    with pytest.raises(ValidationError):
        Price(amount_minor=value)


@pytest.mark.parametrize("original", [0, 99, 100])
def test_discount_requires_a_strictly_larger_original_price(original):
    with pytest.raises(ValidationError):
        Price(amount_minor=100, original_amount_minor=original)


def test_catalog_requires_both_currencies_and_never_sells_platinum():
    document = catalog().model_dump(mode="json")
    document["entries"][0]["offer"]["plan"] = "PLATINUM"
    with pytest.raises(ValidationError):
        Catalog.model_validate(document)
    document["entries"][0]["offer"]["plan"] = "PREMIUM"
    del document["entries"][0]["offer"]["prices"]["USD"]
    with pytest.raises(ValidationError):
        Catalog.model_validate(document)


def test_catalog_has_no_demo_default():
    value = overview_for(Subscription.new_free(uuid4(), NOW), Catalog(), None, NOW)
    assert value.offers == []
    assert value.actions == []
    assert not value.payment_operations_available
    assert value.current_price is value.payment_method is value.pending_operation_id is None


@pytest.mark.parametrize("plan", [SubscriptionPlan.PREMIUM, SubscriptionPlan.PLATINUM])
def test_paid_access_and_renewal_are_distinct_and_expiry_changes_revision(plan):
    subscription = paid(plan=plan)
    offers = catalog()
    revision = uuid4()
    active = overview_for(subscription, offers, revision, NOW)
    assert active.plan is plan
    assert active.status == "CANCELED"
    assert active.paid_until == subscription.current_period_end
    assert not active.auto_renew
    assert active.current_price is None  # Catalogue is not a receipt for an existing subscription.
    assert active.actions == []
    assert overview_for(subscription, offers, revision, NOW + timedelta(minutes=1)).revision == active.revision
    expired = overview_for(subscription, offers, revision, subscription.current_period_end)
    assert expired.status == "EXPIRED"
    assert expired.plan is SubscriptionPlan.FREE
    assert expired.revision != active.revision


def test_legacy_renewal_flag_is_preserved_without_fabricating_a_payment_method():
    value = overview_for(paid(auto_renew=True), catalog(), uuid4(), NOW)
    assert value.status == "ACTIVE" and value.auto_renew
    assert value.payment_method is None
    assert value.current_price is None


def test_same_snapshot_is_stable_but_catalog_and_subscription_changes_change_revision():
    subscription = paid()
    offers = catalog()
    revision = uuid4()
    value = overview_for(subscription, offers, revision, NOW)
    assert overview_for(subscription, offers, revision, NOW).revision == value.revision
    assert overview_for(subscription, offers, uuid4(), NOW).revision != value.revision
    assert overview_for(replace(subscription, updated_at=NOW + timedelta(seconds=1)), offers, revision, NOW).revision != value.revision


@pytest.mark.parametrize("error,status", [(None, 200), (InvalidSessionError(), 401), (BillingUnavailableError(), 503), (RuntimeError("private"), 503)])
def test_http_overview_is_private_read_only_and_uses_stable_errors(error, status):
    dependency = AsyncMock()
    service = AsyncMock()
    service.overview.return_value = overview_for(paid(), catalog(), uuid4(), NOW)
    service.overview.side_effect = error
    app = create_app(Settings(_env_file=None), postgres=dependency, valkey=dependency, product_events=AsyncMock(), authenticated_sessions=AsyncMock(), billing=service, support_worker=AsyncMock())
    with TestClient(app) as client:
        response = client.get("/billing/overview", headers={"Authorization": "Bearer token"})
        assert response.status_code == status
        assert response.headers["Cache-Control"] == "no-store"
        assert response.headers["Vary"] == "Authorization"
        if status == 200:
            assert response.json()["actions"] == []
            assert response.json()["payment_operations_available"] is False
        else:
            assert "private" not in response.text
        assert client.get("/billing/overview").status_code == 401
        assert client.post("/billing/operations", json={"action": "SUBSCRIBE"}).status_code == 404


def test_group_and_date_selection_is_exclusive_and_has_no_cross_group_fallback():
    document = catalog().model_dump(mode="json")
    entry = document["entries"][0]
    entry["valid_from"] = NOW.isoformat()
    entry["valid_to"] = (NOW + timedelta(hours=1)).isoformat()
    scheduled = Catalog.model_validate(document)
    assert not scheduled.offers_for(DEFAULT_GROUP_ID, NOW - timedelta(microseconds=1))
    assert scheduled.offers_for(DEFAULT_GROUP_ID, NOW)
    assert not scheduled.offers_for(DEFAULT_GROUP_ID, NOW + timedelta(hours=1))
    assert not scheduled.offers_for(uuid4(), NOW)
    for start, end in [(NOW, NOW), (NOW, NOW - timedelta(seconds=1))]:
        entry["valid_from"], entry["valid_to"] = start.isoformat(), end.isoformat()
        with pytest.raises(ValidationError):
            Catalog.model_validate(document)


def test_same_group_windows_cannot_overlap_but_may_touch():
    import copy
    document = catalog().model_dump(mode="json")
    first = document["entries"][0]
    first["valid_to"] = NOW.isoformat()
    second = copy.deepcopy(first)
    second["offer"]["id"] = str(uuid4())
    second["valid_from"] = NOW.isoformat()
    second["valid_to"] = None
    document["entries"].append(second)
    Catalog.model_validate(document)
    second["valid_from"] = (NOW - timedelta(seconds=1)).isoformat()
    with pytest.raises(ValidationError):
        Catalog.model_validate(document)
    second["group_id"] = str(uuid4())
    Catalog.model_validate(document)
    second["valid_from"] = "2026-10-18T00:00:00"
    with pytest.raises(ValidationError):
        Catalog.model_validate(document)
