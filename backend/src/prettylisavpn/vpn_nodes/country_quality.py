"""Replaceable country-quality aggregation over backend metric snapshots."""

from collections.abc import Sequence
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol

from prettylisavpn.vpn_nodes.availability import VpnNodeCapacitySnapshot


class CountryQualityStrategy(Protocol):
    def score(self, candidates: Sequence[VpnNodeCapacitySnapshot], now: datetime) -> int: ...


class ResilientCapacityCountryQualityStrategy:
    """Combine independent usable-capacity contributions without averaging nodes."""

    _minimum_eligible_contribution = Decimal("0.01")

    def __init__(self, stale_timeout: timedelta) -> None:
        if stale_timeout <= timedelta(0):
            raise ValueError("stale_timeout must be positive")
        self._stale_seconds = Decimal(str(stale_timeout.total_seconds()))

    def score(self, candidates: Sequence[VpnNodeCapacitySnapshot], now: datetime) -> int:
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now must be timezone-aware")
        if not candidates:
            return 0

        combined_failure = Decimal(1)
        for candidate in candidates:
            headroom = Decimal(candidate.remaining_capacity) / Decimal(candidate.node.capacity)
            freshness = self._freshness(candidate, now)
            contribution = max(
                self._minimum_eligible_contribution,
                min(Decimal(1), headroom * freshness),
            )
            combined_failure *= Decimal(1) - contribution

        score = int(
            ((Decimal(1) - combined_failure) * Decimal(100)).quantize(
                Decimal(1), rounding=ROUND_HALF_UP
            )
        )
        return max(1, min(100, score))

    def _freshness(self, candidate: VpnNodeCapacitySnapshot, now: datetime) -> Decimal:
        last_seen_at = candidate.node.last_seen_at
        if last_seen_at is None:
            return self._minimum_eligible_contribution
        age_seconds = Decimal(str(max(0.0, (now - last_seen_at).total_seconds())))
        half_stale = self._stale_seconds / Decimal(2)
        if age_seconds <= half_stale:
            return Decimal(1)
        confidence = Decimal(2) * (Decimal(1) - age_seconds / self._stale_seconds)
        return max(self._minimum_eligible_contribution, min(Decimal(1), confidence))
