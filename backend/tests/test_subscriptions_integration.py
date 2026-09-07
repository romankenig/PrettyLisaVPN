"""Subscription persistence tests against local Compose PostgreSQL or CI."""

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError

from prettylisavpn.config import Settings
from prettylisavpn.connections import Postgres
from prettylisavpn.subscriptions.domain import (
    Subscription,
    SubscriptionPlan,
    SubscriptionStatus,
)
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


async def test_new_user_persists_with_one_free_subscription():
    postgres = Postgres(Settings())
    email = f"subscription-{uuid4()}@example.com"
    try:
        async with postgres.session() as session:
            user = await UserService(
                UserRepository(session), SubscriptionRepository(session)
            ).create(email)
            await session.commit()

        async with postgres.session() as session:
            persisted = await SubscriptionRepository(session).get_by_user_id(user.id)

        assert persisted is not None
        assert persisted.plan is SubscriptionPlan.FREE
        assert persisted.status is SubscriptionStatus.ACTIVE
        assert persisted.current_period_end is None
        assert not persisted.auto_renew
        assert persisted.created_at.utcoffset().total_seconds() == 0

        now = datetime.now(UTC)
        duplicate = Subscription(
            id=uuid4(),
            user_id=user.id,
            plan=SubscriptionPlan.PREMIUM,
            status=SubscriptionStatus.ACTIVE,
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
            auto_renew=True,
            created_at=now,
            updated_at=now,
        )
        with pytest.raises(IntegrityError):
            async with postgres.session() as session:
                await SubscriptionRepository(session).add(duplicate)
    finally:
        async with postgres.session() as session:
            await session.execute(delete(UserRecord).where(UserRecord.email == email))
            await session.commit()
        await postgres.close()
