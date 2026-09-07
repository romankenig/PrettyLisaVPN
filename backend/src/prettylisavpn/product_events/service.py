"""Best-effort, privacy-conscious product event recording."""

import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from uuid import UUID, uuid4

from prettylisavpn.product_events.domain import (
    ProductEvent,
    ProductEventName,
    allowlisted_properties,
)
from prettylisavpn.product_events.repository import ProductEventRepository

logger = logging.getLogger(__name__)


class ProductEventService:
    def __init__(self, repository: ProductEventRepository) -> None:
        self._repository = repository

    async def record(
        self,
        event_name: ProductEventName,
        *,
        user_id: UUID | None = None,
        device_id: UUID | None = None,
        properties: Mapping[str, object] | None = None,
        occurred_at: datetime | None = None,
    ) -> ProductEvent | None:
        try:
            event = ProductEvent(
                id=uuid4(),
                user_id=user_id,
                device_id=device_id,
                event_name=event_name,
                properties=allowlisted_properties(event_name, properties),
                occurred_at=occurred_at if occurred_at is not None else datetime.now(UTC),
            )
            return await self._repository.add(event)
        except Exception:
            logger.warning("product_event_recording_failed")
            return None
