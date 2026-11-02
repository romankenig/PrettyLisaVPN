"""Main-server daily worker; restart catch-up and PostgreSQL concurrency fencing."""

import asyncio
import logging
import signal

from prettylisavpn.config import Settings
from prettylisavpn.connections import Postgres
from prettylisavpn.logging import configure_logging
from prettylisavpn.product_analytics.service import ProductAnalyticsService

logger = logging.getLogger(__name__)


async def run(service: ProductAnalyticsService, stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            if await service.refresh():
                logger.info("product_analytics_updated")
        except Exception:
            logger.error("product_analytics_refresh_failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=60)
        except TimeoutError:
            pass


async def main() -> None:
    settings = Settings()
    configure_logging(settings.log_level)
    postgres = Postgres(settings)
    stop = asyncio.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        asyncio.get_running_loop().add_signal_handler(sig, stop.set)
    try:
        await run(ProductAnalyticsService(postgres), stop)
    finally:
        await postgres.close()


if __name__ == "__main__":
    asyncio.run(main())
