"""Real HTTP admission and sandbox receipts for all four currency matrices."""

import os
from uuid import UUID

import pytest
from test_billing_operations_integration import body, overview, post
from test_billing_sandbox_integration import settle
from test_billing_sandbox_integration import state as _sandbox_state
from test_subscription_access_integration import access_state as _access_state

from prettylisavpn.billing.domain import RouteCapability
from prettylisavpn.main import create_app
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock

access_state = _access_state
state = _sandbox_state
pytestmark = [pytest.mark.integration, pytest.mark.skipif(os.getenv("RUN_INTEGRATION_TESTS") != "1", reason="Requires PostgreSQL")]


@pytest.mark.parametrize("route,currency,available,recurring", [
    ("MIR", "RUB", True, True), ("MIR", "USD", False, False),
    ("BANK_CARD", "RUB", True, True), ("BANK_CARD", "USD", True, True),
    ("ALIPAY_WECHAT", "RUB", False, False), ("ALIPAY_WECHAT", "USD", True, False),
    ("CRYPTO", "RUB", False, False), ("CRYPTO", "USD", True, False),
])
async def test_route_currency_admission_matches_metadata_and_recurring_receipt(
    state, route, currency, available, recurring
):
    view = await overview(state)
    assert view["provider_mode"] == "SANDBOX"
    cap = next(cap for cap in view["payment_routes"] if cap["id"] == route)
    assert (currency in cap["currencies"]) == available
    assert (currency in cap["recurring_currencies"]) == recurring
    command = await body(state, payment_route=route, currency=currency)
    result = await post(state, command)
    if not available:
        assert result.status_code == 409
        return
    assert result.status_code == 200
    operation_id = UUID(result.json()["id"])
    await settle(state, operation_id)
    paid = await overview(state)
    assert paid["auto_renew"] == recurring
    assert (paid["payment_method"] is not None) == recurring
    assert paid["current_price"]["currency"] == currency
    assert all(currency == code for cap in paid["payment_routes"] for code in cap["currencies"])


async def test_capability_change_changes_revision_and_rejects_stale_consent(state):
    command = await body(state)
    state[4].capabilities = (RouteCapability(id="BANK_CARD", currencies=("USD",)),)
    response = await post(state, command)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "BILLING_REVISION_CHANGED"
    view = await overview(state)
    assert len(view["payment_routes"]) == 4
    assert view["payment_routes"][0]["currencies"] == []


async def test_accepted_recurring_capability_survives_provider_profile_change(state):
    operation_id = UUID((await post(state, await body(state))).json()["id"])
    state[4].capabilities = ()
    await settle(state, operation_id)
    assert (await overview(state))["auto_renew"]


async def test_one_time_card_profile_never_invents_recurring_or_method_binding(state):
    state[4].capabilities = (RouteCapability(id="BANK_CARD", currencies=("USD",)),)
    operation_id = UUID((await post(state, await body(state, payment_route="BANK_CARD", currency="USD"))).json()["id"])
    await settle(state, operation_id)
    paid = await overview(state)
    assert not paid["auto_renew"] and paid["payment_method"] is None
    assert "CHANGE_METHOD" not in paid["actions"]


async def test_disabled_runtime_never_advertises_payment_actions_and_reads_saved_status(state):
    operation_id = UUID((await post(state, await body(state))).json()["id"])
    config = state[6].model_copy(update={"billing_provider": "disabled"})
    app = create_app(config, postgres=state[0], valkey=AsyncMock(), product_events=AsyncMock(), support_worker=AsyncMock())
    headers = {"Authorization": "Bearer " + state[2]}
    async with app.router.lifespan_context(app), AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        view = (await client.get("/billing/overview", headers=headers)).json()
        assert view["provider_mode"] == "DISABLED" and view["actions"] == []
        assert len(view["payment_routes"]) == 4
        assert all(cap["currencies"] == cap["recurring_currencies"] == [] for cap in view["payment_routes"])
        assert (await client.get(f"/billing/operations/{operation_id}", headers=headers)).status_code == 200
        assert (await client.post("/billing/operations", headers=headers, json=await body(state))).status_code == 503
