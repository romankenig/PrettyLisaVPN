"""Durable API operations and read-only fleet projections."""

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError

from prettylisavpn.config import Settings
from prettylisavpn.connections import Postgres
from prettylisavpn.fleet.domain import (
    FleetError,
    ManagedConfig,
    Node,
    NodeInput,
    NodeUpdate,
    Observation,
    WireGuardConfig,
    server_quality,
)
from prettylisavpn.fleet.model import (
    FleetMethodRecord,
    FleetNodeRecord,
    FleetObservationRecord,
    FleetOperationRecord,
)


def node_value(row: FleetNodeRecord) -> Node:
    return Node.model_validate({field: getattr(row, field) for field in Node.model_fields})


def operation_view(row: FleetOperationRecord) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "node_id": str(row.node_id),
        "method": row.method,
        "kind": row.kind,
        "status": row.status,
        "result": row.result,
        "created_at": row.created_at,
        "started_at": row.started_at,
        "finished_at": row.finished_at,
        "attempts": row.attempts,
    }


def bucket_status(items: list[Observation]) -> str:
    for status in ("FAILED", "DEGRADED", "HEALTHY"):
        if any(item.status == status for item in items):
            return status
    return "UNKNOWN"


class FleetService:
    def __init__(self, postgres: Postgres, settings: Settings) -> None:
        self.postgres, self.settings = postgres, settings

    async def register(self, data: NodeInput) -> dict[str, Any]:
        values = data.model_dump(mode="json")
        async with self.postgres.session() as session, session.begin():
            existing = await session.scalar(
                select(FleetNodeRecord).where(
                    or_(
                        FleetNodeRecord.host == str(data.host),
                        FleetNodeRecord.name == data.name,
                    )
                )
            )
            if existing is not None:
                if any(getattr(existing, key) != value for key, value in values.items()):
                    raise FleetError("fleet_node_conflict")
                return node_value(existing).model_dump(mode="json")
            row = FleetNodeRecord(**values)
            session.add(row)
            try:
                await session.flush()
            except IntegrityError:
                raise FleetError("fleet_node_conflict") from None
            return node_value(row).model_dump(mode="json")

    async def nodes(self) -> list[dict[str, Any]]:
        async with self.postgres.session() as session:
            rows = (
                await session.scalars(select(FleetNodeRecord).order_by(FleetNodeRecord.name))
            ).all()
            return [node_value(row).model_dump(mode="json") for row in rows]

    async def update_node(self, identifier: UUID, data: NodeUpdate) -> dict[str, Any]:
        from prettylisavpn.client_vpn.model import ClientLeaseRecord

        async with self.postgres.session() as session, session.begin():
            row = await session.get(FleetNodeRecord, identifier, with_for_update=True)
            if row is None:
                raise FleetError("fleet_node_not_found", 404)
            if row.group != data.group and await session.scalar(
                select(ClientLeaseRecord.id)
                .where(
                    or_(
                        ClientLeaseRecord.node_id == identifier,
                        ClientLeaseRecord.relay_node_id == identifier,
                    ),
                    ClientLeaseRecord.removed_at.is_(None),
                )
                .limit(1)
            ):
                raise FleetError("fleet_node_has_active_access")
            row.name, row.group = data.name, data.group
            if data.capacity is not None:
                row.capacity = data.capacity
            row.is_available_for_free = data.group == "FREE"
            try:
                await session.flush()
            except IntegrityError:
                raise FleetError("fleet_node_conflict") from None
            return node_value(row).model_dump(mode="json")

    async def enqueue(
        self,
        node_id: UUID,
        method: str,
        kind: str,
        request_key: UUID,
        config: WireGuardConfig | ManagedConfig | None = None,
    ) -> dict[str, Any]:
        if method not in ("wireguard", "managed"):
            raise FleetError("fleet_method_unsupported", 422)
        if method == "managed" and self.settings.managed_vpn_secret is None:
            raise FleetError("fleet_method_unavailable", 503)
        if kind == "CONFIGURE" and not isinstance(
            config, WireGuardConfig if method == "wireguard" else ManagedConfig
        ):
            raise FleetError("fleet_configuration_invalid", 422)
        parameters = config.model_dump(mode="json") if config is not None else {}
        async with self.postgres.session() as session, session.begin():
            node = await session.get(FleetNodeRecord, node_id, with_for_update=True)
            if node is None:
                raise FleetError("fleet_node_not_found", 404)
            if not node.enabled:
                raise FleetError("fleet_node_disabled")
            existing = await session.scalar(
                select(FleetOperationRecord).where(
                    FleetOperationRecord.node_id == node_id,
                    FleetOperationRecord.kind == kind,
                    FleetOperationRecord.request_key == str(request_key),
                )
            )
            if existing is not None:
                if existing.method != method or existing.parameters != parameters:
                    raise FleetError("fleet_idempotency_conflict")
                return operation_view(existing)
            installed = await session.get(FleetMethodRecord, (node_id, method))
            if kind == "CHECK":
                if installed is None or installed.configured_at is None:
                    raise FleetError("fleet_method_not_configured")
                recent = await session.scalar(
                    select(FleetOperationRecord.id)
                    .where(
                        FleetOperationRecord.node_id == node_id,
                        FleetOperationRecord.kind == "CHECK",
                        FleetOperationRecord.created_at > datetime.now(UTC) - timedelta(minutes=5),
                    )
                    .limit(1)
                )
                if recent is not None:
                    raise FleetError("fleet_check_rate_limited", 429)
            if kind == "CONFIGURE" and installed is None:
                session.add(
                    FleetMethodRecord(node_id=node_id, method=method, configuration=parameters)
                )
            row = FleetOperationRecord(
                node_id=node_id,
                method=method,
                kind=kind,
                request_key=str(request_key),
                parameters=parameters,
            )
            session.add(row)
            await session.flush()
            return operation_view(row)

    async def operation(self, operation_id: UUID) -> dict[str, Any]:
        async with self.postgres.session() as session:
            row = await session.get(FleetOperationRecord, operation_id)
            if row is None:
                raise FleetError("fleet_operation_not_found", 404)
            return operation_view(row)

    async def monitoring(self, node_id: UUID | None = None, days: int = 7) -> dict[str, Any]:
        now = datetime.now(UTC)
        end_hour = now.replace(minute=0, second=0, microsecond=0)
        start = end_hour - timedelta(hours=days * 24 - 1)
        async with self.postgres.session() as session:
            query = select(FleetNodeRecord).where(FleetNodeRecord.enabled.is_(True))
            if node_id is not None:
                query = query.where(FleetNodeRecord.id == node_id)
            nodes = (await session.scalars(query.order_by(FleetNodeRecord.name))).all()
            if node_id is not None and not nodes:
                raise FleetError("fleet_node_not_found", 404)
            ids = [node.id for node in nodes]
            methods = {
                row.node_id: row
                for row in (
                    await session.scalars(
                        select(FleetMethodRecord).where(
                            FleetMethodRecord.node_id.in_(ids),
                            FleetMethodRecord.method == "wireguard",
                        )
                    )
                ).all()
            }
            rows = (
                await session.scalars(
                    select(FleetObservationRecord)
                    .where(
                        FleetObservationRecord.node_id.in_(ids),
                        FleetObservationRecord.method == "wireguard",
                        FleetObservationRecord.observed_at >= start,
                        FleetObservationRecord.observed_at <= now,
                    )
                    .order_by(FleetObservationRecord.observed_at)
                )
            ).all()
        by_node: dict[UUID, list[FleetObservationRecord]] = defaultdict(list)
        for row in rows:
            by_node[row.node_id].append(row)
        result: list[dict[str, Any]] = []
        total_expected = total_known = total_healthy = 0
        for node in nodes:
            records = by_node[node.id]
            observations = [Observation.model_validate(row.data) for row in records]
            method = methods.get(node.id)
            quality = server_quality(
                observations,
                node.capacity,
                now,
                speed_target_mbps=self.settings.fleet_speed_target_mbps,
                connection_target_ms=self.settings.fleet_connection_target_ms,
                quality_weights=self.settings.fleet_quality_weights,
            )
            if method is None or method.state != "READY":
                quality = {"quality": 0, "available": False, "confidence": "UNVERIFIED"}
            buckets: dict[datetime, list[Observation]] = defaultdict(list)
            measurements: dict[datetime, list[dict[str, Any]]] = defaultdict(list)
            for row, item in zip(records, observations, strict=True):
                measurements[item.observed_at.replace(minute=0, second=0, microsecond=0)].append(
                    {
                        "observed_at": item.observed_at,
                        "status": item.status,
                        "mode": item.mode,
                        "code": item.code,
                        "quality": row.quality,
                        "download_mbps": item.download_mbps,
                        "upload_mbps": item.upload_mbps,
                        "connection_ms": item.connection_ms,
                        "active_connections": item.active_connections,
                    }
                )
            for item in observations:
                buckets[item.observed_at.replace(minute=0, second=0, microsecond=0)].append(item)
            history = []
            expected = known = healthy = 0
            for index in range(days * 24):
                hour = start + timedelta(hours=index)
                registered = node.created_at < hour + timedelta(hours=1)
                values = buckets[hour]
                status = (
                    bucket_status(values)
                    if values
                    else (
                        "NOT_REGISTERED"
                        if not registered
                        else "PENDING"
                        if hour == end_hour
                        else "UNKNOWN"
                    )
                )
                if registered and hour < end_hour:
                    expected += 1
                    known += status in ("HEALTHY", "DEGRADED", "FAILED")
                    healthy += status == "HEALTHY"
                history.append(
                    {
                        "at": hour,
                        "status": status,
                        "modes": sorted({item.mode for item in values}),
                        "checks": len(values),
                        "measurements": measurements[hour],
                    }
                )
            total_expected += expected
            total_known += known
            total_healthy += healthy
            latest = observations[-1].model_dump(mode="json") if observations else None
            full = next(
                (
                    item
                    for item in reversed(observations)
                    if item.mode == "SYNTHETIC" and item.status == "HEALTHY"
                ),
                None,
            )
            result.append(
                {
                    "id": str(node.id),
                    "name": node.name,
                    "country_code": node.country_code,
                    "group": node.group,
                    "method": "wireguard",
                    "configuration_state": method.state if method else "REGISTERED",
                    "capacity": node.capacity,
                    "is_available_for_free": node.is_available_for_free,
                    **quality,
                    "latest": latest,
                    "latest_source_id": str(records[-1].source_id)
                    if records and records[-1].source_id
                    else None,
                    "last_full_check_at": full.observed_at if full else None,
                    "next_check_at": method.next_check_at if method else None,
                    "history": history,
                    "expected_hours": expected,
                    "known_hours": known,
                    "successful_hours": healthy,
                }
            )
        return {
            "generated_at": now,
            "window_start": start,
            "window_end": now,
            "timezone": "UTC",
            "nodes": result,
            "overall": {
                "servers": len(result),
                "available_servers": sum(bool(item["available"]) for item in result),
                "expected_hours": total_expected,
                "known_hours": total_known,
                "successful_hours": total_healthy,
                "availability_percent": round(100 * total_healthy / total_known, 2)
                if total_known
                else None,
                "coverage_percent": round(100 * total_known / total_expected, 2)
                if total_expected
                else None,
            },
        }

    async def countries(self, free_only: bool) -> dict[str, Any]:
        snapshot = await self.monitoring(days=1)
        by_country: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for node in snapshot["nodes"]:
            if node["group"] != "INTERMEDIATE" and (not free_only or node["is_available_for_free"]):
                by_country[node["country_code"]].append(node)
        countries = []
        for code, nodes in sorted(by_country.items()):
            denominator = sum(item["capacity"] for item in nodes)
            countries.append(
                {
                    "country_code": code,
                    "quality": round(
                        sum(item["quality"] * item["capacity"] for item in nodes) / denominator
                    ),
                    "available": any(item["available"] for item in nodes),
                }
            )
        return {
            "countries": countries,
            "autopilot": {
                "quality": max(
                    (item["quality"] for item in countries if item["available"]), default=0
                ),
                "available": any(item["available"] for item in countries),
            },
        }
