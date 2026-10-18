"""Real PostgreSQL and auth sessions: account-wide ACK across independent clients."""

import asyncio
import os
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select
from sqlalchemy.exc import SQLAlchemyError
from test_account_messages import document
from test_device_management_integration import FakeDependency, create_state, headers, settings

from prettylisavpn.account_messages.domain import Publication
from prettylisavpn.account_messages.model import MessageReceiptRecord, MessageRecord, MessageRevisionRecord
from prettylisavpn.account_messages.repository import MessageRepository
from prettylisavpn.account_messages.service import MessagePublicationService, PublicationConflictError
from prettylisavpn.auth.tokens import AccessTokenService
from prettylisavpn.connections import Postgres
from prettylisavpn.devices.domain import DevicePlatform
from prettylisavpn.devices.model import DeviceRecord
from prettylisavpn.devices.repository import DeviceRepository
from prettylisavpn.devices.service import DeviceService
from prettylisavpn.main import create_app
from prettylisavpn.users.model import UserRecord

pytestmark = [pytest.mark.integration, pytest.mark.skipif(os.getenv("RUN_INTEGRATION_TESTS") != "1", reason="Needs PostgreSQL")]

WINDOWS = {"platform": "WINDOWS", "app_version": "0.8.0", "locale": "ru-RU", "schema_version": "1"}
ANDROID = {**WINDOWS, "platform": "ANDROID", "app_version": "0.1.0"}


@pytest.fixture
async def state():
    config = settings()
    postgres = Postgres(config)
    own = await create_state(postgres, config, f"messages-own-{uuid4()}@example.com", device_count=2)
    other = await create_state(postgres, config, f"messages-other-{uuid4()}@example.com")
    async with postgres.session() as session:
        await DeviceService(DeviceRepository(session)).register(own.user.id, own.devices[1].installation_id, DevicePlatform.ANDROID, "Android")
        await session.commit()
    android_token = AccessTokenService(config).issue(own.user.id, own.devices[1].id, own.sessions[1].session.id).token
    published = []
    publisher = MessagePublicationService(postgres)

    async def publish(**changes):
        payload = Publication.model_validate(document(user_ids=[str(own.user.id)], **changes))
        if payload.id not in published:
            published.append(payload.id)
        await publisher.publish(payload, "integration-test")
        return payload

    app = create_app(config, postgres=postgres, valkey=FakeDependency(), product_events=AsyncMock())
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as windows:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as android:
                try:
                    yield postgres, own, other, android_token, publish, publisher, windows, android
                finally:
                    async with postgres.session() as session:
                        await session.execute(delete(MessageRecord).where(MessageRecord.id.in_(published)))
                        await session.execute(delete(UserRecord).where(UserRecord.id.in_([own.user.id, other.user.id])))
                        await session.commit()


def ack_url(message):
    return f"/messages/{message.id}/acknowledgements"


async def listing(client, token, params=WINDOWS):
    response = await client.get("/messages", params=params, headers=headers(token))
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["vary"] == "Authorization"
    assert len(response.content) <= 65536
    return response.json()["messages"]


async def test_acknowledgement_is_shared_by_two_real_sessions_and_platforms(state):
    postgres, own, other, token, publish, _, windows, android = state
    message = await publish()
    assert [item["id"] for item in await listing(windows, own.access_token)] == [str(message.id)]
    assert [item["id"] for item in await listing(android, token, ANDROID)] == [str(message.id)]
    assert await listing(windows, other.access_token) == []
    forbidden = await windows.post(ack_url(message), json={"revision": 1}, headers=headers(other.access_token))
    assert forbidden.status_code == 404
    assert forbidden.json() == {"error": {"code": "MESSAGE_NOT_FOUND"}}
    first = await windows.post(ack_url(message), json={"revision": 1}, headers=headers(own.access_token))
    assert first.status_code == 200
    assert first.json() == {"id": str(message.id), "revision": 1, "acknowledged": True}
    # A fresh request and independent device must observe the committed account receipt.
    assert await listing(android, token, ANDROID) == []
    duplicate = await android.post(ack_url(message), json={"revision": 1}, headers=headers(token))
    assert duplicate.json() == first.json()
    async with postgres.session() as session:
        assert await session.scalar(select(func.count()).select_from(MessageReceiptRecord).where(MessageReceiptRecord.message_id == message.id)) == 1
        devices = list(await session.scalars(select(DeviceRecord).where(DeviceRecord.user_id == own.user.id)))
        assert all(device.last_login_at is None for device in devices)


