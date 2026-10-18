"""Real PostgreSQL/JWT HTTP admission with a simulated external idempotent provider."""

import asyncio
import os
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.exc import SQLAlchemyError, DBAPIError
from test_subscription_access_integration import access_state as _access_state
from test_vpn_sessions_integration import create_dependencies, clean_up
from billing_fake import TestBillingProvider

from prettylisavpn.auth.tokens import AccessTokenService
from prettylisavpn.auth_sessions.repository import AuthSessionRepository
from prettylisavpn.auth_sessions.service import AuthSessionService
from prettylisavpn.billing.catalog import publish_catalog
from prettylisavpn.billing.domain import Catalog
from prettylisavpn.billing.model import BillingOperationRecord, BillingCatalogRecord, BillingContractRecord, BillingAccountRecord
from prettylisavpn.billing.operations import BillingOperationsService
from prettylisavpn.billing.operations_domain import BillingCommand
from prettylisavpn.billing.worker import BillingWorker
from prettylisavpn.devices.domain import DevicePlatform
from prettylisavpn.devices.repository import DeviceRepository
from prettylisavpn.devices.service import DeviceService
from prettylisavpn.main import create_app
from prettylisavpn.subscriptions.model import SubscriptionRecord

access_state = _access_state
pytestmark = [pytest.mark.integration, pytest.mark.skipif(os.getenv("RUN_INTEGRATION_TESTS") != "1", reason="Requires PostgreSQL")]


@pytest.fixture
async def state(access_state):
    config, pg, user, _, _, token, auth, _ = access_state
    provider = TestBillingProvider()
    app = create_app(config, postgres=pg, valkey=AsyncMock(), product_events=AsyncMock(), support_worker=AsyncMock(), billing_provider=provider, billing_worker=AsyncMock())
    async with app.router.lifespan_context(app), AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield pg, user, token, auth, provider, client, config


async def overview(state, token=None):
    response = await state[5].get("/billing/overview", headers={"Authorization":"Bearer " + (token or state[2])})
    assert response.status_code == 200, response.text
    return response.json()


async def body(state, action="SUBSCRIBE", **updates):
    view = await overview(state)
    return {"request_id": str(uuid4()), "expected_revision": view["revision"], "action":action,
        "offer_id": view["offers"][0]["id"] if action in ("SUBSCRIBE","RENEW") else None,
        "payment_route": "MIR" if action in ("SUBSCRIBE","RENEW") else None, "currency":"RUB", **updates}


async def post(state, data, token=None):
    return await state[5].post("/billing/operations", json=data, headers={"Authorization":"Bearer " + (token or state[2])})


async def due(pg, operation_id, *, expire_lease=False):
    async with pg.session() as session, session.begin():
        fields = {"next_attempt_at": datetime.now(UTC)-timedelta(seconds=1)}
        if expire_lease:
            fields["lease_until"] = datetime.now(UTC)-timedelta(seconds=1)
        await session.execute(update(BillingOperationRecord).where(BillingOperationRecord.id == operation_id).values(**fields))


async def get(state, operation_id, token=None):
    return await state[5].get(f"/billing/operations/{operation_id}", headers={"Authorization":"Bearer " + (token or state[2])})


