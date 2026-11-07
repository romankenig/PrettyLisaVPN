"""Read-only traffic projection and idempotent storage behind fleet authorization."""

from datetime import UTC, datetime, timedelta
from statistics import median
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert

from prettylisavpn.config import Settings
from prettylisavpn.connections import Postgres
from prettylisavpn.fleet.domain import FleetError
from prettylisavpn.fleet.model import FleetNodeRecord, FleetObservationRecord
from prettylisavpn.fleet.traffic import MAX_GAP, PERIODS, Snapshot, TrafficRollup, intervals
from prettylisavpn.fleet.traffic_model import TrafficCursorRecord, TrafficIntervalRecord


class TrafficService:
    def __init__(self, postgres: Postgres, settings: Settings):
        self.postgres, self.settings = postgres, settings

    async def ingest(
        self, node_id: UUID, sample: Snapshot, owners: dict[UUID, UUID], now: datetime
    ) -> bool:
        if abs(sample.at - now.timestamp()) > MAX_GAP:
            raise FleetError("traffic_clock_skew")
        async with self.postgres.session() as session, session.begin():
            # ON CONFLICT plus the row lock fences overlapping collectors/retries.
            await session.execute(
                insert(TrafficCursorRecord)
                .values(node_id=node_id, data={})
                .on_conflict_do_nothing()
            )
            cursor = await session.get(TrafficCursorRecord, node_id, with_for_update=True)
            assert cursor is not None
            previous = Snapshot.model_validate(cursor.data) if cursor.data else None
            if previous is not None and sample.at <= previous.at:
                return False
            data, complete = intervals(previous, sample, owners)
            session.add(
                TrafficIntervalRecord(
                    node_id=node_id,
                    end_at=datetime.fromtimestamp(sample.at, UTC),
                    start_at=datetime.fromtimestamp(
                        previous.at
                        if previous and sample.at - previous.at <= MAX_GAP
                        else sample.at,
                        UTC,
                    ),
                    complete=complete,
                    data=data,
                )
            )
            cursor.data = sample.model_dump(mode="json")
        return True

    async def prune(self, now: datetime) -> None:
        async with self.postgres.session() as session, session.begin():
            await session.execute(
                delete(TrafficIntervalRecord).where(
                    TrafficIntervalRecord.end_at < now - timedelta(days=8)
                )
            )
            # Stopped nodes must not retain connection identifiers indefinitely.
            await session.execute(
                delete(TrafficCursorRecord).where(
                    TrafficCursorRecord.data["at"].as_float()
                    < (now - timedelta(days=8)).timestamp()
                )
            )

    async def history(
        self, period: str, node_ids: list[UUID] | None, now: datetime | None = None
    ) -> dict[str, Any]:
        now = now or datetime.now(UTC)
        duration, step = PERIODS[period]
        # Completed minutes only, including the current partial five-minute/hour
        # block. Allow both counter age and collection interval before finalizing.
        end = int((now.timestamp() - 2 * MAX_GAP) // 60) * 60
        start = end - duration
        async with self.postgres.session() as session, session.begin():
            await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
            await session.execute(text("SET LOCAL statement_timeout = '25s'"))
            nodes = list(
                (
                    await session.scalars(select(FleetNodeRecord).where(FleetNodeRecord.enabled))
                ).all()
            )
            if node_ids is not None:
                if set(node_ids) - {node.id for node in nodes}:
                    raise FleetError("traffic_node_not_found", 404)
                nodes = [node for node in nodes if node.id in node_ids]
            exits = [node for node in nodes if node.group != "INTERMEDIATE"]
            ids = [node.id for node in exits]
            rollup = TrafficRollup(
                start,
                end,
                step,
                [str(node) for node in ids],
                self.settings.fleet_activity_threshold_bps,
            )
            rows = await session.stream_scalars(
                select(TrafficIntervalRecord)
                .where(
                    TrafficIntervalRecord.node_id.in_(ids),
                    TrafficIntervalRecord.end_at > datetime.fromtimestamp(start, UTC),
                    TrafficIntervalRecord.end_at < datetime.fromtimestamp(end + 2 * MAX_GAP, UTC),
                )
                .order_by(TrafficIntervalRecord.end_at)
                .execution_options(yield_per=500)
            )
            async for row in rows:
                rollup.add(
                    str(row.node_id),
                    row.data,
                    row.start_at.timestamp(),
                    row.end_at.timestamp(),
                    row.complete,
                )
                # A connection snapshot may lag its enclosing poll by MAX_GAP.
                rollup.flush(row.end_at.timestamp() - 2 * MAX_GAP)
            points = rollup.points()
            observations = (
                await session.scalars(
                    select(FleetObservationRecord)
                    .where(
                        FleetObservationRecord.node_id.in_(ids),
                        FleetObservationRecord.observed_at >= datetime.fromtimestamp(start, UTC),
                        FleetObservationRecord.observed_at < datetime.fromtimestamp(end, UTC),
                    )
                    .order_by(FleetObservationRecord.observed_at)
                )
            ).all()
            references: dict[int, dict[UUID, dict[str, object]]] = {}
            for observation in observations:
                if observation.data.get("mode") == "SYNTHETIC":
                    bucket = int(observation.observed_at.timestamp() // step) * step
                    references.setdefault(bucket, {})[observation.node_id] = observation.data
            for point in points:
                bucket = int(datetime.fromisoformat(point["at"]).timestamp() // step) * step
                reference = references.get(bucket, {})
                for direction in ("download", "upload"):
                    values = [
                        float(value)
                        for row in reference.values()
                        if isinstance(value := row.get(direction + "_mbps"), (float, int))
                        and value >= 0
                    ]
                    measured = median(values) if values else None
                    point[direction].update(reference_mbps=measured, reference_servers=len(values))
                    # Do not compare partial and full populations or divide by zero.
                    point[direction]["reference_percent"] = (
                        point[direction]["mean_mbps"] / measured * 100
                        if measured
                        and len(values) == len(ids)
                        and point["coverage"]["complete_servers"] == len(ids)
                        and point[direction]["mean_mbps"] is not None
                        else None
                    )
            return {
                "generated_at": now,
                "period": period,
                "bucket_seconds": step,
                "activity_threshold_bps": self.settings.fleet_activity_threshold_bps,
                "sample_seconds": 5,
                "max_gap_seconds": MAX_GAP,
                "nodes": [{"id": str(node.id), "name": node.name} for node in exits],
                "excluded_transit_nodes": [
                    str(node.id) for node in nodes if node.group == "INTERMEDIATE"
                ],
                "points": points,
            }
