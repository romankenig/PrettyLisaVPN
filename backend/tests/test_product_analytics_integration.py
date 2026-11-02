"""Activity-time cohorts, atomic publication and retries against disposable PostgreSQL."""

import asyncio
import os
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import delete, select, update
from test_auth_sessions_integration import create_user

from prettylisavpn.config import Settings
from prettylisavpn.connections import Postgres
from prettylisavpn.product_analytics.activity import DatabaseActivitySink
from prettylisavpn.product_analytics.domain import boundary, day
from prettylisavpn.product_analytics.model import (
    ActivityRecord,
    AnalyticsCollectionRecord,
    AnalyticsSnapshotRecord,
)
from prettylisavpn.product_analytics.service import ProductAnalyticsService
from prettylisavpn.product_events.domain import ProductEventName
from prettylisavpn.product_events.model import ProductEventRecord
from prettylisavpn.subscriptions.domain import SubscriptionPlan
from prettylisavpn.subscriptions.model import SubscriptionRecord
from prettylisavpn.users.model import UserRecord

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1", reason="Requires disposable PostgreSQL"
    ),
]


@pytest.fixture
async def analytics_db():
    postgres = Postgres(Settings())
    user = await create_user(postgres, f"analytics-{uuid4()}@gmail.com")
    try:
        yield postgres, user
    finally:
        async with postgres.session() as session, session.begin():
            await session.execute(delete(UserRecord).where(UserRecord.id == user.id))
        await postgres.close()


async def test_capture_deduplicates_devices_and_observes_expiry_and_reserved_accounts(analytics_db):
    postgres, user = analytics_db
    sink = DatabaseActivitySink(postgres)
    now = datetime.now(UTC)
    async with postgres.session() as session, session.begin():
        await session.execute(
            update(SubscriptionRecord)
            .where(SubscriptionRecord.user_id == user.id)
            .values(
                plan=SubscriptionPlan.PLATINUM,
                current_period_start=now - timedelta(days=2),
                current_period_end=now + timedelta(days=1),
            )
        )
    await asyncio.gather(*(sink.record(user.id) for _ in range(4)))
    async with postgres.session() as session, session.begin():
        rows = (
            await session.scalars(select(ActivityRecord).where(ActivityRecord.user_id == user.id))
        ).all()
        assert len(rows) == 1 and rows[0].plan == "PLATINUM"
        await session.execute(
            update(SubscriptionRecord)
            .where(SubscriptionRecord.user_id == user.id)
            .values(current_period_end=now - timedelta(hours=1))
        )
    await sink.record(user.id)
    async with postgres.session() as session, session.begin():
        row = await session.get(ActivityRecord, (user.id, day(now)))
        assert row.plan == "FREE"
        await session.execute(delete(ActivityRecord).where(ActivityRecord.user_id == user.id))
        await session.execute(
            update(UserRecord)
            .where(UserRecord.id == user.id)
            .values(email=f"excluded-{uuid4()}@example.com")
        )
    await sink.record(user.id)
    async with postgres.session() as session:
        assert (
            await session.scalar(select(ActivityRecord).where(ActivityRecord.user_id == user.id))
            is None
        )


async def test_daily_snapshot_survives_failure_and_restart_without_relabelling(
    analytics_db, monkeypatch
):
    postgres, user = analytics_db
    # Isolate report date from any other integration fixtures.
    now = datetime(2099, 6, 2, 9, tzinfo=UTC)
    yesterday = day(now) - timedelta(days=1)
    observed = boundary(yesterday) + timedelta(hours=10)
    service = ProductAnalyticsService(postgres)
    async with postgres.session() as session, session.begin():
        collection = await session.get(AnalyticsCollectionRecord, 1)
        old_start = collection.started_at
        collection.started_at = boundary(yesterday)
        session.add(
            ActivityRecord(user_id=user.id, day=yesterday, observed_at=observed, plan="FREE")
        )
        # Old event stream has no tariff. It must not erase the new known plan.
        session.add(
            ProductEventRecord(
                event_name=ProductEventName.TOKEN_REFRESHED,
                user_id=user.id,
                occurred_at=observed + timedelta(seconds=1),
                properties={},
            )
        )
        await session.execute(
            update(SubscriptionRecord)
            .where(SubscriptionRecord.user_id == user.id)
            .values(
                plan=SubscriptionPlan.PLATINUM,
                current_period_start=observed,
                current_period_end=now + timedelta(days=30),
            )
        )
    original = service.build
    try:
        monkeypatch.setattr(service, "build", AsyncMock(side_effect=RuntimeError("interrupted")))
        with pytest.raises(RuntimeError, match="interrupted"):
            await service.refresh(now)
        async with postgres.session() as session:
            assert await session.get(AnalyticsSnapshotRecord, yesterday) is None
        monkeypatch.setattr(service, "build", original)
        results = await asyncio.gather(service.refresh(now), service.refresh(now))
        assert sum(results) == 1
        stored = await service.latest()
        point = stored["points"][-1]
        assert point["date"] == yesterday.isoformat()
        assert point["dau"]["plans"] == {"FREE": 1, "PREMIUM": 0, "PLATINUM": 0, "UNKNOWN": 0}
        assert not await ProductAnalyticsService(postgres).refresh(now + timedelta(hours=1))
        assert await service.latest() == stored
        assert str(user.id) not in str(stored) and user.email not in str(stored)
    finally:
        async with postgres.session() as session, session.begin():
            await session.execute(
                update(AnalyticsCollectionRecord)
                .where(AnalyticsCollectionRecord.id == 1)
                .values(started_at=old_start)
            )
            await session.execute(
                delete(AnalyticsSnapshotRecord).where(
                    AnalyticsSnapshotRecord.through_date == yesterday
                )
            )
