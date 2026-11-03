"""Real PostgreSQL inbox and HTTP delivery, with a mockable Cardlink status API."""

import asyncio
import os
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from test_cardlink import BILL, ORDER, TOKEN, bill, payload
from test_subscription_access_integration import access_state as _access_state

from prettylisavpn.billing.cardlink import CardlinkCallbacks
from prettylisavpn.billing.cardlink_store import PostgresCardlinkReceipts
from prettylisavpn.billing.model import (
    BillingOperationRecord,
    CardlinkBillRecord,
    CardlinkReceiptRecord,
)
from prettylisavpn.config import Settings
from prettylisavpn.main import create_app
from prettylisavpn.subscriptions.model import SubscriptionRecord

access_state = _access_state
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.getenv("RUN_INTEGRATION_TESTS") != "1", reason="Requires PostgreSQL"),
]


@pytest.fixture
async def inbox(access_state):
    _, pg, user, *_ = access_state
    api = AsyncMock()
    api.lookup.return_value = bill()
    handler = CardlinkCallbacks(TOKEN, api, PostgresCardlinkReceipts(pg))
    app = create_app(Settings(_env_file=None, environment="test"), cardlink_callbacks=handler)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield pg, user, api, client


async def seed(inbox, *, provider="cardlink", bound=True, action="SUBSCRIBE"):
    pg, user, *_ = inbox
    now = datetime.now(UTC)
    async with pg.session() as session, session.begin():
        session.add(
            BillingOperationRecord(
                id=ORDER,
                user_id=user,
                request_id=uuid4(),
                fingerprint="test-inbox",
                command={"action": action, "currency": "RUB"},
                quote={"amount_minor": 19900},
                provider_name=provider,
                status="PENDING",
                created_at=now,
                next_attempt_at=now,
            )
        )
        await session.flush()
        if bound:
            session.add(CardlinkBillRecord(operation_id=ORDER, bill_id=BILL))


async def post(inbox, **changes):
    return await inbox[3].post(
        "/api/payments/cardlink/callback",
        content=payload(**changes),
        headers={"content-type": "application/x-www-form-urlencoded"},
    )


async def test_concurrent_replays_are_durable_and_do_not_activate_subscription(inbox):
    await seed(inbox)
    pg, user, api, _ = inbox
    responses = await asyncio.gather(*(post(inbox) for _ in range(8)))
    assert all(response.status_code == 200 for response in responses)
    async with pg.session() as session:
        assert await session.scalar(select(func.count()).select_from(CardlinkReceiptRecord)) == 1
        receipt = await session.get(CardlinkReceiptRecord, (ORDER, "SUCCESS"))
        assert receipt is not None and receipt.verified_at.tzinfo is not None
        original_date = receipt.verified_at
        operation = await session.get(BillingOperationRecord, ORDER)
        assert operation.status == "PENDING"
        subscription = await session.scalar(
            select(SubscriptionRecord).where(SubscriptionRecord.user_id == user)
        )
        assert subscription.plan.value == "FREE"
        assert subscription.auto_renew is False
    # Late contradictory snapshots cannot erase successful evidence or apply a second period.
    api.lookup.return_value = bill(status="UNDERPAID")
    assert (await post(inbox, Status="SUCCESS")).status_code == 200
    api.lookup.return_value = bill()
    assert (await post(inbox)).status_code == 200
    async with pg.session() as session:
        assert (
            await session.get(CardlinkReceiptRecord, (ORDER, "SUCCESS"))
        ).verified_at == original_date
        assert await session.get(CardlinkReceiptRecord, (ORDER, "UNDERPAID")) is not None


@pytest.mark.parametrize(
    "options",
    [
        {"provider": "sandbox"},
        {"bound": False},
        {"action": "CANCEL"},
    ],
)
async def test_wrong_provider_unbound_bill_and_nonpayment_operation_are_rejected(inbox, options):
    await seed(inbox, **options)
    response = await post(inbox)
    assert response.status_code == 404
    inbox[2].lookup.assert_not_awaited()


async def test_unknown_order_and_swapped_bill_id_are_rejected(inbox):
    assert (await post(inbox)).status_code == 404
    await seed(inbox)
    # TrsId is not signed, so matching the server-owned binding is mandatory.
    assert (await post(inbox, TrsId="another-bill")).status_code == 404
    inbox[2].lookup.assert_not_awaited()
