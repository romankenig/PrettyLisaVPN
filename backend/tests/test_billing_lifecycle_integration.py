"""Lifecycle settlement through the shipped provider, never a banking service."""

import asyncio
import os
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError
from test_billing_operations_integration import body, due, get, overview, post
from test_billing_sandbox_integration import settle
from test_billing_sandbox_integration import state as _sandbox_state
from test_subscription_access_integration import access_state as _access_state

from prettylisavpn.billing.model import BillingAccountRecord, SandboxMandateRecord
from prettylisavpn.billing.operations_domain import ProviderRequest, ProviderResult
from prettylisavpn.billing.sandbox import SandboxBillingProvider, simulated_result
from prettylisavpn.billing.worker import BillingWorker
from prettylisavpn.subscriptions.model import SubscriptionRecord

access_state = _access_state
state = _sandbox_state
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.getenv("RUN_INTEGRATION_TESTS") != "1", reason="Requires PostgreSQL"),
]


async def subscribe(state):
    operation_id = UUID((await post(state, await body(state))).json()["id"])
    await settle(state, operation_id)


async def projection(state):
    async with state[0].session() as session:
        account = await session.get(BillingAccountRecord, state[1])
        subscription = await session.scalar(
            select(SubscriptionRecord).where(SubscriptionRecord.user_id == state[1])
        )
        return {
            "contract": account.contract_id,
            "mandate": account.mandate_reference,
            "start": subscription.current_period_start,
            "end": subscription.current_period_end,
            "plan": subscription.plan,
            "status": subscription.status,
            "auto_renew": subscription.auto_renew,
            "updated": subscription.updated_at,
        }


async def authorities(state):
    async with state[0].session() as session:
        rows = await session.scalars(
            select(SandboxMandateRecord).where(SandboxMandateRecord.user_id == state[1])
        )
        return {row.reference: row.status for row in rows}


@pytest.mark.parametrize(
    "paid_until,expected",
    [("2099-01-31", "2099-02-28"), ("2104-01-31", "2104-02-29"), ("2099-12-31", "2100-01-31")],
)
async def test_parallel_renewal_applies_exactly_one_calendar_month_without_rebinding(
    state, paid_until, expected
):
    await subscribe(state)
    async with state[0].session() as session, session.begin():
        await session.execute(
            update(SubscriptionRecord)
            .where(SubscriptionRecord.user_id == state[1])
            .values(
                current_period_end=datetime.fromisoformat(paid_until).replace(tzinfo=UTC),
                updated_at=datetime.now(UTC),
            )
        )
    before, view = await projection(state), await overview(state)
    command = await body(state, "RENEW")
    responses = await asyncio.gather(*(post(state, command) for _ in range(6)))
    assert all(response.status_code == 200 for response in responses)
    ids = {response.json()["id"] for response in responses}
    assert len(ids) == 1 and await projection(state) == before
    operation_id, event_id = UUID(ids.pop()), uuid4()
    await asyncio.gather(*(state[4].notify(operation_id, event_id, "SUCCEEDED") for _ in range(3)))
    await asyncio.gather(
        *(BillingWorker(state[0], state[4]).process(operation_id) for _ in range(3))
    )
    after = await projection(state)
    assert after["end"] == datetime.fromisoformat(expected).replace(tzinfo=UTC)
    assert after["start"] == before["start"] and after["contract"] == before["contract"]
    assert after["mandate"] == before["mandate"] and after["auto_renew"]
    assert await authorities(state) == {before["mandate"]: "ACTIVE"}
    assert (await overview(state))["current_price"] == view["current_price"]
    await settle(state, operation_id, event_id=event_id)
    assert (await post(state, command)).json()["status"] == "SUCCEEDED"
    assert await projection(state) == after


async def test_change_method_and_cancel_preserve_paid_dates_and_revoke_only_the_old_authority(
    state,
):
    await subscribe(state)
    before = await projection(state)
    command = await body(state, "CHANGE_METHOD")
    operation_id = UUID((await post(state, command)).json()["id"])
    assert await projection(state) == before
    await state[4].notify(operation_id, uuid4(), "SUCCEEDED")
    # Provider result commits before local projection, so the old UI state remains until settlement.
    assert await projection(state) == before
    assert await authorities(state) == {
        before["mandate"]: "REVOKED",
        "sandbox-" + str(operation_id): "ACTIVE",
    }
    assert (await get(state, operation_id)).json()["status"] == "SUCCEEDED"
    changed = await projection(state)
    for field in ("start", "end", "plan", "contract", "auto_renew"):
        assert changed[field] == before[field]
    assert changed["mandate"] != before["mandate"]
    await settle(state, operation_id)
    assert (await post(state, command)).json()["status"] == "SUCCEEDED"
    assert await projection(state) == changed
    cancel = UUID((await post(state, await body(state, "CANCEL"))).json()["id"])
    await settle(state, cancel)
    canceled = await projection(state)
    assert canceled["start"] == before["start"] and canceled["end"] == before["end"]
    assert not canceled["auto_renew"] and canceled["mandate"] is None
    assert set((await authorities(state)).values()) == {"REVOKED"}
    me = await state[5].get("/me", headers={"Authorization": "Bearer " + state[2]})
    assert me.status_code == 200 and me.json()["plan"] == "PREMIUM"
    # Explicit later replacement may enable recurring again; an old CANCEL cannot revoke it.
    new_method = UUID((await post(state, await body(state, "CHANGE_METHOD"))).json()["id"])
    await settle(state, new_method)
    latest = await projection(state)
    await settle(state, cancel)
    await settle(state, operation_id)
    assert await projection(state) == latest and latest["auto_renew"]
    assert latest["end"] == before["end"]
    assert (await authorities(state))[latest["mandate"]] == "ACTIVE"


