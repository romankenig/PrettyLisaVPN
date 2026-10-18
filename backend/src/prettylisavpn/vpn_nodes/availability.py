"""Effective VPN node availability policy, independent of ORM mappings."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from prettylisavpn.subscriptions.domain import SubscriptionPlan
from prettylisavpn.subscriptions.entitlements import entitlements_for_plan
from prettylisavpn.vpn_nodes.domain import VpnNode, VpnNodeHealthStatus, VpnNodeStatus


class NodeUnavailabilityReason(StrEnum):
    NO_RUNNABLE_PROFILE = "NO_RUNNABLE_PROFILE"
    ADMINISTRATIVE_STATUS = "ADMINISTRATIVE_STATUS"
    NOT_HEALTHY = "NOT_HEALTHY"
    NEVER_SEEN = "NEVER_SEEN"
    STALE = "STALE"
    PLAN_RESTRICTED = "PLAN_RESTRICTED"
    CAPACITY_EXHAUSTED = "CAPACITY_EXHAUSTED"


@dataclass(frozen=True, slots=True)
class NodeAvailability:
    available: bool
    reason: NodeUnavailabilityReason | None


@dataclass(frozen=True, slots=True)
class VpnNodeCapacitySnapshot:
    node: VpnNode
    live_sessions: int

    def __post_init__(self) -> None:
        if self.live_sessions < 0:
            raise ValueError("live_sessions must not be negative")

    @property
    def remaining_capacity(self) -> int:
        return max(0, self.node.capacity - self.live_sessions)


class VpnNodeAvailabilityPolicy:
    def __init__(self, stale_timeout: timedelta) -> None:
        if stale_timeout <= timedelta(0):
            raise ValueError("stale_timeout must be positive")
        self._stale_timeout = stale_timeout

    def evaluate(self, node: VpnNode, now: datetime) -> NodeAvailability:
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now must be timezone-aware")
        if not node.supports_current_session_protocol:
            return NodeAvailability(False, NodeUnavailabilityReason.NO_RUNNABLE_PROFILE)
        if node.deployed_profiles and node.verified_wireguard_session_profile(now) is None:
            return NodeAvailability(False, NodeUnavailabilityReason.NO_RUNNABLE_PROFILE)
        if node.status is not VpnNodeStatus.ACTIVE:
            return NodeAvailability(False, NodeUnavailabilityReason.ADMINISTRATIVE_STATUS)
        if node.health_status is not VpnNodeHealthStatus.HEALTHY:
            return NodeAvailability(False, NodeUnavailabilityReason.NOT_HEALTHY)
        if node.last_seen_at is None:
            return NodeAvailability(False, NodeUnavailabilityReason.NEVER_SEEN)
        if now - node.last_seen_at > self._stale_timeout:
            return NodeAvailability(False, NodeUnavailabilityReason.STALE)
        return NodeAvailability(True, None)


class VpnNodeEligibilityPolicy:
    """Single plan, health, lifecycle, freshness, and capacity policy."""

    def __init__(self, stale_timeout: timedelta) -> None:
        self._availability = VpnNodeAvailabilityPolicy(stale_timeout)

    def evaluate(
        self,
        snapshot: VpnNodeCapacitySnapshot,
        plan: SubscriptionPlan,
        now: datetime,
    ) -> NodeAvailability:
        operational = self._availability.evaluate(snapshot.node, now)
        if not operational.available:
            return operational
        if entitlements_for_plan(plan).free_nodes_only and not snapshot.node.is_available_for_free:
            return NodeAvailability(False, NodeUnavailabilityReason.PLAN_RESTRICTED)
        if snapshot.remaining_capacity == 0:
            return NodeAvailability(False, NodeUnavailabilityReason.CAPACITY_EXHAUSTED)
        return NodeAvailability(True, None)
