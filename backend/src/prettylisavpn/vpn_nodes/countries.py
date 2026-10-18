"""Authenticated, product-safe VPN country availability application service."""

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Protocol

from sqlalchemy.exc import SQLAlchemyError

from prettylisavpn.auth.session_service import AuthenticatedSessionHandler
from prettylisavpn.connections import Postgres
from prettylisavpn.subscriptions.domain import SubscriptionPlan
from prettylisavpn.vpn_nodes.repository import VpnNodeRepository
from prettylisavpn.vpn_nodes.selection import CountryEligibility, VpnNodeSelectionService


class VpnCountryAvailabilityUnavailableError(RuntimeError):
    """Country availability snapshots cannot currently be loaded."""


@dataclass(frozen=True, slots=True)
class AutopilotEligibility:
    available: bool
    quality: int

    def __post_init__(self) -> None:
        if not 0 <= self.quality <= 100:
            raise ValueError("quality must be between 0 and 100")
        if self.available != (self.quality > 0):
            raise ValueError("availability and quality are inconsistent")


@dataclass(frozen=True, slots=True)
class VpnCountryAvailability:
    autopilot: AutopilotEligibility
    countries: tuple[CountryEligibility, ...]


class VpnCountryCatalog(Protocol):
    async def list_countries(
        self, plan: SubscriptionPlan, now: datetime
    ) -> list[CountryEligibility]: ...


class VpnCountryAvailabilityHandler(Protocol):
    async def list_countries(self, access_token: str) -> VpnCountryAvailability: ...


class DatabaseVpnCountryCatalog:
    """Loads backend-maintained node and capacity snapshots without agent calls."""

    def __init__(self, postgres: Postgres, stale_timeout: timedelta) -> None:
        self._postgres = postgres
        self._stale_timeout = stale_timeout

    async def list_countries(
        self, plan: SubscriptionPlan, now: datetime
    ) -> list[CountryEligibility]:
        try:
            async with self._postgres.session() as session:
                selection = VpnNodeSelectionService(VpnNodeRepository(session), self._stale_timeout)
                return await selection.list_countries(plan, now)
        except SQLAlchemyError:
            raise VpnCountryAvailabilityUnavailableError(
                "VPN country availability storage is unavailable"
            ) from None


class VpnCountryAvailabilityService:
    def __init__(
        self,
        authenticated_sessions: AuthenticatedSessionHandler,
        catalog: VpnCountryCatalog,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._authenticated_sessions = authenticated_sessions
        self._catalog = catalog
        self._clock = clock or (lambda: datetime.now(UTC))

    async def list_countries(self, access_token: str) -> VpnCountryAvailability:
        principal = await self._authenticated_sessions.me(access_token)
        countries = tuple(await self._catalog.list_countries(principal.plan, self._clock()))
        if principal.plan is SubscriptionPlan.FREE and principal.free_seconds_remaining == 0:
            countries = tuple(replace(country, available=False, quality=0) for country in countries)
        best_quality = max((country.quality for country in countries), default=0)
        return VpnCountryAvailability(
            autopilot=AutopilotEligibility(best_quality > 0, best_quality),
            countries=countries,
        )

