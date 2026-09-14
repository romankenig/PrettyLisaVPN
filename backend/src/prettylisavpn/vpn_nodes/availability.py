"""Effective VPN node availability policy, independent of ORM mappings."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from prettylisavpn.vpn_nodes.domain import VpnNode, VpnNodeHealthStatus, VpnNodeStatus


class NodeUnavailabilityReason(StrEnum):
    ADMINISTRATIVE_STATUS = "ADMINISTRATIVE_STATUS"
    NOT_HEALTHY = "NOT_HEALTHY"
    NEVER_SEEN = "NEVER_SEEN"
    STALE = "STALE"


@dataclass(frozen=True, slots=True)
class NodeAvailability:
    available: bool
    reason: NodeUnavailabilityReason | None


class VpnNodeAvailabilityPolicy:
    def __init__(self, stale_timeout: timedelta) -> None:
        if stale_timeout <= timedelta(0):
            raise ValueError("stale_timeout must be positive")
        self._stale_timeout = stale_timeout

    def evaluate(self, node: VpnNode, now: datetime) -> NodeAvailability:
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now must be timezone-aware")
        if node.status is not VpnNodeStatus.ACTIVE:
            return NodeAvailability(False, NodeUnavailabilityReason.ADMINISTRATIVE_STATUS)
        if node.health_status is not VpnNodeHealthStatus.HEALTHY:
            return NodeAvailability(False, NodeUnavailabilityReason.NOT_HEALTHY)
        if node.last_seen_at is None:
            return NodeAvailability(False, NodeUnavailabilityReason.NEVER_SEEN)
        if now - node.last_seen_at > self._stale_timeout:
            return NodeAvailability(False, NodeUnavailabilityReason.STALE)
        return NodeAvailability(True, None)
