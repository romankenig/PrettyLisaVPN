"""Country Quality aggregation and eligibility integration tests."""

from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from ipaddress import IPv4Address
from uuid import UUID

import pytest

from prettylisavpn.subscriptions.domain import SubscriptionPlan
from prettylisavpn.vpn_nodes.availability import VpnNodeCapacitySnapshot
from prettylisavpn.vpn_nodes.country_quality import (
    ResilientCapacityCountryQualityStrategy,
)
from prettylisavpn.vpn_nodes.domain import (
    VpnNode,
    VpnNodeHealthStatus,
    VpnNodeProvider,
    VpnNodeStatus,
)
from prettylisavpn.vpn_nodes.selection import CountryEligibility, VpnNodeSelectionService

NOW = datetime(2026, 9, 15, 12, tzinfo=UTC)
STALE_TIMEOUT = timedelta(seconds=100)
PUBLIC_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="


def make_node(node_id: int, **changes: object) -> VpnNode:
    node = VpnNode(
        id=UUID(int=node_id),
        name=f"node-{node_id}",
        provider=VpnNodeProvider.DIGITALOCEAN,
        provider_region="fra1",
        country_code="DE",
        city="Frankfurt",
        public_ipv4=IPv4Address(f"203.0.113.{node_id}"),
        private_ipv4=None,
        wireguard_port=51820,
        wireguard_public_key=PUBLIC_KEY,
        capacity=100,
        status=VpnNodeStatus.ACTIVE,
        last_seen_at=NOW,
        created_at=NOW - timedelta(days=1),
        updated_at=NOW,
        health_status=VpnNodeHealthStatus.HEALTHY,
        health_checked_at=NOW,
        is_available_for_free=True,
    )
    return replace(node, **changes)


class FakeCapacityRepository:
    def __init__(self, snapshots: list[VpnNodeCapacitySnapshot]) -> None:
        self._snapshots = snapshots

    async def list_capacity_snapshots(
        self,
        country_code: str | None = None,
        *,
        at: datetime,
        lock_nodes: bool = False,
    ) -> list[VpnNodeCapacitySnapshot]:
        return [
            snapshot
            for snapshot in self._snapshots
            if country_code is None or snapshot.node.country_code == country_code
        ]


def test_one_fresh_empty_node_scores_100():
    strategy = ResilientCapacityCountryQualityStrategy(STALE_TIMEOUT)

    score = strategy.score([VpnNodeCapacitySnapshot(make_node(1), 0)], NOW)

    assert score == 100


def test_several_nodes_are_combined_non_linearly_instead_of_averaged():
    strategy = ResilientCapacityCountryQualityStrategy(STALE_TIMEOUT)
    candidates = [
        VpnNodeCapacitySnapshot(make_node(1), 50),
        VpnNodeCapacitySnapshot(make_node(2), 50),
    ]

    score = strategy.score(candidates, NOW)

    assert score == 75
    assert score != 50


def test_one_good_and_one_poor_node_preserve_good_country_quality():
    strategy = ResilientCapacityCountryQualityStrategy(STALE_TIMEOUT)
    candidates = [
        VpnNodeCapacitySnapshot(make_node(1), 10),
        VpnNodeCapacitySnapshot(make_node(2), 90),
    ]

    assert strategy.score(candidates, NOW) == 91


def test_health_snapshot_freshness_reduces_confidence_after_half_stale_timeout():
    strategy = ResilientCapacityCountryQualityStrategy(STALE_TIMEOUT)
    aging = make_node(
        1,
        last_seen_at=NOW - timedelta(seconds=75),
        health_checked_at=NOW - timedelta(seconds=75),
    )

    assert strategy.score([VpnNodeCapacitySnapshot(aging, 0)], NOW) == 50


@pytest.mark.parametrize("live_sessions", [0, 1, 50, 99])
def test_nonempty_quality_is_always_bounded_from_1_to_100(live_sessions: int):
    strategy = ResilientCapacityCountryQualityStrategy(STALE_TIMEOUT)

    score = strategy.score([VpnNodeCapacitySnapshot(make_node(1), live_sessions)], NOW)

    assert 1 <= score <= 100


@pytest.mark.parametrize(
    "snapshots",
    [
        [],
        [VpnNodeCapacitySnapshot(make_node(1, capacity=1), 1)],
        [VpnNodeCapacitySnapshot(make_node(1, status=VpnNodeStatus.OFFLINE), 0)],
    ],
)
async def test_no_eligible_full_or_offline_country_scores_zero(
    snapshots: list[VpnNodeCapacitySnapshot],
):
    selection = VpnNodeSelectionService(FakeCapacityRepository(snapshots), STALE_TIMEOUT)

    result = await selection.country_availability("DE", SubscriptionPlan.PREMIUM, NOW)

    assert result == CountryEligibility("DE", False, 0)


async def test_free_and_premium_quality_use_different_eligible_sets():
    free_poor = VpnNodeCapacitySnapshot(make_node(1, is_available_for_free=True), 90)
    premium_good = VpnNodeCapacitySnapshot(make_node(2, is_available_for_free=False), 0)
    selection = VpnNodeSelectionService(
        FakeCapacityRepository([free_poor, premium_good]), STALE_TIMEOUT
    )

    free = await selection.country_availability("DE", SubscriptionPlan.FREE, NOW)
    premium = await selection.country_availability("DE", SubscriptionPlan.PREMIUM, NOW)

    assert free == CountryEligibility("DE", True, 10)
    assert premium == CountryEligibility("DE", True, 100)


class FixedCountryQualityStrategy:
    def __init__(self, score: int = 37) -> None:
        self.candidates: tuple[UUID, ...] = ()
        self._score = score

    def score(self, candidates: Sequence[VpnNodeCapacitySnapshot], now: datetime) -> int:
        self.candidates = tuple(candidate.node.id for candidate in candidates)
        return self._score


async def test_country_quality_formula_is_replaceable_and_receives_only_eligible_snapshots():
    eligible = VpnNodeCapacitySnapshot(make_node(1), 20)
    offline = VpnNodeCapacitySnapshot(make_node(2, status=VpnNodeStatus.OFFLINE), 0)
    formula = FixedCountryQualityStrategy()
    selection = VpnNodeSelectionService(
        FakeCapacityRepository([eligible, offline]),
        STALE_TIMEOUT,
        country_quality_strategy=formula,
    )

    result = await selection.country_availability("DE", SubscriptionPlan.PREMIUM, NOW)

    assert result == CountryEligibility("DE", True, 37)
    assert formula.candidates == (eligible.node.id,)
    assert not hasattr(result, "node_scores")
    assert not hasattr(result, "node_count")


@pytest.mark.parametrize("invalid_score", [0, 101])
async def test_replaceable_formula_cannot_return_out_of_bounds_for_eligible_country(
    invalid_score: int,
):
    selection = VpnNodeSelectionService(
        FakeCapacityRepository([VpnNodeCapacitySnapshot(make_node(1), 0)]),
        STALE_TIMEOUT,
        country_quality_strategy=FixedCountryQualityStrategy(invalid_score),
    )

    with pytest.raises(ValueError, match="out-of-range"):
        await selection.country_availability("DE", SubscriptionPlan.PREMIUM, NOW)
