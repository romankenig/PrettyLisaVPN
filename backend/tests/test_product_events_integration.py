"""Product event persistence tests against local Compose PostgreSQL or CI."""

import os
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from prettylisavpn.config import Settings
from prettylisavpn.connections import Postgres
from prettylisavpn.product_events.domain import ProductEventName
from prettylisavpn.product_events.model import ProductEventRecord
from prettylisavpn.product_events.repository import ProductEventRepository
from prettylisavpn.product_events.service import ProductEventService
from prettylisavpn.subscriptions.repository import SubscriptionRepository
from prettylisavpn.users.model import UserRecord
from prettylisavpn.users.repository import UserRepository
from prettylisavpn.users.service import UserService

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1",
        reason="Set RUN_INTEGRATION_TESTS=1 with PostgreSQL running",
    ),
]


async def test_persists_allowlisted_jsonb_properties_with_utc_time():
    postgres = Postgres(Settings())
    recorded_id = None
    try:
        async with postgres.session() as session:
            recorded = await ProductEventService(ProductEventRepository(session)).record(
                ProductEventName.DEVICE_REGISTERED,
                properties={"platform": "WINDOWS", "refresh_token": "never-store-this"},
            )
            await session.commit()

        assert recorded is not None
        recorded_id = recorded.id
        async with postgres.session() as session:
            persisted = await session.get(ProductEventRecord, recorded.id)

        assert persisted is not None
        assert persisted.properties == {"platform": "WINDOWS"}
        assert persisted.occurred_at.utcoffset().total_seconds() == 0
    finally:
        if recorded_id is not None:
            async with postgres.session() as session:
                await session.execute(
                    delete(ProductEventRecord).where(ProductEventRecord.id == recorded_id)
                )
                await session.commit()
        await postgres.close()


async def test_event_failure_does_not_abort_user_creation_transaction():
    postgres = Postgres(Settings())
    email = f"analytics-failure-{uuid4()}@example.com"
    try:
        async with postgres.session() as session:
            user = await UserService(
                UserRepository(session), SubscriptionRepository(session)
            ).create(email)
            recorded = await ProductEventService(ProductEventRepository(session)).record(
                ProductEventName.LOGIN_SUCCEEDED,
                user_id=uuid4(),
            )
            assert recorded is None
            await session.commit()

        async with postgres.session() as session:
            persisted_user = await session.scalar(
                select(UserRecord).where(UserRecord.id == user.id)
            )
        assert persisted_user is not None
    finally:
        async with postgres.session() as session:
            await session.execute(delete(UserRecord).where(UserRecord.email == email))
            await session.commit()
        await postgres.close()
