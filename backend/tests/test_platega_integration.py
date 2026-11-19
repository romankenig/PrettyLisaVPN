"""Real DB/OTP-session ownership, simulated Platega; no real money or merchant secrets."""

import asyncio
import json
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy import select
from test_billing_operations_integration import due
from test_subscription_access_integration import access_state as _access_state

from prettylisavpn.billing.model import BillingAccountRecord, BillingContractRecord
from prettylisavpn.billing.operations import BillingOperationsService
from prettylisavpn.billing.operations_domain import BillingCommand, next_month
from prettylisavpn.billing.platega import PlategaBillingProvider
from prettylisavpn.billing.platega_api import (
    CreatedSubscription,
    PlategaPayment,
    PlategaSubscription,
    PlategaUnavailable,
    description_for,
    subscription_url,
)
from prettylisavpn.billing.platega_callbacks import InvalidPlategaCallback, PlategaCallbacks
from prettylisavpn.billing.platega_model import PlategaAgreementRecord, PlategaChargeRecord
from prettylisavpn.billing.service import BillingOverviewService
from prettylisavpn.subscriptions.model import SubscriptionRecord

access_state = _access_state
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.getenv("RUN_INTEGRATION_TESTS") != "1", reason="Requires PostgreSQL"),
]


class ProviderAPI:
    def __init__(self):
        self.subscriptions = {}
        self.payments = {}
        self.creates = 0
        self.lose_create_response = False
        self.cancel_gate = None
        self.cancel_started = asyncio.Event()

    async def create(self, operation_id, amount_minor, email):
        self.creates += 1
        identity = uuid4()
        self.subscriptions[identity] = PlategaSubscription(
            id=identity,
            status="PendingAgreement",
            amount_minor=amount_minor,
            currency="RUB",
            next_charge_at=None,
            last_charge_at=None,
            successful_charges=0,
            description=description_for(operation_id),
            created_at=datetime.now(UTC),
        )
        if self.lose_create_response:
            self.lose_create_response = False
            raise PlategaUnavailable
        return CreatedSubscription(id=identity, redirect=subscription_url(identity))

    async def subscription(self, identity):
        return self.subscriptions[identity]

    async def recover(self, operation_id, since):
        return [
            value
            for value in self.subscriptions.values()
            if value.description == description_for(operation_id)
        ]

    async def recover_payments(self, operation_id, since):
        return [
            payment
            for payment in self.payments.values()
            if payment.description == description_for(operation_id)
        ]

    async def payment(self, identity):
        return self.payments[identity]

    async def cancel(self, identity):
        self.cancel_started.set()
        if self.cancel_gate:
            await self.cancel_gate.wait()
        self.subscriptions[identity] = self.subscriptions[identity].model_copy(
            update={"status": "Cancelled", "next_charge_at": None}
        )


@pytest.fixture
async def state(access_state):
    _, pg, user, _, _, token, auth, _ = access_state
    api = ProviderAPI()
    provider = PlategaBillingProvider(pg, api)
    operations = BillingOperationsService(pg, auth, provider)
    overview = BillingOverviewService(pg, auth, provider)
    callbacks = PlategaCallbacks(pg, uuid4(), SecretStr("test-only-webhook-secret-32-characters"))
    return pg, user, token, api, provider, operations, overview, callbacks


async def command(state, action="SUBSCRIBE"):
    view = await state[6].overview(state[2])
    return BillingCommand(
        action=action,
        payment_route="SBP" if action == "SUBSCRIBE" else None,
        request_id=uuid4(),
        expected_revision=view.revision,
        offer_id=view.offers[0].id if action == "SUBSCRIBE" else None,
        currency="RUB",
    )


async def projection(state):
    async with state[0].session() as session:
        row = await session.scalar(
            select(SubscriptionRecord).where(SubscriptionRecord.user_id == state[1])
        )
        account = await session.get(BillingAccountRecord, state[1])
        return row.current_period_end, row.auto_renew, account.contract_id if account else None


async def notification(state, subscription_id, status="CONFIRMED", payment_id=None, amount=199):
    identity = payment_id or uuid4()
    await state[7].accept(
        json.dumps(
            {
                "id": str(identity),
                "subscriptionId": str(subscription_id),
                "amount": amount,
                "currency": "RUB",
                "status": status,
            }
        ).encode()
    )
    return identity


