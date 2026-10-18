"""Actual PostgreSQL/auth HTTP billing, group/date and contract-price boundaries."""

import asyncio
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select, update
from sqlalchemy.exc import DBAPIError
from test_subscription_access_integration import access_state as _access_state, set_paid

from prettylisavpn.auth.tokens import AccessTokenService
from prettylisavpn.auth_sessions.repository import AuthSessionRepository
from prettylisavpn.auth_sessions.service import AuthSessionService
from prettylisavpn.billing.catalog import CatalogConflictError, publish_catalog
from prettylisavpn.billing.domain import Catalog
from prettylisavpn.billing.model import (
    BillingCatalogRecord,
    ClientGroupMembershipRecord,
    ClientGroupRecord,
    SubscriptionPriceRecord,
)
from prettylisavpn.billing.pricing import PriceConfirmationError, lock_contract_price
from prettylisavpn.devices.domain import DevicePlatform
from prettylisavpn.devices.repository import DeviceRepository
from prettylisavpn.devices.service import DeviceService
from prettylisavpn.main import create_app
from prettylisavpn.subscriptions.domain import SubscriptionPlan, SubscriptionStatus
from prettylisavpn.subscriptions.model import SubscriptionRecord

access_state = _access_state

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.getenv("RUN_INTEGRATION_TESTS") != "1", reason="Requires PostgreSQL"),
]


@pytest.fixture
async def billing_state(access_state):
    config, postgres, user_id, _, _, token, _, _ = access_state
    async with postgres.session() as session:
        row = await session.get(BillingCatalogRecord, 1)
        original = (row.document, row.revision, row.updated_at)
    app = create_app(
        config,
        postgres=postgres,
        valkey=AsyncMock(),
        product_events=AsyncMock(),
        support_worker=AsyncMock(),
    )
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        try:
            yield postgres, user_id, token, client, config
        finally:
            # Restore the disposable shared test catalogue, including its identity.
            async with postgres.session() as session, session.begin():
                await session.execute(
                    update(BillingCatalogRecord)
                    .where(BillingCatalogRecord.id == 1)
                    .values(document=original[0], revision=original[1], updated_at=original[2])
                )
                await session.execute(
                    delete(ClientGroupMembershipRecord).where(
                        ClientGroupMembershipRecord.user_id == user_id
                    )
                )
                await session.execute(
                    delete(ClientGroupRecord).where(ClientGroupRecord.name == str(user_id))
                )


async def overview(client, token):
    response = await client.get("/billing/overview", headers={"Authorization": "Bearer " + token})
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["vary"] == "Authorization"
    body = response.json()
    assert body["actions"] == [] and body["payment_operations_available"] is False
    assert body["pending_operation_id"] is body["payment_method"] is None
    return body


async def test_auth_account_scope_cross_device_and_no_payment_side_effects(billing_state):
    postgres, user_id, token, client, config = billing_state
    assert (await client.get("/billing/overview")).status_code == 401
    assert (
        await client.get("/billing/overview", headers={"Authorization": "Bearer invalid"})
    ).status_code == 401
    first = await overview(client, token)
    assert first["plan"] == first["status"] == "FREE"
    assert first["current_price"] is None
    async with postgres.session() as session, session.begin():
        device = await DeviceService(DeviceRepository(session)).register(
            user_id, uuid4(), DevicePlatform.ANDROID, "Billing second device"
        )
        auth = await AuthSessionService(AuthSessionRepository(session), timedelta(days=1)).issue(
            user_id, device.id
        )
    second_token = AccessTokenService(config).issue(user_id, device.id, auth.session.id).token
    assert await overview(client, second_token) == first
    # Untrusted query parameters cannot choose another group, user, date or price.
    response = await client.get(
        f"/billing/overview?user_id={uuid4()}&group_id={uuid4()}&at=2099-01-01",
        headers={"Authorization": "Bearer " + token},
    )
    assert response.json() == first
    assert (
        await client.post(
            "/billing/operations",
            json={"action": "SUBSCRIBE"},
            headers={"Authorization": "Bearer " + token},
        )
    ).status_code == 404
    assert (
        await client.get(
            f"/billing/operations/{uuid4()}", headers={"Authorization": "Bearer " + token}
        )
    ).status_code == 404
    assert await overview(client, token) == first
    # A newly constructed application uses PostgreSQL, not process-local fixtures/cache.
    restarted = create_app(
        config,
        postgres=postgres,
        valkey=AsyncMock(),
        product_events=AsyncMock(),
        support_worker=AsyncMock(),
    )
    async with (
        restarted.router.lifespan_context(restarted),
        AsyncClient(transport=ASGITransport(app=restarted), base_url="http://test") as another,
    ):
        assert await overview(another, token) == first


