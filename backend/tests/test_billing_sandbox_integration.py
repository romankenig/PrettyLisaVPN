"""HTTP + real PostgreSQL + shipped sandbox adapter, including process recovery."""

import asyncio
import os
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.exc import SQLAlchemyError
from test_billing_operations_integration import body, due, get, overview, post
from test_subscription_access_integration import access_state as _access_state

from prettylisavpn.billing.model import (
    BillingContractRecord,
    BillingOperationRecord,
    SandboxNotificationRecord,
    SandboxPaymentRecord,
)
from prettylisavpn.billing.operations_domain import ProviderRequest
from prettylisavpn.billing.sandbox import SandboxBillingProvider
from prettylisavpn.billing.worker import BillingWorker
from prettylisavpn.connections import Postgres
from prettylisavpn.main import create_app

access_state = _access_state
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.getenv("RUN_INTEGRATION_TESTS") != "1", reason="Requires PostgreSQL"),
]


@pytest.fixture
async def state(access_state):
    config, pg, user, _, _, token, auth, _ = access_state
    config = config.model_copy(update={"billing_provider": "sandbox"})
    app = create_app(
        config,
        postgres=pg,
        valkey=AsyncMock(),
        product_events=AsyncMock(),
        support_worker=AsyncMock(),
        billing_worker=AsyncMock(),
    )
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        provider = app.state.billing_operations.provider
        assert isinstance(provider, SandboxBillingProvider)
        yield pg, user, token, auth, provider, client, config


async def settle(state, operation_id, status="SUCCEEDED", event_id=None):
    await state[4].notify(operation_id, event_id or uuid4(), status)
    result = await get(state, operation_id)
    assert result.status_code == 200 and result.json()["status"] == status
    return result.json()


async def test_subscription_delayed_confirmation_and_duplicate_notifications(state):
    data = await body(state)
    responses = await asyncio.gather(*(post(state, data) for _ in range(6)))
    assert all(response.status_code == 200 for response in responses)
    ids = {response.json()["id"] for response in responses}
    assert len(ids) == 1
    operation_id = UUID(ids.pop())
    assert (await overview(state))["plan"] == "FREE"
    assert (await get(state, operation_id)).json()["status"] == "PENDING"
    event_id = uuid4()
    await asyncio.gather(*(state[4].notify(operation_id, event_id, "SUCCEEDED") for _ in range(6)))
    assert (await get(state, operation_id)).json()["status"] == "SUCCEEDED"
    paid = await overview(state)
    assert paid["plan"] == "PREMIUM" and paid["auto_renew"]
    for _ in range(3):
        await settle(state, operation_id, event_id=event_id)
        await settle(state, operation_id)
        assert (await post(state, data)).json()["status"] == "SUCCEEDED"
    assert (await overview(state))["paid_until"] == paid["paid_until"]
    async with state[0].session() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(SandboxPaymentRecord)
                .where(SandboxPaymentRecord.operation_id == operation_id)
            )
            == 1
        )
        assert await session.get(BillingContractRecord, operation_id) is not None
        assert await session.get(SandboxNotificationRecord, event_id) is not None


@pytest.mark.parametrize("status", ["FAILED", "CANCELED"])
async def test_decline_or_payment_cancellation_does_not_grant_subscription(state, status):
    data = await body(state)
    operation_id = UUID((await post(state, data)).json()["id"])
    await settle(state, operation_id, status)
    view = await overview(state)
    assert view["plan"] == "FREE" and view["pending_operation_id"] is None
    assert (await post(state, data)).json()["status"] == status
    with pytest.raises(ValueError, match="terminal"):
        await state[4].notify(operation_id, uuid4(), "SUCCEEDED")


async def test_renewal_and_subscription_cancellation_apply_once_and_preserve_paid_access(state):
    first = UUID((await post(state, await body(state))).json()["id"])
    await settle(state, first)
    paid = await overview(state)
    renew = UUID((await post(state, await body(state, "RENEW"))).json()["id"])
    await settle(state, renew)
    renewed = await overview(state)
    assert renewed["paid_until"] > paid["paid_until"]
    assert renewed["current_price"] == paid["current_price"]
    await settle(state, renew)
    assert (await overview(state))["paid_until"] == renewed["paid_until"]
    cancel = UUID((await post(state, await body(state, "CANCEL"))).json()["id"])
    assert (await overview(state))["auto_renew"]
    await settle(state, cancel)
    canceled = await overview(state)
    assert canceled["plan"] == "PREMIUM" and canceled["status"] == "CANCELED"
    assert not canceled["auto_renew"] and canceled["payment_method"] is None
    assert canceled["paid_until"] == renewed["paid_until"]
    await settle(state, cancel)
    assert (await overview(state))["paid_until"] == renewed["paid_until"]