async def test_saved_idempotency_parallel_retry_cross_device_restart_and_terminal_replay(state):
    pg, user, token, auth, provider, client, config = state
    data = await body(state)
    responses = await asyncio.gather(*(post(state,data) for _ in range(8)))
    assert all(r.status_code == 200 for r in responses)
    ids = {r.json()["id"] for r in responses}
    assert len(ids) == len(provider.ledger) == 1
    operation_id = UUID(ids.pop())
    async with pg.session() as session, session.begin():
        device = await DeviceService(DeviceRepository(session)).register(user,uuid4(),DevicePlatform.ANDROID,"Billing recovery")
        issued = await AuthSessionService(AuthSessionRepository(session),timedelta(days=1)).issue(user,device.id)
    second = AccessTokenService(config).issue(user,device.id,issued.session.id).token
    recovered = await overview(state,second)
    assert recovered["pending_operation_id"] == str(operation_id) and recovered["actions"] == []
    assert recovered["revision"] == (await overview(state))["revision"]
    changed = await post(state,{**data,"currency":"USD"})
    assert changed.status_code == 409 and changed.json()["error"]["code"] == "BILLING_IDEMPOTENCY_CONFLICT"
    assert (await post(state,{**data,"request_id":str(uuid4())})).status_code == 409
    provider.complete(operation_id)
    await due(pg,operation_id)
    # A different service/worker instance recovers from PostgreSQL and the external ledger.
    restarted_provider = TestBillingProvider(provider.ledger)
    restarted = BillingOperationsService(pg,auth,restarted_provider)
    result = await restarted.get(second,operation_id)
    assert result.status == "SUCCEEDED"
    paid = await overview(state)
    assert paid["plan"] == "PREMIUM" and paid["current_price"]["amount_minor"] == 19900
    assert paid["pending_operation_id"] is None
    end = paid["paid_until"]
    for _ in range(3):
        assert (await post(state,data)).json()["status"] == "SUCCEEDED"
    assert (await overview(state))["paid_until"] == end
    assert len(provider.ledger) == 1
    assert (await BillingOperationsService(pg,auth,None).start(token,BillingCommand.model_validate(data))).id == operation_id


async def test_different_request_ids_race_to_one_pending_operation(state):
    data = await body(state)
    results = await asyncio.gather(*(post(state,{**data,"request_id":str(uuid4())}) for _ in range(8)))
    assert sorted(r.status_code for r in results) == [200] + [409]*7
    assert len(state[4].ledger) == 1


async def test_price_revision_changed_before_admission_but_frozen_after_acceptance(state):
    pg, _, _, _, provider, _, _ = state
    data = await body(state)
    async with pg.session() as session:
        catalog = await session.get(BillingCatalogRecord,1)
        original, revision, timestamp = catalog.document, catalog.revision, catalog.updated_at
    import copy
    changed = copy.deepcopy(original)
    changed["entries"][0]["offer"]["prices"]["RUB"]["amount_minor"] += 100
    try:
        await publish_catalog(pg,Catalog.model_validate(changed),revision)
        stale = await post(state,data)
        assert stale.status_code == 409 and stale.json()["error"]["code"] == "BILLING_REVISION_CHANGED"
        assert provider.ledger == {}
        current = await body(state)
        accepted = await post(state,current)
        operation_id = UUID(accepted.json()["id"])
        await publish_catalog(pg,Catalog.model_validate(original))
        provider.complete(operation_id)
        await due(pg,operation_id)
        assert (await get(state,operation_id)).json()["status"] == "SUCCEEDED"
        assert (await overview(state))["current_price"]["amount_minor"] == 20000
    finally:
        async with pg.session() as session, session.begin():
            await session.execute(update(BillingCatalogRecord).where(BillingCatalogRecord.id==1).values(document=original,revision=revision,updated_at=timestamp))


async def test_provider_accepted_timeout_and_database_commit_failure_never_duplicate_payment(state,monkeypatch):
    pg, _, _, _, provider, _, _ = state
    provider.outcome = "SUCCEEDED"
    provider.fail_after_accept_once = True
    accepted = await post(state,await body(state))
    assert accepted.status_code == 200 and accepted.json()["status"] == "PENDING"
    operation_id = UUID(accepted.json()["id"])
    assert (await overview(state))["plan"] == "FREE"
    await due(pg,operation_id)
    original = BillingWorker._apply
    async def fail_after_apply(self,*args):
        await original(self,*args)
        raise SQLAlchemyError("Commit unavailable")
    with monkeypatch.context() as patch:
        patch.setattr(BillingWorker,"_apply",fail_after_apply)
        assert (await get(state,operation_id)).json()["status"] == "PENDING"
    assert (await overview(state))["plan"] == "FREE"
    await due(pg,operation_id)
    await BillingWorker(pg,provider).run_once()
    assert (await get(state,operation_id)).json()["status"] == "SUCCEEDED"
    assert len(provider.ledger) == 1 and set(provider.calls) == {operation_id}
    async with pg.session() as session:
        assert await session.scalar(select(func.count()).select_from(BillingContractRecord).where(BillingContractRecord.id==operation_id)) == 1