async def test_publication_cas_concurrency_group_filter_and_no_fallback(billing_state):
    postgres, user_id, token, client, _ = billing_state
    original = await overview(client, token)
    group_id = uuid4()
    async with postgres.session() as session, session.begin():
        await session.merge(ClientGroupRecord(id=group_id, name=str(user_id)))
        session.add(ClientGroupMembershipRecord(user_id=user_id, group_id=group_id))
    no_offer = await overview(client, token)
    assert no_offer["offers"] == [] and no_offer["revision"] != original["revision"]
    async with postgres.session() as session:
        row = await session.get(BillingCatalogRecord, 1)
        document, expected = row.document, row.revision
    document["entries"][0]["group_id"] = str(group_id)
    document["entries"][0]["offer"]["prices"]["RUB"]["amount_minor"] = 12345
    updated = Catalog.model_validate(document)
    revisions = await asyncio.gather(
        *(publish_catalog(postgres, updated, expected) for _ in range(2)), return_exceptions=True
    )
    assert sum(isinstance(result, CatalogConflictError) for result in revisions) == 1
    new_revision = next(result for result in revisions if not isinstance(result, BaseException))
    assert await publish_catalog(postgres, updated, new_revision) == new_revision
    current = await overview(client, token)
    assert current["offers"][0]["prices"]["RUB"]["amount_minor"] == 12345
    assert current["revision"] != no_offer["revision"]
    document["entries"][0]["group_id"] = str(uuid4())
    with pytest.raises(ValueError, match="Unknown client group"):
        await publish_catalog(postgres, Catalog.model_validate(document))
    assert await overview(client, token) == current
    document["entries"][0]["group_id"] = str(group_id)
    document["entries"][0]["valid_from"] = "2099-01-01T00:00:00Z"
    await publish_catalog(postgres, Catalog.model_validate(document), new_revision)
    assert (await overview(client, token))["offers"] == []


async def test_confirmed_price_survives_catalog_group_changes_cancel_expiry_and_cannot_be_updated(
    billing_state,
):
    postgres, user_id, token, client, _ = billing_state
    await set_paid(postgres, user_id, datetime.now(UTC) + timedelta(days=20), auto_renew=True)
    legacy = await overview(client, token)
    assert legacy["current_price"] is None and legacy["auto_renew"]
    assert legacy["offers"] == []
    async with postgres.session() as session, session.begin():
        catalog = await session.get(BillingCatalogRecord, 1)
        subscription = await session.scalar(
            select(SubscriptionRecord).where(SubscriptionRecord.user_id == user_id)
        )
        offer_id = Catalog.model_validate(catalog.document).entries[0].offer.id
        subscription_id, revision = subscription.id, catalog.revision
        with pytest.raises(PriceConfirmationError):
            await lock_contract_price(
                session, subscription_id, uuid4(), "RUB", revision, datetime.now(UTC)
            )
        with pytest.raises(PriceConfirmationError):
            await lock_contract_price(
                session, subscription_id, offer_id, "RUB", uuid4(), datetime.now(UTC)
            )
        locked = await lock_contract_price(
            session, subscription_id, offer_id, "RUB", revision, datetime.now(UTC)
        )
        assert (
            await lock_contract_price(
                session, subscription_id, offer_id, "RUB", revision, datetime.now(UTC)
            )
            == locked
        )
    before = await overview(client, token)
    assert before["current_price"] == locked.model_dump()
    async with postgres.session() as session:
        row = await session.get(BillingCatalogRecord, 1)
        document = row.document
    document["entries"][0]["offer"]["prices"]["RUB"]["amount_minor"] += 100
    await publish_catalog(postgres, Catalog.model_validate(document), revision)
    changed = await overview(client, token)
    assert changed["revision"] != before["revision"]
    assert changed["current_price"] == before["current_price"]
    assert changed["offers"] == before["offers"]
    with pytest.raises(DBAPIError):
        async with postgres.session() as session, session.begin():
            await session.execute(
                update(SubscriptionPriceRecord)
                .where(SubscriptionPriceRecord.subscription_id == subscription_id)
                .values(amount_minor=999)
            )
    async with postgres.session() as session, session.begin():
        session.add(ClientGroupRecord(id=(group_id := uuid4()), name=str(user_id)))
        await session.flush()
        session.add(ClientGroupMembershipRecord(user_id=user_id, group_id=group_id))
    after_group = await overview(client, token)
    assert after_group["current_price"] == before["current_price"]
    assert after_group["offers"] == before["offers"]
    await set_paid(
        postgres, user_id, datetime.now(UTC) + timedelta(days=1), status=SubscriptionStatus.CANCELED
    )
    assert (await overview(client, token))["status"] == "CANCELED"
    await set_paid(
        postgres,
        user_id,
        datetime.now(UTC) - timedelta(seconds=1),
        status=SubscriptionStatus.CANCELED,
    )
    expired = await overview(client, token)
    assert expired["plan"] == "FREE" and expired["status"] == "EXPIRED"
    assert expired["current_price"] == before["current_price"]