async def test_receipt_survives_lost_response_and_new_connection_pools(state, monkeypatch):
    original = SandboxBillingProvider.reconcile

    async def lost_response(self, request):
        await original(self, request)
        raise TimeoutError("Simulated response lost after durable provider acceptance")

    with monkeypatch.context() as patch:
        patch.setattr(SandboxBillingProvider, "reconcile", lost_response)
        data = await body(state)
        response = await post(state, data)
    assert response.json()["status"] == "PENDING"
    operation_id = UUID(response.json()["id"])
    restarted_pg = Postgres(state[6])
    try:
        restarted = SandboxBillingProvider(restarted_pg, state[6])
        async with restarted_pg.session() as session:
            receipt = await session.get(SandboxPaymentRecord, operation_id)
            accepted = ProviderRequest.model_validate(receipt.request)
        assert (await restarted.reconcile(accepted)).status == "PENDING"
        # Receipt commits, then the notifying process dies before local settlement.
        await restarted.notify(operation_id, uuid4(), "SUCCEEDED")
    finally:
        await restarted_pg.close()
    recovered_pg = Postgres(state[6])
    try:
        recovered = SandboxBillingProvider(recovered_pg, state[6])
        assert (await recovered.reconcile(accepted)).status == "SUCCEEDED"
        await BillingWorker(recovered_pg, recovered).run_once()
        assert (await get(state, operation_id)).json()["status"] == "SUCCEEDED"
        end = (await overview(state))["paid_until"]
        await BillingWorker(recovered_pg, recovered).run_once()
        assert (await post(state, data)).json()["status"] == "SUCCEEDED"
        assert (await overview(state))["paid_until"] == end
    finally:
        await recovered_pg.close()


async def test_notification_cannot_steal_worker_lease_and_recovery_waits_for_expiry(state):
    operation_id = UUID((await post(state, await body(state))).json()["id"])
    claim = uuid4()
    async with state[0].session() as session, session.begin():
        await session.execute(
            update(BillingOperationRecord)
            .where(BillingOperationRecord.id == operation_id)
            .values(claim_token=claim, lease_until=datetime.now(UTC) + timedelta(minutes=1))
        )
    await state[4].notify(operation_id, uuid4(), "SUCCEEDED")
    worker = BillingWorker(state[0], state[4])
    assert not await worker.process(operation_id)
    assert (await get(state, operation_id)).json()["status"] == "PENDING"
    await due(state[0], operation_id, expire_lease=True)
    assert await worker.process(operation_id)
    assert (await get(state, operation_id)).json()["status"] == "SUCCEEDED"


async def test_provider_confirmation_survives_local_settlement_rollback(state, monkeypatch):
    operation_id = UUID((await post(state, await body(state))).json()["id"])
    await state[4].notify(operation_id, uuid4(), "SUCCEEDED")
    original = BillingWorker._apply

    async def fail_after_apply(self, *args):
        await original(self, *args)
        raise SQLAlchemyError("Simulated local commit failure")

    with monkeypatch.context() as patch:
        patch.setattr(BillingWorker, "_apply", fail_after_apply)
        assert (await get(state, operation_id)).json()["status"] == "PENDING"
    assert (await overview(state))["plan"] == "FREE"
    async with state[0].session() as session:
        saved = await session.get(SandboxPaymentRecord, operation_id)
        assert saved.result["status"] == "SUCCEEDED"
        assert await session.get(BillingContractRecord, operation_id) is None
    await due(state[0], operation_id)
    await BillingWorker(state[0], SandboxBillingProvider(state[0], state[6])).run_once()
    assert (await get(state, operation_id)).json()["status"] == "SUCCEEDED"


async def test_conflicting_events_are_atomic_and_original_request_is_pinned(state):
    operation_id = UUID((await post(state, await body(state))).json()["id"])
    provider = state[4]
    results = await asyncio.gather(
        provider.notify(operation_id, uuid4(), "SUCCEEDED"),
        provider.notify(operation_id, uuid4(), "FAILED"),
        return_exceptions=True,
    )
    assert sum(isinstance(result, ValueError) for result in results) == 1
    async with state[0].session() as session:
        receipt = await session.get(SandboxPaymentRecord, operation_id)
        accepted = ProviderRequest.model_validate(receipt.request)
        saved = receipt.result
        assert (
            await session.scalar(
                select(func.count())
                .select_from(SandboxNotificationRecord)
                .where(SandboxNotificationRecord.operation_id == operation_id)
            )
            == 1
        )
    with pytest.raises(ValueError, match="identity"):
        await provider.reconcile(accepted.model_copy(update={"amount_minor": 1}))
    assert (await provider.reconcile(accepted)).model_dump(mode="json") == saved


async def test_event_id_cannot_be_reused_for_another_operation_and_controls_are_not_public(state):
    event_id = uuid4()
    first = UUID((await post(state, await body(state))).json()["id"])
    await settle(state, first, "FAILED", event_id)
    second = UUID((await post(state, await body(state))).json()["id"])
    with pytest.raises(ValueError, match="notification identity"):
        await state[4].notify(second, event_id, "FAILED")
    assert (await get(state, second)).json()["status"] == "PENDING"
    with pytest.raises(ValueError, match="Unknown"):
        await state[4].notify(uuid4(), uuid4(), "SUCCEEDED")
    response = await state[5].post(
        "/billing/sandbox/notifications",
        json={"operation_id": str(second), "status": "SUCCEEDED"},
        headers={"Authorization": "Bearer " + state[2]},
    )
    assert response.status_code == 404
