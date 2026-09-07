"""Async persistence operations for product events."""

from sqlalchemy.ext.asyncio import AsyncSession

from prettylisavpn.product_events.domain import ProductEvent
from prettylisavpn.product_events.model import ProductEventRecord


class ProductEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, event: ProductEvent) -> ProductEvent:
        record = ProductEventRecord(
            id=event.id,
            user_id=event.user_id,
            device_id=event.device_id,
            event_name=event.event_name,
            properties=event.properties,
            occurred_at=event.occurred_at,
        )
        async with self._session.begin_nested():
            self._session.add(record)
            await self._session.flush()
        return event
