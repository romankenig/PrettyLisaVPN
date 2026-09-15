"""Replaceable, provider-neutral concrete-node ranking strategies."""

from collections.abc import Sequence
from fractions import Fraction
from typing import Protocol

from prettylisavpn.vpn_nodes.availability import VpnNodeCapacitySnapshot


class NodeSelectionStrategy(Protocol):
    """Select one candidate without exposing ranks or scores outside the control plane."""

    def select(self, candidates: Sequence[VpnNodeCapacitySnapshot]) -> VpnNodeCapacitySnapshot: ...


class LeastLoadedNodeSelectionStrategy:
    """Prefer lowest utilization, then greatest headroom, then stable node UUID."""

    def select(self, candidates: Sequence[VpnNodeCapacitySnapshot]) -> VpnNodeCapacitySnapshot:
        if not candidates:
            raise ValueError("candidates must not be empty")
        return min(
            candidates,
            key=lambda candidate: (
                Fraction(candidate.live_sessions, candidate.node.capacity),
                -candidate.remaining_capacity,
                str(candidate.node.id),
            ),
        )
