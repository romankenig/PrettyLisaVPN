"""Traffic accounting primitives. Only counter deltas, never destinations or packets.

Five-second UTC windows merge all selected connections before applying the
directional threshold. Bytes are apportioned uniformly within a measured interval;
overlapping connection durations form a union, not device-seconds.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from statistics import median
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_GAP = 7.5
PERIODS = {"1h": (3600, 60), "24h": (86400, 300), "7d": (604800, 3600)}


class Counter(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    lease_id: UUID
    epoch: str = Field(min_length=1, max_length=160)
    at: float = Field(gt=0)
    monotonic: float = Field(ge=0)
    download: int = Field(ge=0, le=2**63 - 1, strict=True)
    upload: int = Field(ge=0, le=2**63 - 1, strict=True)


class Snapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    at: float = Field(gt=0)
    monotonic: float = Field(ge=0)
    boot: str = Field(min_length=1, max_length=64)
    complete: bool
    counters: list[Counter] = Field(max_length=10000)

    @model_validator(mode="after")
    def unique_connections(self) -> "Snapshot":
        if len({row.lease_id for row in self.counters}) != len(self.counters):
            raise ValueError("Duplicate connection")
        if any(not 0 <= self.at - row.at <= MAX_GAP for row in self.counters):
            raise ValueError("Stale connection counter")
        return self


def elapsed(before_at: float, after_at: float, before_mono: float, after_mono: float) -> bool:
    wall, actual = after_at - before_at, after_mono - before_mono
    return 0 < actual <= MAX_GAP and 0 < wall <= MAX_GAP and abs(wall - actual) < 0.5


def intervals(
    previous: Snapshot | None, current: Snapshot, owners: dict[UUID, UUID]
) -> tuple[list[dict[str, Any]], bool]:
    """A new epoch/reset/gap establishes a baseline; it never becomes traffic."""
    if (
        previous is None
        or previous.boot != current.boot
        or not elapsed(previous.at, current.at, previous.monotonic, current.monotonic)
    ):
        return [], False
    prior = {row.lease_id: row for row in previous.counters}
    present = {row.lease_id for row in current.counters}
    complete = current.complete and previous.complete and present == set(prior)
    result = []
    for row in current.counters:
        old, owner = prior.get(row.lease_id), owners.get(row.lease_id)
        if (
            owner is None
            or old is None
            or row.epoch != old.epoch
            or not elapsed(old.at, row.at, old.monotonic, row.monotonic)
            or row.download < old.download
            or row.upload < old.upload
        ):
            complete = False
            continue
        result.append(
            {
                "user": str(owner),
                "start": old.at,
                "end": row.at,
                "download": row.download - old.download,
                "upload": row.upload - old.upload,
            }
        )
    return result, complete


def union_seconds(spans: list[tuple[float, float]]) -> float:
    end, total = float("-inf"), 0.0
    for left, right in sorted(spans):
        total += max(0, right - max(left, end))
        end = max(end, right)
    return total


@dataclass
class Window:
    spans: list[tuple[float, float]] = field(default_factory=list)
    download: float = 0
    upload: float = 0


class TrafficRollup:
    """Stream ordered interval batches; retain at most a few five-second windows.

    Per-output-bucket user byte/second sums retain exact medians across time and
    servers. No ready-made server means or medians enter these calculations.
    """

    def __init__(self, start: int, end: int, step: int, nodes: list[str], threshold: float):
        self.start, self.end, self.step = start, end, step
        self.nodes, self.threshold = nodes, threshold
        self.windows: dict[int, dict[str, Window]] = defaultdict(dict)
        self.users: dict[int, dict[str, list[float]]] = defaultdict(dict)
        self.coverage: dict[int, dict[str, list[tuple[float, float]]]] = defaultdict(dict)

    def add(
        self, node: str, data: list[dict[str, Any]], start: float, end: float, complete: bool
    ) -> None:
        if node not in self.nodes:
            return
        if complete:
            for bucket, left, right in self.parts(start, end, self.step):
                self.coverage[bucket].setdefault(node, []).append((left, right))
        for row in data:
            for slot, left, right in self.parts(row["start"], row["end"], 5):
                window = self.windows[slot].setdefault(row["user"], Window())
                fraction = (right - left) / (row["end"] - row["start"])
                window.spans.append((left, right))
                window.download += row["download"] * fraction
                window.upload += row["upload"] * fraction

    def parts(self, start: float, end: float, step: int) -> list[tuple[int, float, float]]:
        start, end = max(self.start, start), min(self.end, end)
        result = []
        slot = int(start // step) * step
        while slot < end:
            result.append((slot, max(slot, start), min(slot + step, end)))
            slot += step
        return result

    def flush(self, before: float) -> None:
        for slot in sorted(list(self.windows)):
            if slot + 5 > before:
                break
            bucket = slot // self.step * self.step
            for user, window in self.windows.pop(slot).items():
                seconds = union_seconds(window.spans)
                for offset, traffic in ((0, window.download), (2, window.upload)):
                    if seconds and traffic * 8 / seconds > self.threshold:
                        sums = self.users[bucket].setdefault(user, [0.0] * 4)
                        sums[offset] += traffic
                        sums[offset + 1] += seconds

    def points(self) -> list[dict[str, Any]]:
        self.flush(float("inf"))
        points = []
        for bucket in range(self.start, self.end, self.step):
            directions: dict[str, Any] = {}
            for direction, offset in (("download", 0), ("upload", 2)):
                values = [v for v in self.users.get(bucket, {}).values() if v[offset + 1] > 0]
                traffic = sum(v[offset] for v in values)
                seconds = sum(v[offset + 1] for v in values)
                directions[direction] = {
                    "bytes": traffic,
                    "active_seconds": seconds,
                    "mean_mbps": traffic * 8 / seconds / 1e6 if seconds else None,
                    "median_mbps": median(v[offset] * 8 / v[offset + 1] / 1e6 for v in values)
                    if values
                    else None,
                    "active_users": len(values),
                }
            coverage = {
                node: union_seconds(spans) for node, spans in self.coverage.get(bucket, {}).items()
            }
            points.append(
                {
                    "at": datetime.fromtimestamp(bucket, UTC).isoformat(),
                    **directions,
                    "coverage": {
                        "expected_servers": len(self.nodes),
                        "complete_servers": sum(
                            seconds >= self.step - 0.01 for seconds in coverage.values()
                        ),
                        "reporting_servers": len(coverage),
                        "fraction": sum(coverage.values()) / (self.step * len(self.nodes))
                        if self.nodes
                        else None,
                        "server_seconds": coverage,
                    },
                }
            )
        return points