async def test_crash_lease_expiry_and_fencing_prevent_double_application(state):
    pg, _, token, auth, provider, _, _ = state
    provider.gate = asyncio.Event()
    task = asyncio.create_task(post(state,await body(state)))
    await provider.started.wait()
    async with pg.session() as session:
        operation_id = await session.scalar(select(BillingOperationRecord.id).where(BillingOperationRecord.user_id==state[1]))
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    # Simulated process death: no cleanup callback; another instance waits for the lease.
    assert not await BillingWorker(pg,provider).process(operation_id)
    provider.gate = None
    provider.outcome = "SUCCEEDED"
    await due(pg,operation_id,expire_lease=True)
    assert (await BillingOperationsService(pg,auth,provider).get(token,operation_id)).status == "SUCCEEDED"
    end = (await overview(state))["paid_until"]
    assert not await BillingWorker(pg,provider).process(operation_id)
    assert (await overview(state))["paid_until"] == end and len(provider.ledger) == 1


@pytest.mark.parametrize("outcome",["FAILED","CANCELED"])
async def test_only_authoritative_terminal_failures_release_account_and_do_not_grant_access(state,outcome):
    state[4].outcome = outcome
    data = await body(state)
    response = await post(state,data)
    assert response.json()["status"] == outcome
    assert (await overview(state))["plan"] == "FREE"
    assert (await overview(state))["pending_operation_id"] is None
    assert (await post(state,data)).json() == response.json()
    state[4].outcome = "PENDING"
    assert (await post(state,await body(state))).json()["status"] == "PENDING"


async def test_renew_change_method_cancel_keep_paid_period_and_prices(state):
    state[4].outcome = "SUCCEEDED"
    assert (await post(state,await body(state))).json()["status"] == "SUCCEEDED"
    first = await overview(state)
    assert {"RENEW","CHANGE_METHOD","CANCEL"} == set(first["actions"])
    assert (await post(state,await body(state,"RENEW",currency="USD"))).status_code == 409
    renew = await body(state,"RENEW")
    assert (await post(state,renew)).json()["status"] == "SUCCEEDED"
    after = await overview(state)
    assert after["paid_until"] > first["paid_until"] and after["current_price"] == first["current_price"]
    assert (await post(state,await body(state,"CHANGE_METHOD"))).json()["status"] == "SUCCEEDED"
    before_cancel = await overview(state)
    assert (await post(state,await body(state,"CANCEL"))).json()["status"] == "SUCCEEDED"
    canceled = await overview(state)
    assert canceled["plan"] == "PREMIUM" and canceled["status"] == "CANCELED"
    assert not canceled["auto_renew"] and canceled["payment_method"] is None
    assert canceled["paid_until"] == before_cancel["paid_until"]
    assert canceled["offers"] == first["offers"]


async def test_foreign_account_unknown_ids_auth_and_disabled_adapter(state):
    pg, _, _, _, provider, client, config = state
    response = await post(state,await body(state))
    operation_id = UUID(response.json()["id"])
    other, device, node = await create_dependencies(pg)
    try:
        async with pg.session() as session, session.begin():
            issued = await AuthSessionService(AuthSessionRepository(session),timedelta(days=1)).issue(other,device)
        token = AccessTokenService(config).issue(other,device,issued.session.id).token
        count = len(provider.calls)
        assert (await get(state,operation_id,token)).status_code == 404
        assert len(provider.calls) == count
        assert (await get(state,uuid4())).status_code == 404
        assert (await client.get(f"/billing/operations/{operation_id}")).status_code == 401
        assert (await client.post("/billing/operations",json=await body(state))).status_code == 401
        disabled = BillingOperationsService(pg,state[3],None)
        with pytest.raises(Exception) as error:
            await disabled.start(state[2],BillingCommand.model_validate(await body(state)))
        assert type(error.value).__name__ == "BillingDisabledError"
    finally:
        await clean_up(pg,other,node)


