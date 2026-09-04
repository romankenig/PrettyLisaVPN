"""Readiness policy, independent of HTTP and concrete providers."""

import asyncio
import logging
from typing import Protocol

logger = logging.getLogger(__name__)


class Dependency(Protocol):
    async def ping(self) -> None: ...

    async def close(self) -> None: ...


class Readiness:
    def __init__(self, postgres: Dependency, valkey: Dependency, timeout: float) -> None:
        self.postgres = postgres
        self.valkey = valkey
        self.timeout = timeout

    async def _check(self, dependency: Dependency) -> bool:
        try:
            async with asyncio.timeout(self.timeout):
                await dependency.ping()
            return True
        except Exception:
            # Never emit exception messages: drivers may include credentials or URLs.
            logger.warning("dependency_check_failed")
            return False

    async def check(self) -> dict[str, bool]:
        postgres, valkey = await asyncio.gather(
            self._check(self.postgres), self._check(self.valkey)
        )
        return {"postgresql": postgres, "valkey": valkey}
