"""Async persistence operations for subscriptions."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from prettylisavpn.subscriptions.domain import Subscription
from prettylisavpn.subscriptions.model import SubscriptionRecord


class SubscriptionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, subscription: Subscription) -> Subscription:
        record = SubscriptionRecord(
            id=subscription.id,
            user_id=subscription.user_id,
            plan=subscription.plan,
            status=subscription.status,
            current_period_start=subscription.current_period_start,
            current_period_end=subscription.current_period_end,
            auto_renew=subscription.auto_renew,
            created_at=subscription.created_at,
            updated_at=subscription.updated_at,
        )
        self._session.add(record)
        await self._session.flush()
        return self._to_domain(record)

    async def get_by_user_id(self, user_id: UUID) -> Subscription | None:
        statement = select(SubscriptionRecord).where(SubscriptionRecord.user_id == user_id)
        record = await self._session.scalar(statement)
        return self._to_domain(record) if record is not None else None

    @staticmethod
    def _to_domain(record: SubscriptionRecord) -> Subscription:
        return Subscription(
            id=record.id,
            user_id=record.user_id,
            plan=record.plan,
            status=record.status,
            current_period_start=record.current_period_start,
            current_period_end=record.current_period_end,
            auto_renew=record.auto_renew,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )
