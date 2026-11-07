"""Account billing presentation cannot invent a schedule or expose card numbers."""

from datetime import timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError
from test_billing import NOW, catalog, paid

from prettylisavpn.billing.domain import Catalog, CurrentPrice, PaymentMethod, overview_for
from prettylisavpn.billing.operations_domain import ProviderMandate
from prettylisavpn.subscriptions.domain import SubscriptionPlan


@pytest.mark.parametrize("model", [PaymentMethod, ProviderMandate])
@pytest.mark.parametrize("last4", ["4242424242424242", "42", "abcd", " 4242", None])
def test_only_verified_four_digit_card_summary_is_accepted(model, last4):
    identity = {"provider": "test"} if model is PaymentMethod else {"reference": "opaque"}
    with pytest.raises(ValidationError):
        model(**identity, label="Visa •••• 4242", kind="CARD", card_brand="visa", card_last4=last4)


@pytest.mark.parametrize("kind", ["UNKNOWN", "SBP"])
def test_noncard_method_never_claims_card_brand_or_last_four(kind):
    with pytest.raises(ValidationError):
        PaymentMethod(
            provider="test", label="test", kind=kind, card_brand="visa", card_last4="4242"
        )


@pytest.mark.parametrize("label", ["4242 4242 4242 4242", "4242-4242-4242-4242"])
def test_adapter_cannot_put_full_card_number_in_human_label(label):
    with pytest.raises(ValidationError):
        ProviderMandate(reference="opaque", label=label)


def test_displayed_next_charge_is_explicit_and_uses_contract_amount():
    price = CurrentPrice(currency="RUB", amount_minor=12345)
    method = PaymentMethod(
        provider="test", label="Visa •••• 4242", kind="CARD", card_brand="visa", card_last4="4242"
    )
    scheduled = NOW + timedelta(days=20)
    value = overview_for(
        paid(auto_renew=True),
        catalog(),
        uuid4(),
        NOW,
        current_price=price,
        payment_method=method,
        next_charge_at=scheduled,
    )
    assert value.next_charge_at == scheduled
    assert value.next_charge_price == price
    assert value.payment_method.card_last4 == "4242"
    assert "reference" not in value.payment_method.model_dump()
    unknown = overview_for(
        paid(auto_renew=True), catalog(), uuid4(), NOW, current_price=price, payment_method=method
    )
    assert unknown.next_charge_at is unknown.next_charge_price is None
    canceled = overview_for(
        paid(),
        catalog(),
        uuid4(),
        NOW,
        current_price=price,
        next_charge_at=scheduled,
        new_contract_required=True,
    )
    assert canceled.next_charge_at is canceled.next_charge_price is None


def test_price_changes_only_after_explicit_cancellation_and_new_contract():
    old = catalog().entries[0].offer
    document = catalog().model_dump(mode="json")
    document["entries"][0]["offer"]["prices"]["RUB"] = {
        "amount_minor": 54321,
        "original_amount_minor": None,
    }
    latest = Catalog.model_validate(document)
    subscription = paid(auto_renew=True)
    expired = subscription.current_period_end + timedelta(seconds=1)
    value = overview_for(subscription, latest, uuid4(), expired, contract_offer=old)
    assert value.offers == [old]  # Expiry/failed payment alone cannot change the agreed price.
    canceled = overview_for(
        paid(), latest, uuid4(), NOW, contract_offer=old, new_contract_required=True
    )
    assert canceled.offers == [latest.entries[0].offer]
    assert canceled.paid_until == subscription.current_period_end


def test_manually_assigned_platinum_can_see_premium_acquisition_prices():
    offers = catalog()
    value = overview_for(
        paid(plan=SubscriptionPlan.PLATINUM), offers, uuid4(), NOW, new_contract_required=True
    )
    assert value.plan is SubscriptionPlan.PLATINUM
    assert value.offers == [offers.entries[0].offer]
    assert value.current_price is None  # Manual privileges are not proof of a paid contract.