async def test_bad_receipt_and_unconfirmed_mandate_revocation_stay_pending(state):
    provider = state[4]
    provider.outcome = "SUCCEEDED"
    assert (await post(state,await body(state))).json()["status"] == "SUCCEEDED"
    before = await overview(state)
    provider.outcome = "PENDING"
    accepted = await post(state,await body(state,"CANCEL"))
    operation_id = UUID(accepted.json()["id"])
    provider.complete(operation_id)
    valid = provider.ledger[operation_id]
    provider.invalid = valid.model_copy(update={"previous_mandate_revoked":False})
    await due(state[0],operation_id)
    assert (await get(state,operation_id)).json()["status"] == "PENDING"
    assert (await overview(state))["auto_renew"]
    provider.invalid = valid.model_copy(update={"operation_id":uuid4()})
    await due(state[0],operation_id)
    assert (await get(state,operation_id)).json()["status"] == "PENDING"
    provider.invalid = valid.model_copy(update={"redirect_url":"https://evil.example/secret"})
    await due(state[0],operation_id)
    assert (await get(state,operation_id)).json()["status"] == "PENDING"
    provider.invalid = None
    await due(state[0],operation_id)
    assert (await get(state,operation_id)).json()["status"] == "SUCCEEDED"
    assert (await overview(state))["paid_until"] == before["paid_until"]


async def test_manual_subscription_change_is_not_overwritten_by_late_provider_confirmation(state):
    accepted = await post(state,await body(state))
    operation_id = UUID(accepted.json()["id"])
    async with state[0].session() as session, session.begin():
        await session.execute(update(SubscriptionRecord).where(SubscriptionRecord.user_id==state[1]).values(updated_at=datetime.now(UTC)))
    state[4].complete(operation_id)
    await due(state[0],operation_id)
    assert (await get(state,operation_id)).json()["status"] == "PENDING"
    assert (await overview(state))["plan"] == "FREE"
    async with state[0].session() as session:
        row = await session.get(BillingOperationRecord,operation_id)
        assert row.last_error == "SUBSCRIPTION_CHANGED"
    assert len(state[4].ledger) == 1


async def test_expired_claim_is_fenced_when_old_worker_returns_after_new_worker_settles(state):
    pg, _, _, _, provider, _, _ = state
    first_gate = asyncio.Event()
    provider.gate = first_gate
    task = asyncio.create_task(post(state,await body(state)))
    await provider.started.wait()
    async with pg.session() as session:
        operation_id = await session.scalar(select(BillingOperationRecord.id).where(BillingOperationRecord.user_id==state[1]))
    provider.gate = None
    provider.outcome = "SUCCEEDED"
    await due(pg,operation_id,expire_lease=True)
    assert await BillingWorker(pg,provider).process(operation_id)
    settled = await overview(state)
    first_gate.set()
    assert (await task).json()["status"] == "SUCCEEDED"
    assert (await overview(state))["paid_until"] == settled["paid_until"]
    assert len(provider.ledger) == 1


async def test_quote_and_terminal_results_are_immutable_at_database_boundary(state):
    state[4].outcome = "SUCCEEDED"
    response = await post(state,await body(state))
    operation_id = UUID(response.json()["id"])
    for fields in [{"quote":{}}, {"status":"PENDING"}]:
        with pytest.raises(DBAPIError):
            async with state[0].session() as session, session.begin():
                await session.execute(update(BillingOperationRecord).where(BillingOperationRecord.id==operation_id).values(**fields))
    with pytest.raises(DBAPIError):
        async with state[0].session() as session, session.begin():
            await session.execute(update(BillingContractRecord).where(BillingContractRecord.id==operation_id).values(amount_minor=1))


async def test_unsupported_route_currency_pair_is_rejected_before_provider_io(state):
    state[4].unsupported.add(("MIR","USD"))
    response = await post(state,await body(state,currency="USD"))
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "BILLING_ROUTE_UNAVAILABLE"
    assert state[4].ledger == {}
