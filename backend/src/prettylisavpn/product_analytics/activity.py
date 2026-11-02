"""Best-effort activity capture after authentication, without request details."""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy.dialects.postgresql import insert

from prettylisavpn.connections import Postgres
from prettylisavpn.product_analytics.domain import day
from prettylisavpn.product_analytics.model import ActivityRecord
from prettylisavpn.subscriptions.repository import SubscriptionRepository
from prettylisavpn.users.model import UserRecord

logger = logging.getLogger(__name__)


class ActivitySink(Protocol):
    async def record(self, user_id: UUID) -> None: ...


async def record_activity(sink: ActivitySink | None, user_id: UUID) -> None:
    if sink is None:
        return
    try:
        async with asyncio.timeout(0.5):
            await sink.record(user_id)
    except Exception:
        # Analytics can never invalidate a successful login or VPN request.
        logger.warning("activity_recording_failed")


def is_test_account(email: str) -> bool:
    domain = email.rpartition("@")[2].lower()
    return domain in {"example.com", "example.net", "example.org"} or domain.endswith(
        (".test", ".invalid", ".example")
    )


class DatabaseActivitySink:
    def __init__(self, postgres: Postgres) -> None:
        self.postgres = postgres

    async def record(self, user_id: UUID) -> None:
        async with self.postgres.session() as session, session.begin():
            user = await session.get(UserRecord, user_id)
            if user is None or is_test_account(user.email):
                return
            subscription = await SubscriptionRepository(session).get_by_user_id(user_id)
            now = datetime.now(UTC)
            plan = subscription.effective_plan(now).value if subscription else "UNKNOWN"
            statement = insert(ActivityRecord).values(
                user_id=user_id, day=day(now), observed_at=now, plan=plan
            )
            await session.execute(
                statement.on_conflict_do_update(
                    index_elements=[ActivityRecord.user_id, ActivityRecord.day],
                    set_={"observed_at": now, "plan": plan},
                    where=ActivityRecord.observed_at < now,
                )
            )
