"""Real PostgreSQL acceptance, account isolation, durable retries and retention."""

import asyncio
import json
import os
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select
from test_device_management_integration import FakeDependency, create_state, headers, settings
from test_support import diagnostics, image, report

from prettylisavpn.auth.tokens import AccessTokenService
from prettylisavpn.connections import Postgres
from prettylisavpn.main import create_app
from prettylisavpn.support.delivery import SupportWorker
from prettylisavpn.support.model import SupportAttachmentRecord, SupportRequestRecord
from prettylisavpn.users.model import UserRecord

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.getenv("RUN_INTEGRATION_TESTS") != "1", reason="Needs PostgreSQL"),
]


@pytest.fixture
async def support_state():
    config = settings()
    postgres = Postgres(config)
    own = await create_state(postgres, config, f"support-own-{uuid4()}@example.com", device_count=2)
    other = await create_state(postgres, config, f"support-other-{uuid4()}@example.com")
    second = (
        AccessTokenService(config)
        .issue(own.user.id, own.devices[1].id, own.sessions[1].session.id)
        .token
    )
    app = create_app(config, postgres=postgres, valkey=FakeDependency(), product_events=AsyncMock())
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            try:
                yield postgres, own, other, second, client
            finally:
                async with postgres.session() as session:
                    await session.execute(
                        delete(UserRecord).where(UserRecord.id.in_([own.user.id, other.user.id]))
                    )
                    await session.commit()


async def submit(client, token, payload, screenshots=True):
    files = [("report", (None, json.dumps(payload)))]
    if screenshots:
        files.append(("screenshots", ("private-original-name.png", image(), "image/png")))
    return await client.post("/support/requests", headers=headers(token), files=files)


async def test_concurrent_retries_cross_device_status_and_foreign_account(support_state):
    postgres, own, other, second, client = support_state
    data = report(diagnostics=diagnostics())
    data["diagnostics"]["auth_session_id"] = str(other.sessions[0].session.id)
    data["diagnostics"]["vpn"]["session_id"] = str(uuid4())
    responses = await asyncio.gather(
        *(submit(client, token, data) for token in (own.access_token, second, own.access_token))
    )
    assert all(r.status_code == 202 for r in responses)
    assert len({r.json()["request_id"] for r in responses}) == 1
    url = "/support/requests/" + data["request_id"]
    assert (await client.get(url, headers=headers(second))).json()["status"] == "ACCEPTED"
    assert (await client.get(url, headers=headers(other.access_token))).status_code == 404
    changed = await submit(client, own.access_token, {**data, "description": "different content"})
    assert changed.status_code == 409
    async with postgres.session() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(SupportRequestRecord)
                .where(SupportRequestRecord.user_id == own.user.id)
            )
            == 1
        )
        row = await session.get(SupportRequestRecord, (own.user.id, UUID(data["request_id"])))
        assert row.payload["diagnostics"]["auth_session_id"] is None
        assert row.payload["diagnostics"]["vpn"]["session_id"] is None
        assert (
            await session.scalar(
                select(func.count())
                .select_from(SupportAttachmentRecord)
                .where(SupportAttachmentRecord.user_id == own.user.id)
            )
            == 1
        )


async def test_outbox_survives_provider_failure_and_restart_no_duplicate_ticket(
    support_state, caplog
):
    postgres, own, _, second, client = support_state
    data = report()
    assert (await submit(client, own.access_token, data)).status_code == 202
    failing = AsyncMock()
    failing.send.side_effect = OSError("secret SMTP password and payload")
    assert await SupportWorker(postgres, failing).deliver_one()
    url = "/support/requests/" + data["request_id"]
    assert (await client.get(url, headers=headers(second))).json()["status"] == "RETRYING"
    assert (await submit(client, second, data)).status_code == 202
    async with postgres.session() as session, session.begin():
        row = await session.get(SupportRequestRecord, (own.user.id, UUID(data["request_id"])))
        row.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
    succeeding = AsyncMock()
    await SupportWorker(postgres, succeeding).deliver_one()
    assert succeeding.send.await_count == 1
    assert (await client.get(url, headers=headers(second))).json()["status"] == "SENT"
    assert not await SupportWorker(postgres, succeeding).deliver_one()
    assert "secret SMTP" not in caplog.text