async def paid(state, operation_id):
    api = state[3]
    async with state[0].session() as session:
        binding = await session.get(PlategaAgreementRecord, operation_id)
        identity = binding.provider_id
    now = datetime.now(UTC)
    previous = api.subscriptions[identity]
    api.subscriptions[identity] = previous.model_copy(
        update={
            "status": "Active",
            "next_charge_at": next_month(now),
            "last_charge_at": now,
            "successful_charges": previous.successful_charges + 1,
        }
    )
    payment_id = uuid4()
    api.payments[payment_id] = PlategaPayment(
        id=payment_id, status="CONFIRMED", amount_minor=19900, currency="RUB"
    )
    await notification(state, identity, payment_id=payment_id)
    await state[4].verify_charge(payment_id)
    return payment_id, identity


async def subscribe(state):
    op = await state[5].start(state[2], await command(state))
    assert op.status == "PENDING" and op.redirect_url.startswith(
        "https://pay.platega.io/subscription/"
    )
    payment, identity = await paid(state, op.id)
    await due(state[0], op.id)
    assert (await state[5].get(state[2], op.id)).status == "SUCCEEDED"
    await state[4].apply_recurring(payment)
    return op.id, payment, identity


async def test_lost_create_response_recovers_same_subscription_without_second_create(state):
    state[3].lose_create_response = True
    original = await command(state)
    value = await state[5].start(state[2], original)
    assert value.status == "PENDING" and value.redirect_url is None
    await due(state[0], value.id)
    recovered = await state[5].get(state[2], value.id)
    assert recovered.redirect_url == subscription_url(next(iter(state[3].subscriptions)))
    assert state[3].creates == 1
    assert (await state[5].start(state[2], original)).id == value.id


async def test_missed_callback_recovers_from_bound_provider_ledger_without_new_charge(state):
    value = await state[5].start(state[2], await command(state))
    identity = next(iter(state[3].subscriptions))
    authority = state[3].subscriptions[identity]
    state[3].subscriptions[identity] = authority.model_copy(
        update={
            "status": "Active",
            "successful_charges": 1,
            "next_charge_at": next_month(datetime.now(UTC)),
        }
    )
    payment = uuid4()
    state[3].payments[payment] = PlategaPayment(
        id=payment,
        status="CONFIRMED",
        amount_minor=19900,
        currency="RUB",
        description=description_for(value.id),
    )
    await state[4].refresh_agreement(value.id)
    await state[4].run_once()
    await due(state[0], value.id)
    assert (await state[5].get(state[2], value.id)).status == "SUCCEEDED"
    await state[4].run_once()
    before = await projection(state)
    await state[4].refresh_agreement(value.id)
    await state[4].run_once()
    assert await projection(state) == before
    assert before[0] is not None and state[3].creates == 1


async def test_activation_and_return_url_never_grant_premium_without_verified_payment(state):
    value = await state[5].start(state[2], await command(state))
    identity = next(iter(state[3].subscriptions))
    state[3].subscriptions[identity] = (
        state[3].subscriptions[identity].model_copy(update={"status": "Active"})
    )
    await notification(state, identity, "SUBSCRIPTION_ACTIVATED", identity)
    await due(state[0], value.id)
    assert (await state[5].get(state[2], value.id)).status == "PENDING"
    assert (await state[6].overview(state[2])).plan.value == "FREE"
    payment_id = uuid4()
    state[3].payments[payment_id] = PlategaPayment(
        id=payment_id, status="CONFIRMED", amount_minor=100, currency="RUB"
    )
    await notification(state, identity, payment_id=payment_id)
    with pytest.raises(PlategaUnavailable):
        await state[4].verify_charge(payment_id)
    assert (await state[6].overview(state[2])).plan.value == "FREE"


async def test_pending_receipt_is_rechecked_without_another_callback(state):
    value = await state[5].start(state[2], await command(state))
    identity = next(iter(state[3].subscriptions))
    payment_id = uuid4()
    state[3].payments[payment_id] = PlategaPayment(
        id=payment_id, status="PENDING", amount_minor=19900, currency="RUB"
    )
    await notification(state, identity, payment_id=payment_id)
    await state[4].run_once()
    assert (await state[6].overview(state[2])).plan.value == "FREE"
    async with state[0].session() as session, session.begin():
        receipt = await session.get(PlategaChargeRecord, payment_id)
        assert receipt.status == "PENDING" and receipt.verified_at
        receipt.verified_at = datetime.now(UTC) - timedelta(minutes=2)
    state[3].payments[payment_id] = (
        state[3].payments[payment_id].model_copy(update={"status": "CONFIRMED"})
    )
    state[3].subscriptions[identity] = (
        state[3]
        .subscriptions[identity]
        .model_copy(update={"status": "Active", "successful_charges": 1})
    )
    await state[4].run_once()
    await due(state[0], value.id)
    assert (await state[5].get(state[2], value.id)).status == "SUCCEEDED"
    assert state[3].creates == 1