async def test_get_is_not_read_and_concurrent_ack_is_idempotent(state):
    postgres, own, _, token, publish, _, windows, android = state
    message = await publish()
    assert len(await listing(windows, own.access_token)) == 1
    assert len(await listing(windows, own.access_token)) == 1
    async with postgres.session() as session:
        offered = await session.get(MessageReceiptRecord, (own.user.id, message.id, 1))
        assert offered.acknowledged_at is None
    results = await asyncio.gather(
        windows.post(ack_url(message), json={"revision": 1}, headers=headers(own.access_token)),
        android.post(ack_url(message), json={"revision": 1}, headers=headers(token)),
    )
    assert all(response.status_code == 200 for response in results)
    assert results[0].json() == results[1].json()
    assert await listing(android, token, ANDROID) == []


async def test_revisions_require_explicit_redisplay_and_stale_ack_cannot_read_new_revision(state):
    _, own, _, _, publish, _, client, _ = state
    first = await publish()
    await listing(client, own.access_token)
    await client.post(ack_url(first), json={"revision": 1}, headers=headers(own.access_token))
    await publish(id=str(first.id), revision=2, redisplay_after_ack=False)
    assert await listing(client, own.access_token) == []
    third = await publish(id=str(first.id), revision=3, redisplay_after_ack=True)
    assert (await listing(client, own.access_token))[0]["revision"] == 3
    assert (await client.post(ack_url(first), json={"revision": 1}, headers=headers(own.access_token))).status_code == 200
    assert len(await listing(client, own.access_token)) == 1
    stale = await client.post(ack_url(third), json={"revision": 2}, headers=headers(own.access_token))
    assert stale.status_code == 404
    await publish(id=str(first.id), revision=4, redisplay_after_ack=False)
    assert (await listing(client, own.access_token))[0]["revision"] == 4
    assert (await client.post(ack_url(third), json={"revision": 3}, headers=headers(own.access_token))).status_code == 404
    assert (await client.post(ack_url(third), json={"revision": 4}, headers=headers(own.access_token))).status_code == 200
    assert await listing(client, own.access_token) == []


async def test_filters_period_platform_versions_locale_schema_and_plan(state):
    _, own, _, token, publish, _, client, android = state
    now = datetime.now(UTC)
    await publish(starts_at=now + timedelta(days=1))
    await publish(expires_at=now - timedelta(seconds=1))
    await publish(plans=["PREMIUM"])
    message = await publish(platforms={"WINDOWS": {"min_version": "0.8.0", "max_version_exclusive": "1.0.0"}})
    assert [item["id"] for item in await listing(client, own.access_token)] == [str(message.id)]
    assert await listing(android, token, ANDROID) == []
    for params in ({**WINDOWS, "app_version": "0.7.9"}, {**WINDOWS, "app_version": "1.0.0"}, ANDROID):
        assert await listing(client, own.access_token, params) == []
    assert len(await listing(client, own.access_token, {**WINDOWS, "app_version": "0.8.0+build.5", "locale": "fr-FR"})) == 1
    for params in ({**WINDOWS, "schema_version": "2"}, {**WINDOWS, "app_version": "garbage"}, {**WINDOWS, "user_id": str(own.user.id)}):
        response = await client.get("/messages", params=params, headers=headers(own.access_token))
        assert response.status_code == 422
        assert response.headers["cache-control"] == "no-store"


async def test_priority_limit_and_response_byte_budget(state):
    _, own, _, _, publish, _, client, _ = state
    messages = [await publish(priority=i) for i in range(12)]
    rows = await listing(client, own.access_token)
    assert [row["id"] for row in rows] == [str(msg.id) for msg in reversed(messages[2:])]
    for row in rows:
        assert (await client.post(f'/messages/{row["id"]}/acknowledgements', json={"revision": 1}, headers=headers(own.access_token))).status_code == 200
    assert len(await listing(client, own.access_token)) == 2