async def test_workers_skip_locked_ticket_and_terminal_delivery_failure(support_state):
    postgres, own, _, _, client = support_state
    data = report()
    await submit(client, own.access_token, data)
    started, release = asyncio.Event(), asyncio.Event()

    async def blocked_send(*args):
        started.set()
        await release.wait()

    mailer = AsyncMock()
    mailer.send.side_effect = blocked_send
    first = asyncio.create_task(SupportWorker(postgres, mailer).deliver_one())
    await asyncio.wait_for(started.wait(), 5)
    try:
        assert not await SupportWorker(postgres, mailer).deliver_one()
    finally:
        release.set()
        await first
    assert mailer.send.await_count == 1
    data = report()
    await submit(client, own.access_token, data)
    async with postgres.session() as session, session.begin():
        row = await session.get(SupportRequestRecord, (own.user.id, UUID(data["request_id"])))
        row.attempts = 7
    mailer.send.side_effect = OSError()
    await SupportWorker(postgres, mailer).deliver_one()
    response = await client.get(
        "/support/requests/" + data["request_id"], headers=headers(own.access_token)
    )
    assert response.json()["status"] == "FAILED"
    assert not await SupportWorker(postgres, mailer).deliver_one()


async def test_rate_limit_does_not_block_idempotent_retry(support_state):
    _, own, _, second, client = support_state
    first = report()
    for data in [first] + [report() for _ in range(4)]:
        assert (await submit(client, own.access_token, data, False)).status_code == 202
    denied = await submit(client, own.access_token, report(), False)
    assert denied.status_code == 429
    assert denied.json()["error"]["code"] == "RATE_LIMITED"
    assert (await submit(client, second, first, False)).status_code == 202


async def test_retention_removes_content_files_but_retains_idempotency_tombstone(support_state):
    postgres, own, _, _, client = support_state
    data = report()
    await submit(client, own.access_token, data)
    async with postgres.session() as session, session.begin():
        row = await session.get(SupportRequestRecord, (own.user.id, UUID(data["request_id"])))
        row.created_at = datetime.now(UTC) - timedelta(days=31)
    await SupportWorker(postgres, None).purge()
    response = await submit(client, own.access_token, data)
    assert response.status_code == 202
    assert response.json()["status"] == "EXPIRED"
    async with postgres.session() as session:
        row = await session.get(SupportRequestRecord, (own.user.id, UUID(data["request_id"])))
        assert row.payload is None
        assert (
            await session.scalar(
                select(func.count())
                .select_from(SupportAttachmentRecord)
                .where(SupportAttachmentRecord.user_id == own.user.id)
            )
            == 0
        )


async def test_owned_auth_id_preserved_and_bad_attachment_never_written(support_state):
    postgres, own, _, _, client = support_state
    data = report(diagnostics=diagnostics())
    data["diagnostics"]["auth_session_id"] = str(own.sessions[0].session.id)
    bad = await client.post(
        "/support/requests",
        headers=headers(own.access_token),
        files={
            "report": (None, json.dumps(data)),
            "screenshots": ("fake.png", b"not an image", "image/png"),
        },
    )
    assert bad.status_code == 422
    async with postgres.session() as session:
        assert (
            await session.get(SupportRequestRecord, (own.user.id, UUID(data["request_id"]))) is None
        )
    await submit(client, own.access_token, data)
    async with postgres.session() as session:
        row = await session.get(SupportRequestRecord, (own.user.id, UUID(data["request_id"])))
        assert row.payload["diagnostics"]["auth_session_id"] == str(own.sessions[0].session.id)


async def test_daily_quota_survives_hour_window(support_state):
    postgres, own, _, _, client = support_state
    for _ in range(20):
        data = report()
        assert (await submit(client, own.access_token, data, False)).status_code == 202
        async with postgres.session() as session, session.begin():
            row = await session.get(SupportRequestRecord, (own.user.id, UUID(data["request_id"])))
            row.created_at = datetime.now(UTC) - timedelta(hours=2)
    denied = await submit(client, own.access_token, report(), False)
    assert denied.status_code == 429
    assert denied.json()["error"]["code"] == "RATE_LIMITED"
