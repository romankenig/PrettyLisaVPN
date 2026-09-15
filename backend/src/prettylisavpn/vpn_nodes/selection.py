"""Country-safe VPN eligibility views and internal node selection."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Protocol

from prettylisavpn.subscriptions.domain import SubscriptionPlan
from prettylisavpn.vpn_nodes.availability import (
    VpnNodeCapacitySnapshot,
    VpnNodeEligibilityPolicy,
)
from prettylisavpn.vpn_nodes.domain import VpnNode, normalize_country_code
from prettylisavpn.vpn_nodes.strategy import (
    LeastLoadedNodeSelectionStrategy,
    NodeSelectionStrategy,
)


class NodeSelectionMode(StrEnum):
    AUTO = "AUTO"
    COUNTRY = "COUNTRY"


@dataclass(frozen=True, slots=True)
class NodeSelectionRequest:
    mode: NodeSelectionMode
    country_code: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.mode, NodeSelectionMode):
            raise ValueError("mode must be AUTO or COUNTRY")
        if self.mode is NodeSelectionMode.AUTO:
            if self.country_code is not None:
                raise ValueError("AUTO selection must not include country_code")
            return
        if self.country_code is None:
            raise ValueError("COUNTRY selection requires country_code")
        object.__setattr__(self, "country_code", normalize_country_code(self.country_code))

    @classmethod
    def auto(cls) -> "NodeSelectionRequest":
        return cls(NodeSelectionMode.AUTO)

    @classmethod
    def country(cls, country_code: str) -> "NodeSelectionRequest":
        return cls(NodeSelectionMode.COUNTRY, country_code)


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
        strategy: NodeSelectionStrategy | None = None,
    ) -> None:
        self._repository = repository
        self._policy = VpnNodeEligibilityPolicy(stale_timeout)
        self._strategy = strategy or LeastLoadedNodeSelectionStrategy()

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
        request: NodeSelectionRequest,
        plan: SubscriptionPlan,
        now: datetime,
    ) -> VpnNode:
        """Build AUTO/COUNTRY candidates, then invoke the same internal strategy."""
        self._require_aware(now)
        snapshots = await self._repository.list_capacity_snapshots(
            request.country_code, at=now, lock_nodes=True
        )
        eligible = self._eligible(snapshots, plan, now)
        if not eligible:
            raise NoEligibleVpnNodeError(request.mode.value)
        selected = self._strategy.select(eligible)
        if selected not in eligible:
            raise ValueError("node selection strategy returned a non-candidate")
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