@pytest.mark.parametrize("action", ["RENEW", "CHANGE_METHOD", "CANCEL"])
@pytest.mark.parametrize("status", ["FAILED", "CANCELED"])
async def test_external_terminal_errors_do_not_mutate_paid_period_or_method(state, action, status):
    await subscribe(state)
    before, mandates = await projection(state), await authorities(state)
    command = await body(state, action)
    operation_id = UUID((await post(state, command)).json()["id"])
    await settle(state, operation_id, status)
    assert await projection(state) == before and await authorities(state) == mandates
    assert (await post(state, command)).json()["status"] == status
    assert (await overview(state))["pending_operation_id"] is None


@pytest.mark.parametrize("action", ["RENEW", "CHANGE_METHOD", "CANCEL"])
@pytest.mark.parametrize("failure", ["before_acceptance", "lost_response"])
async def test_unknown_external_outcome_keeps_old_projection_until_recovery(
    state, monkeypatch, action, failure
):
    await subscribe(state)
    before = await projection(state)
    original = SandboxBillingProvider.reconcile

    async def unavailable(self, request):
        if failure == "before_acceptance":
            raise OSError("Simulated provider outage")
        await original(self, request)
        raise TimeoutError("Simulated accepted request with lost response")

    with monkeypatch.context() as patch:
        patch.setattr(SandboxBillingProvider, "reconcile", unavailable)
        command = await body(state, action)
        response = await post(state, command)
    assert response.status_code == 200 and response.json()["status"] == "PENDING"
    operation_id = UUID(response.json()["id"])
    assert await projection(state) == before
    await due(state[0], operation_id)
    assert (await get(state, operation_id)).json()["status"] == "PENDING"
    assert await authorities(state) == {before["mandate"]: "ACTIVE"}
    await settle(state, operation_id)
    result = await projection(state)
    assert (await post(state, command)).json()["status"] == "SUCCEEDED"
    assert await projection(state) == result


@pytest.mark.parametrize("action", ["RENEW", "CHANGE_METHOD", "CANCEL"])
async def test_confirmed_external_mutation_survives_local_rollback(state, monkeypatch, action):
    await subscribe(state)
    before = await projection(state)
    operation_id = UUID((await post(state, await body(state, action))).json()["id"])
    await state[4].notify(operation_id, uuid4(), "SUCCEEDED")
    external = await authorities(state)
    original = BillingWorker._apply

    async def fail_after_apply(self, *args):
        await original(self, *args)
        raise SQLAlchemyError("Simulated local transaction failure")

    with monkeypatch.context() as patch:
        patch.setattr(BillingWorker, "_apply", fail_after_apply)
        assert (await get(state, operation_id)).json()["status"] == "PENDING"
    assert await projection(state) == before and await authorities(state) == external
    await due(state[0], operation_id)
    recovered = SandboxBillingProvider(state[0], state[6])
    await BillingWorker(state[0], recovered).run_once()
    assert (await get(state, operation_id)).json()["status"] == "SUCCEEDED"
    after = await projection(state)
    await settle(state, operation_id)
    assert await projection(state) == after and await authorities(state) == external


@pytest.mark.parametrize("action", ["RENEW", "CHANGE_METHOD", "CANCEL"])
async def test_inconsistent_failure_receipt_stays_pending_until_authoritative_recovery(
    state, monkeypatch, action
):
    await subscribe(state)
    before = await projection(state)
    original = SandboxBillingProvider.reconcile

    async def partial_failure(self, request):
        await original(self, request)
        return ProviderResult(
            operation_id=request.operation_id, status="FAILED", previous_mandate_revoked=True
        )

    with monkeypatch.context() as patch:
        patch.setattr(SandboxBillingProvider, "reconcile", partial_failure)
        operation_id = UUID((await post(state, await body(state, action))).json()["id"])
    assert (await get(state, operation_id)).json()["status"] == "PENDING"
    assert await projection(state) == before
    assert (await overview(state))["pending_operation_id"] == str(operation_id)
    await settle(state, operation_id)
    assert (await get(state, operation_id)).json()["status"] == "SUCCEEDED"


@pytest.mark.parametrize("invalid", ["unknown", "foreign", "revoked"])
async def test_sandbox_does_not_acknowledge_unknown_foreign_or_revoked_authority(state, invalid):
    await subscribe(state)
    before = await projection(state)
    reference = before["mandate"]
    if invalid == "revoked":
        async with state[0].session() as session, session.begin():
            await session.execute(
                update(SandboxMandateRecord)
                .where(SandboxMandateRecord.reference == reference)
                .values(status="REVOKED")
            )
    request = ProviderRequest(
        operation_id=uuid4(),
        account_id=uuid4() if invalid == "foreign" else state[1],
        action="CHANGE_METHOD",
        payment_route=None,
        amount_minor=None,
        currency="RUB",
        previous_mandate_reference="missing" if invalid == "unknown" else reference,
    )
    with pytest.raises(ValueError, match="unknown, foreign or revoked"):
        async with state[0].session() as session, session.begin():
            await SandboxBillingProvider._apply_mandate(
                session, request, simulated_result(request, "SUCCEEDED")
            )
    assert await projection(state) == before
