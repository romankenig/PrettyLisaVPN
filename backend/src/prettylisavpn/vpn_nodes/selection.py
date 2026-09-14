"""Country-safe VPN eligibility views and internal node selection."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from fractions import Fraction
from typing import Protocol

from prettylisavpn.subscriptions.domain import SubscriptionPlan
from prettylisavpn.vpn_nodes.availability import (
    VpnNodeCapacitySnapshot,
    VpnNodeEligibilityPolicy,
)
from prettylisavpn.vpn_nodes.domain import VpnNode, normalize_country_code


class CountryQuality(StrEnum):
    GOOD = "GOOD"
    LIMITED = "LIMITED"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class CountryEligibility:
    """Client-safe country result that contains no node identity or topology."""

    country_code: str
    available: bool
    quality: CountryQuality


class VpnNodeCapacityRepository(Protocol):
    async def list_capacity_snapshots(
        self,
        country_code: str | None = None,
        *,
        at: datetime,
        lock_nodes: bool = False,
    ) -> list[VpnNodeCapacitySnapshot]: ...


class NoEligibleVpnNodeError(LookupError):
    pass


class VpnNodeSelectionService:
    """Uses one policy for country views and internal session placement."""

    def __init__(
        self,
        repository: VpnNodeCapacityRepository,
        stale_timeout: timedelta,
    ) -> None:
        self._repository = repository
        self._policy = VpnNodeEligibilityPolicy(stale_timeout)

    async def list_countries(
        self, plan: SubscriptionPlan, now: datetime
    ) -> list[CountryEligibility]:
        self._require_aware(now)
        grouped: dict[str, list[VpnNodeCapacitySnapshot]] = defaultdict(list)
        for snapshot in await self._repository.list_capacity_snapshots(at=now):
            grouped[snapshot.node.country_code].append(snapshot)
        return [
            self._summarize(country_code, snapshots, plan, now)
            for country_code, snapshots in sorted(grouped.items())
        ]

    async def country_availability(
        self,
        country_code: str,
        plan: SubscriptionPlan,
        now: datetime,
    ) -> CountryEligibility:
        self._require_aware(now)
        normalized = normalize_country_code(country_code)
        snapshots = await self._repository.list_capacity_snapshots(normalized, at=now)
        return self._summarize(normalized, snapshots, plan, now)

    async def country_quality(
        self,
        country_code: str,
        plan: SubscriptionPlan,
        now: datetime,
    ) -> CountryQuality:
        return (await self.country_availability(country_code, plan, now)).quality

    async def select_node_for_session(
        self,
        country_code: str,
        plan: SubscriptionPlan,
        now: datetime,
    ) -> VpnNode:
        """Return an internal node only after locking country nodes for allocation."""
        self._require_aware(now)
        normalized = normalize_country_code(country_code)
        snapshots = await self._repository.list_capacity_snapshots(
            normalized, at=now, lock_nodes=True
        )
        eligible = self._eligible(snapshots, plan, now)
        if not eligible:
            raise NoEligibleVpnNodeError(normalized)
        selected = max(
            eligible,
            key=lambda snapshot: (
                Fraction(snapshot.remaining_capacity, snapshot.node.capacity),
                snapshot.remaining_capacity,
                str(snapshot.node.id),
            ),
        )
        return selected.node

    def _summarize(
        self,
        country_code: str,
        snapshots: list[VpnNodeCapacitySnapshot],
        plan: SubscriptionPlan,
        now: datetime,
    ) -> CountryEligibility:
        eligible = self._eligible(snapshots, plan, now)
        if not eligible:
            return CountryEligibility(country_code, False, CountryQuality.UNAVAILABLE)
        remaining = sum(snapshot.remaining_capacity for snapshot in eligible)
        capacity = sum(snapshot.node.capacity for snapshot in eligible)
        quality = CountryQuality.LIMITED if remaining * 4 <= capacity else CountryQuality.GOOD
        return CountryEligibility(country_code, True, quality)

    def _eligible(
        self,
        snapshots: list[VpnNodeCapacitySnapshot],
        plan: SubscriptionPlan,
        now: datetime,
    ) -> list[VpnNodeCapacitySnapshot]:
        return [
            snapshot
            for snapshot in snapshots
            if self._policy.evaluate(snapshot, plan, now).available
        ]

    @staticmethod
    def _require_aware(now: datetime) -> None:
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now must be timezone-aware")
