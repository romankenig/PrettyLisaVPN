"""Best-effort database adapter for authentication product events."""

import logging
from collections.abc import Mapping
from uuid import UUID

from prettylisavpn.connections import Postgres
from prettylisavpn.product_events.domain import ProductEventName
from prettylisavpn.product_events.repository import ProductEventRepository
from prettylisavpn.product_events.service import ProductEventService

logger = logging.getLogger(__name__)


class DatabaseProductEventSink:
    def __init__(self, postgres: Postgres) -> None:
        self._postgres = postgres

    async def record(
        self,
        event_name: ProductEventName,
        *,
        user_id: UUID | None = None,
        device_id: UUID | None = None,
        properties: Mapping[str, object] | None = None,
    ) -> None:
        try:
            async with self._postgres.session() as session:
                event = await ProductEventService(ProductEventRepository(session)).record(
                    event_name,
                    user_id=user_id,
                    device_id=device_id,
                    properties=properties,
                )
                if event is not None:
                    await session.commit()
        except Exception:
            logger.warning("product_event_recording_failed")
