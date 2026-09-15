"""Plan-aware node eligibility shared by country views and session creation."""

from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from ipaddress import IPv4Address
from uuid import UUID, uuid4

import pytest

from prettylisavpn.subscriptions.domain import SubscriptionPlan
from prettylisavpn.vpn_nodes.availability import (
    NodeUnavailabilityReason,
    VpnNodeCapacitySnapshot,
    VpnNodeEligibilityPolicy,
)
from prettylisavpn.vpn_nodes.domain import (
    VpnNode,
    VpnNodeHealthStatus,
    VpnNodeProvider,
    VpnNodeStatus,
)
from prettylisavpn.vpn_nodes.selection import (
    CountryEligibility,
    CountryQuality,
    NodeSelectionRequest,
    NoEligibleVpnNodeError,
    VpnNodeSelectionService,
)
from prettylisavpn.vpn_nodes.strategy import LeastLoadedNodeSelectionStrategy
from prettylisavpn.vpn_sessions.domain import VpnSession
from prettylisavpn.vpn_sessions.service import VpnSessionService

NOW = datetime(2026, 9, 14, 12, tzinfo=UTC)
PUBLIC_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="


def make_node(**changes: object) -> VpnNode:
    node = VpnNode(
        id=uuid4(),
        name=f"node-{uuid4()}",
        provider=VpnNodeProvider.DIGITALOCEAN,
        provider_region="fra1",
        country_code="DE",
        city="Frankfurt",
        public_ipv4=IPv4Address("203.0.113.30"),
        private_ipv4=None,
        wireguard_port=51820,
        wireguard_public_key=PUBLIC_KEY,
        capacity=10,
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
        self.snapshots = snapshots
        self.lock_requests = 0

    async def list_capacity_snapshots(
        self,
        country_code: str | None = None,
        *,
        at: datetime,
        lock_nodes: bool = False,
    ) -> list[VpnNodeCapacitySnapshot]:
        if lock_nodes:
            self.lock_requests += 1
        return [
            snapshot
            for snapshot in self.snapshots
            if country_code is None or snapshot.node.country_code == country_code
        ]


class FakeSessionRepository:
    def __init__(self) -> None:
        self.sessions: list[VpnSession] = []

    async def get_live_for_device(self, device_id: UUID) -> VpnSession | None:
        return next(
            (
                vpn_session
                for vpn_session in self.sessions
                if vpn_session.device_id == device_id and vpn_session.is_live()
            ),
            None,
        )

    async def add(self, vpn_session: VpnSession) -> VpnSession:
        self.sessions.append(vpn_session)
        return vpn_session


def test_policy_applies_plan_and_capacity_after_operational_health():
    premium_only = VpnNodeCapacitySnapshot(make_node(is_available_for_free=False), live_sessions=0)
    exhausted = VpnNodeCapacitySnapshot(make_node(capacity=2), live_sessions=2)
    policy = VpnNodeEligibilityPolicy(timedelta(seconds=90))

    free_result = policy.evaluate(premium_only, SubscriptionPlan.FREE, NOW)
    premium_result = policy.evaluate(premium_only, SubscriptionPlan.PREMIUM, NOW)
    exhausted_result = policy.evaluate(exhausted, SubscriptionPlan.PREMIUM, NOW)

    assert free_result.reason is NodeUnavailabilityReason.PLAN_RESTRICTED
    assert premium_result.available is True
    assert exhausted_result.reason is NodeUnavailabilityReason.CAPACITY_EXHAUSTED


def test_mvp_strategy_is_load_aware_and_deterministic_for_a_snapshot():
    stable_winner = VpnNodeCapacitySnapshot(make_node(id=UUID(int=1), capacity=20), 5)
    busier = VpnNodeCapacitySnapshot(make_node(id=UUID(int=2), capacity=10), 5)
    tied_later_id = VpnNodeCapacitySnapshot(make_node(id=UUID(int=3), capacity=20), 5)
    strategy = LeastLoadedNodeSelectionStrategy()

    assert strategy.select([busier, tied_later_id, stable_winner]) == stable_winner
    assert strategy.select([stable_winner, tied_later_id, busier]) == stable_winner


async def test_auto_uses_all_plan_eligible_countries_for_free_and_premium():
    free_node = make_node(country_code="DE", is_available_for_free=True, capacity=10)
    premium_only = make_node(
        country_code="US",
        is_available_for_free=False,
        capacity=10,
        public_ipv4=IPv4Address("203.0.113.40"),
        wireguard_public_key="BQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
    )
    selection = VpnNodeSelectionService(
        FakeCapacityRepository(
            [VpnNodeCapacitySnapshot(free_node, 8), VpnNodeCapacitySnapshot(premium_only, 0)]
        ),
        timedelta(seconds=90),
    )

    free_selected = await selection.select_node_for_session(
        NodeSelectionRequest.auto(), SubscriptionPlan.FREE, NOW
    )
    premium_selected = await selection.select_node_for_session(
        NodeSelectionRequest.auto(), SubscriptionPlan.PREMIUM, NOW
    )

    assert free_selected.id == free_node.id
    assert premium_selected.id == premium_only.id


async def test_country_ranks_multiple_nodes_only_inside_requested_country():
    busier_de = make_node(id=UUID(int=10), country_code="DE", capacity=10)
    better_de = make_node(
        id=UUID(int=11),
        country_code="DE",
        capacity=20,
        public_ipv4=IPv4Address("203.0.113.41"),
        wireguard_public_key="BgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
    )
    empty_us = make_node(
        id=UUID(int=12),
        country_code="US",
        capacity=100,
        public_ipv4=IPv4Address("203.0.113.42"),
        wireguard_public_key="BwAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
    )
    selection = VpnNodeSelectionService(
        FakeCapacityRepository(
            [
                VpnNodeCapacitySnapshot(busier_de, 5),
                VpnNodeCapacitySnapshot(better_de, 5),
                VpnNodeCapacitySnapshot(empty_us, 0),
            ]
        ),
        timedelta(seconds=90),
    )

    selected = await selection.select_node_for_session(
        NodeSelectionRequest.country("de"), SubscriptionPlan.PREMIUM, NOW
    )

    assert selected.id == better_de.id


class LastCandidateStrategy:
    def __init__(self) -> None:
        self.candidate_sets: list[tuple[UUID, ...]] = []

    def select(self, candidates: Sequence[VpnNodeCapacitySnapshot]) -> VpnNodeCapacitySnapshot:
        self.candidate_sets.append(tuple(candidate.node.id for candidate in candidates))
        return candidates[-1]


async def test_auto_and_country_use_the_same_replaceable_strategy():
    de = make_node(id=UUID(int=20), country_code="DE")
    us = make_node(
        id=UUID(int=21),
        country_code="US",
        public_ipv4=IPv4Address("203.0.113.43"),
        wireguard_public_key="CAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
    )
    full = make_node(
        id=UUID(int=22),
        capacity=1,
        public_ipv4=IPv4Address("203.0.113.44"),
        wireguard_public_key="CQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
    )
    unhealthy = make_node(
        id=UUID(int=23),
        health_status=VpnNodeHealthStatus.UNHEALTHY,
        public_ipv4=IPv4Address("203.0.113.45"),
        wireguard_public_key="CgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
    )
    strategy = LastCandidateStrategy()
    selection = VpnNodeSelectionService(
        FakeCapacityRepository(
            [
                VpnNodeCapacitySnapshot(de, 0),
                VpnNodeCapacitySnapshot(full, 1),
                VpnNodeCapacitySnapshot(unhealthy, 0),
                VpnNodeCapacitySnapshot(us, 0),
            ]
        ),
        timedelta(seconds=90),
        strategy,
    )

    auto_selected = await selection.select_node_for_session(
        NodeSelectionRequest.auto(), SubscriptionPlan.PREMIUM, NOW
    )
    country_selected = await selection.select_node_for_session(
        NodeSelectionRequest.country("DE"), SubscriptionPlan.PREMIUM, NOW
    )

    assert auto_selected.id == us.id
    assert country_selected.id == de.id
    assert strategy.candidate_sets == [(de.id, us.id), (de.id,)]


async def test_free_and_premium_country_selection_use_their_eligible_node_sets():
    free_node = make_node(capacity=10, is_available_for_free=True)
    premium_node = make_node(
        capacity=100,
        is_available_for_free=False,
        public_ipv4=IPv4Address("203.0.113.31"),
        wireguard_public_key="AQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
    )
    repository = FakeCapacityRepository(
        [VpnNodeCapacitySnapshot(free_node, 0), VpnNodeCapacitySnapshot(premium_node, 0)]
    )
    selection = VpnNodeSelectionService(repository, timedelta(seconds=90))

    free_country = await selection.country_availability("de", SubscriptionPlan.FREE, NOW)
    premium_country = await selection.country_availability("DE", SubscriptionPlan.PREMIUM, NOW)

    assert free_country == CountryEligibility("DE", True, CountryQuality.GOOD)
    assert premium_country == CountryEligibility("DE", True, CountryQuality.GOOD)
    assert (
        await selection.select_node_for_session(
            NodeSelectionRequest.country("DE"), SubscriptionPlan.FREE, NOW
        )
    ).id == free_node.id
    assert (
        await selection.select_node_for_session(
            NodeSelectionRequest.country("DE"), SubscriptionPlan.PREMIUM, NOW
        )
    ).id == premium_node.id


async def test_country_quality_ignores_ineligible_nodes_and_exposes_no_topology():
    nearly_full = make_node(capacity=10, is_available_for_free=True)
    unhealthy = make_node(
        capacity=1000,
        health_status=VpnNodeHealthStatus.UNHEALTHY,
        public_ipv4=IPv4Address("203.0.113.32"),
        wireguard_public_key="AgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
    )
    selection = VpnNodeSelectionService(
        FakeCapacityRepository(
            [VpnNodeCapacitySnapshot(nearly_full, 8), VpnNodeCapacitySnapshot(unhealthy, 0)]
        ),
        timedelta(seconds=90),
    )

    country = await selection.country_availability("DE", SubscriptionPlan.FREE, NOW)

    assert country == CountryEligibility("DE", True, CountryQuality.LIMITED)
    assert (
        await selection.country_quality("DE", SubscriptionPlan.FREE, NOW) is CountryQuality.LIMITED
    )
    assert not hasattr(country, "node_id")
    assert not hasattr(country, "public_ipv4")


@pytest.mark.parametrize(
    "node",
    [
        make_node(capacity=1),
        make_node(health_status=VpnNodeHealthStatus.UNHEALTHY),
        make_node(status=VpnNodeStatus.DRAINING),
    ],
)
async def test_exhausted_unhealthy_and_draining_countries_cannot_create_sessions(node: VpnNode):
    live_sessions = node.capacity if node.health_status is VpnNodeHealthStatus.HEALTHY else 0
    selection = VpnNodeSelectionService(
        FakeCapacityRepository([VpnNodeCapacitySnapshot(node, live_sessions)]),
        timedelta(seconds=90),
    )

    country = await selection.country_availability("DE", SubscriptionPlan.FREE, NOW)

    assert country == CountryEligibility("DE", False, CountryQuality.UNAVAILABLE)
    with pytest.raises(NoEligibleVpnNodeError):
        await selection.select_node_for_session(
            NodeSelectionRequest.country("DE"), SubscriptionPlan.FREE, NOW
        )


async def test_session_creation_uses_same_free_auto_eligibility_and_keeps_node_internal():
    free_node = make_node(is_available_for_free=True)
    premium_only = make_node(
        capacity=100,
        is_available_for_free=False,
        public_ipv4=IPv4Address("203.0.113.33"),
        wireguard_public_key="AwAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
    )
    capacity_repository = FakeCapacityRepository(
        [VpnNodeCapacitySnapshot(free_node, 0), VpnNodeCapacitySnapshot(premium_only, 0)]
    )
    selection = VpnNodeSelectionService(capacity_repository, timedelta(seconds=90))
    session_repository = FakeSessionRepository()
    service = VpnSessionService(session_repository, selection)

    vpn_session = await service.create(
        user_id=uuid4(),
        device_id=uuid4(),
        node_selection=NodeSelectionRequest.auto(),
        client_wireguard_public_key="BAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
        allocated_client_ipv4=IPv4Address("10.77.0.2"),
        plan=SubscriptionPlan.FREE,
        now=NOW,
    )

    assert vpn_session.vpn_node_id == free_node.id
    assert vpn_session.plan_snapshot is SubscriptionPlan.FREE
    assert vpn_session.expires_at == NOW + timedelta(minutes=15)
    assert capacity_repository.lock_requests == 1