async def test_publication_is_immutable_idempotent_and_withdrawal_survives_retry(state):
    postgres, own, _, _, publish, publisher, client, _ = state
    message = await publish()
    await publisher.publish(message, "retry")
    payload = message.model_dump(mode="json")
    payload["localizations"]["ru"]["title"] = "changed"
    with pytest.raises(PublicationConflictError):
        await publisher.publish(Publication.model_validate(payload), "operator")
    await publisher.withdraw(message.id)
    await publisher.withdraw(message.id)
    await publisher.publish(message, "retry")
    assert await listing(client, own.access_token) == []
    async with postgres.session() as session:
        assert await session.scalar(select(func.count()).select_from(MessageRevisionRecord).where(MessageRevisionRecord.message_id == message.id)) == 1


async def test_failed_ack_transaction_is_retried_without_losing_message(state, monkeypatch):
    _, own, _, _, publish, _, client, _ = state
    message = await publish()
    await listing(client, own.access_token)
    original = MessageRepository.receipt

    async def fail_after_lock(self, *args):
        record = await original(self, *args)
        record.acknowledged_at = datetime.now(UTC)
        await self.session.flush()
        raise SQLAlchemyError("simulated storage error")

    with monkeypatch.context() as patch:
        patch.setattr(MessageRepository, "receipt", fail_after_lock)
        response = await client.post(ack_url(message), json={"revision": 1}, headers=headers(own.access_token))
        assert response.status_code == 503
        assert response.headers["cache-control"] == "no-store"
    assert len(await listing(client, own.access_token)) == 1
    assert (await client.post(ack_url(message), json={"revision": 1}, headers=headers(own.access_token))).status_code == 200
    assert await listing(client, own.access_token) == []


async def test_no_public_publishing_and_no_unoffered_or_unauthorized_ack(state):
    _, own, _, _, publish, _, client, _ = state
    message = await publish()
    assert (await client.get("/messages", params=WINDOWS)).status_code == 401
    assert (await client.get("/messages", params=WINDOWS, headers=headers("invalid"))).status_code == 401
    for message_id in (message.id, uuid4()):
        response = await client.post(f"/messages/{message_id}/acknowledgements", json={"revision": 1}, headers=headers(own.access_token))
        assert response.status_code == 404
        assert response.headers["cache-control"] == "no-store"
    assert (await client.post("/messages", json=document(), headers=headers(own.access_token))).status_code == 405


async def test_multibyte_response_budget_defers_unoffered_messages(state):
    postgres, own, _, _, publish, _, client, _ = state
    content = {"title": "large", "fallback_text": "text", "blocks": [{"type": "paragraph", "text": "字" * 3000}] * 5}
    for _ in range(3):
        await publish(localizations={"ru": content})
    rows = await listing(client, own.access_token)
    assert len(rows) == 1
    async with postgres.session() as session:
        assert await session.scalar(select(func.count()).select_from(MessageReceiptRecord).where(MessageReceiptRecord.user_id == own.user.id)) == 1
    assert (await client.post(f'/messages/{rows[0]["id"]}/acknowledgements', json={"revision": 1}, headers=headers(own.access_token))).status_code == 200
    assert len(await listing(client, own.access_token)) == 1


@pytest.mark.parametrize("principal", ["user", "device"])
async def test_blocked_principals_cannot_get_or_ack_messages(state, principal):
    postgres, own, _, _, publish, _, client, _ = state
    message = await publish()
    await listing(client, own.access_token)
    from prettylisavpn.devices.domain import DeviceStatus
    from prettylisavpn.users.domain import UserStatus

    async with postgres.session() as session:
        if principal == "user":
            user = await session.get(UserRecord, own.user.id)
            user.status = UserStatus.BLOCKED
        else:
            device = await session.get(DeviceRecord, own.devices[0].id)
            device.status, device.revoked_at = DeviceStatus.REVOKED, datetime.now(UTC)
        await session.commit()
    get = await client.get("/messages", params=WINDOWS, headers=headers(own.access_token))
    ack = await client.post(ack_url(message), json={"revision": 1}, headers=headers(own.access_token))
    assert get.status_code == ack.status_code == 403
    assert get.headers["cache-control"] == ack.headers["cache-control"] == "no-store"