async def test_each_recurring_charge_extends_once_without_repricing_contract(state):
    operation, first, identity = await subscribe(state)
    before = await projection(state)
    second, _ = await paid(state, operation)
    await asyncio.gather(*(state[4].apply_recurring(second) for _ in range(4)))
    after = await projection(state)
    assert after[0] == next_month(before[0]) and after[2] == before[2]
    await notification(state, identity, payment_id=first)
    await notification(state, identity, payment_id=second)
    await state[4].run_once()
    assert await projection(state) == after
    async with state[0].session() as session:
        contract = await session.get(BillingContractRecord, after[2])
        assert contract.amount_minor == 19900
        assert (await session.get(PlategaChargeRecord, first)).applied_at
        assert (await session.get(PlategaChargeRecord, second)).applied_at


async def test_cancel_keeps_paid_access_and_requires_fresh_purchase(state):
    _, _, identity = await subscribe(state)
    before = await projection(state)
    canceled = await state[5].start(state[2], await command(state, "CANCEL"))
    assert canceled.status == "SUCCEEDED"
    view = await state[6].overview(state[2])
    assert view.paid_until == before[0] and view.plan.value == "PREMIUM"
    assert view.payment_method is None and view.next_charge_at is None
    assert view.new_contract_required and "SUBSCRIBE" in view.actions
    assert "RENEW" not in view.actions and "CHANGE_METHOD" not in view.actions
    assert state[3].subscriptions[identity].status == "Cancelled"


async def test_provider_side_cancel_is_confirmed_by_get_and_preserves_paid_period(state):
    operation, _, identity = await subscribe(state)
    before = await projection(state)
    await notification(state, identity, "SUBSCRIPTION_CANCELLED", identity)
    await state[4].refresh_agreement(operation)
    assert (await projection(state))[1]  # Claimed callback alone is insufficient.
    await state[3].cancel(identity)
    await state[4].refresh_agreement(operation)
    after = await projection(state)
    assert after[0] == before[0] and not after[1]
    assert (await state[6].overview(state[2])).new_contract_required


async def test_cancel_racing_with_a_paid_charge_retains_new_paid_deadline(state):
    operation, _, _ = await subscribe(state)
    before = await projection(state)
    state[3].cancel_gate = asyncio.Event()
    task = asyncio.create_task(state[5].start(state[2], await command(state, "CANCEL")))
    await state[3].cancel_started.wait()
    payment, _ = await paid(state, operation)
    await state[4].apply_recurring(payment)
    state[3].cancel_gate.set()
    assert (await task).status == "SUCCEEDED"
    after = await projection(state)
    assert after[0] == next_month(before[0]) and not after[1]


async def test_mismatched_callback_amount_never_reaches_entitlement_settlement(state):
    await state[5].start(state[2], await command(state))
    with pytest.raises(InvalidPlategaCallback):
        await notification(state, next(iter(state[3].subscriptions)), amount=1)
    assert (await state[6].overview(state[2])).plan.value == "FREE"


async def test_cancellation_waits_for_successful_charge_receipt_even_if_webhook_is_late(state):
    value = await state[5].start(state[2], await command(state))
    identity = next(iter(state[3].subscriptions))
    state[3].subscriptions[identity] = (
        state[3]
        .subscriptions[identity]
        .model_copy(update={"status": "Cancelled", "successful_charges": 1})
    )
    await due(state[0], value.id)
    assert (await state[5].get(state[2], value.id)).status == "PENDING"


async def test_refund_is_visible_for_operator_review_without_unproven_access_mutation(state):
    from prettylisavpn.billing.platega_audit import report

    _, payment, identity = await subscribe(state)
    before = await projection(state)
    state[3].payments[payment] = (
        state[3].payments[payment].model_copy(update={"status": "CHARGEBACKED"})
    )
    await notification(state, identity, status="CHARGEBACKED", payment_id=payment)
    await state[4].run_once()
    assert await projection(state) == before
    audit = await report(state[0])
    assert any(
        row["payment_id"] == str(payment) and row["status"] == "CHARGEBACKED"
        for row in audit["review_required"]
    )
    assert "@" not in json.dumps(audit)