async def test_record_billing_api_evidence(billing_state):
    postgres, user_id, token, client, _ = billing_state
    path = os.getenv("BILLING_BACKEND_EVIDENCE_PATH")
    if path:
        assert os.getenv("GITHUB_ACTIONS") == "true"
        assert "127.0.0.1" in postgres.engine.url.render_as_string(hide_password=True)
    snapshots = {"free": await overview(client, token)}
    await set_paid(postgres, user_id, datetime.now(UTC) + timedelta(days=20), auto_renew=True)
    snapshots["active-unknown"] = await overview(client, token)
    async with postgres.session() as session, session.begin():
        subscription = await session.scalar(
            select(SubscriptionRecord).where(SubscriptionRecord.user_id == user_id)
        )
        catalog = await session.get(BillingCatalogRecord, 1)
        await lock_contract_price(
            session,
            subscription.id,
            Catalog.model_validate(catalog.document).entries[0].offer.id,
            "RUB",
            catalog.revision,
            datetime.now(UTC),
        )
    snapshots["active"] = await overview(client, token)
    await set_paid(
        postgres,
        user_id,
        datetime.now(UTC) + timedelta(days=20),
        status=SubscriptionStatus.CANCELED,
    )
    snapshots["canceled"] = await overview(client, token)
    await set_paid(
        postgres,
        user_id,
        datetime.now(UTC) - timedelta(seconds=1),
        status=SubscriptionStatus.CANCELED,
    )
    snapshots["expired"] = await overview(client, token)
    await set_paid(postgres, user_id, datetime.now(UTC) + timedelta(days=20))
    async with postgres.session() as session, session.begin():
        await session.execute(
            update(SubscriptionRecord)
            .where(SubscriptionRecord.user_id == user_id)
            .values(plan=SubscriptionPlan.PLATINUM)
        )
    snapshots["platinum"] = await overview(client, token)
    assert snapshots["platinum"]["offers"] == []
    for key, value in snapshots.items():
        assert value["plan"] == (
            "FREE" if key in ("free", "expired") else "PLATINUM" if key == "platinum" else "PREMIUM"
        )
    me = await client.get("/me", headers={"Authorization": "Bearer " + token})
    assert me.status_code == 200 and me.json()["plan"] == snapshots["platinum"]["plan"]
    if path:
        output = Path(path)
        await asyncio.to_thread(output.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(
            output.write_text,
            json.dumps(
                {
                    "source_sha": os.getenv("PR_HEAD_SHA", os.getenv("GITHUB_SHA")),
                    "provenance": ("Actual HTTP responses with real PostgreSQL/auth in disposable CI; "
                               "no live account or payment provider"),
                    "snapshots": snapshots,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
