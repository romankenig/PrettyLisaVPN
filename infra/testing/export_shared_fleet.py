"""Forced-command exporter run inside the owner backend; SELECT-only, no account data."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from ipaddress import IPv4Interface

from sqlalchemy import select, text

from prettylisavpn.client_vpn.model import ClientLeaseRecord
from prettylisavpn.config import Settings
from prettylisavpn.connections import Postgres
from prettylisavpn.fleet.method_check_model import MethodCheckRecord
from prettylisavpn.fleet.model import FleetMethodRecord, FleetNodeRecord, FleetObservationRecord

NODE_FIELDS = (
    "id",
    "name",
    "country_code",
    "host",
    "credential_ref",
    "expected_egress_ips",
    "capacity",
    "is_available_for_free",
    "group",
    "enabled",
    "created_at",
)
METHOD_FIELDS = ("node_id", "method", "configuration", "state", "public_key", "configured_at")
OBSERVATION_FIELDS = (
    "id",
    "operation_id",
    "node_id",
    "source_id",
    "method",
    "observed_at",
    "data",
    "quality",
)


def fields(row, names):
    return {name: getattr(row, name) for name in names}


async def main():
    database = Postgres(Settings())
    now = datetime.now(UTC)
    try:
        async with database.session() as session, session.begin():
            await session.execute(text("SET TRANSACTION READ ONLY"))
            nodes = (await session.scalars(select(FleetNodeRecord))).all()
            methods = (await session.scalars(select(FleetMethodRecord))).all()
            observations = (
                await session.scalars(
                    select(FleetObservationRecord)
                    .where(
                        FleetObservationRecord.observed_at >= now - timedelta(hours=24),
                        FleetObservationRecord.observed_at <= now,
                    )
                    .order_by(FleetObservationRecord.observed_at)
                )
            ).all()
            leases = (
                await session.scalars(
                    select(ClientLeaseRecord).where(ClientLeaseRecord.removed_at.is_(None))
                )
            ).all()
            reservations = (
                await session.scalars(
                    select(MethodCheckRecord.relay_port).where(
                        MethodCheckRecord.reserved_until > now
                    )
                )
            ).all()
            safe = (
                all(n.capacity <= 100 for n in nodes)
                and all(
                    IPv4Interface(str(m.configuration["address"])).network.prefixlen == 24
                    for m in methods
                    if m.method == "wireguard"
                )
                and all(
                    (not row.address or int(IPv4Interface(row.address).ip) % 256 < 128)
                    and (not row.engine_port or row.engine_port < 48000)
                    and (not row.relay_port or row.relay_port < 28000)
                    for row in leases
                )
                and not any(port and 28000 <= port < 28500 for port in reservations)
            )
            result = {
                "generated_at": now,
                "safe_resources": safe,
                "nodes": [fields(n, NODE_FIELDS) for n in nodes],
                "methods": [fields(m, METHOD_FIELDS) for m in methods],
                "observations": [fields(o, OBSERVATION_FIELDS) for o in observations],
            }
            payload = json.dumps(result, default=str)
            if len(payload.encode()) > 1000000:
                raise ValueError("Snapshot exceeds bound")
            print(payload)
    finally:
        await database.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        print(json.dumps({"error": "FLEET_SNAPSHOT_UNAVAILABLE"}))
