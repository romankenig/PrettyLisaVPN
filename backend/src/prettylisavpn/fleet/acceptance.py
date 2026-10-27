"""Server-run acceptance report. No Codex/ChatGPT scheduler or callback is required."""

import argparse
import asyncio
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from prettylisavpn.config import Settings
from prettylisavpn.connections import Postgres
from prettylisavpn.fleet.model import (
    FleetMethodRecord,
    FleetNodeRecord,
    FleetObservationRecord,
    FleetOperationRecord,
)


def assess(expected: int, observations: list[dict[str, Any]], incomplete: int) -> dict[str, Any]:
    healthy = sum(
        item["status"] == "HEALTHY" and item.get("cleanup_confirmed", True) for item in observations
    )
    return {
        "passed": expected > 0
        and healthy >= expected
        and healthy == len(observations)
        and incomplete == 0,
        "expected_checks": expected,
        "observed_checks": len(observations),
        "healthy_checks": healthy,
        "incomplete_operations": incomplete,
        "full_checks": sum(item["mode"] == "SYNTHETIC" for item in observations),
        "passive_checks": sum(item["mode"] == "PASSIVE" for item in observations),
        "failure_codes": sorted(
            {
                item["code"]
                for item in observations
                if item["status"] != "HEALTHY" or not item.get("cleanup_confirmed", True)
            }
        ),
    }


async def report(postgres: Postgres, since: datetime, until: datetime) -> dict[str, Any]:
    if since.tzinfo is None or until.tzinfo is None or until <= since or until > datetime.now(UTC):
        raise ValueError("A completed UTC observation interval is required")
    async with postgres.session() as session:
        nodes = (
            await session.scalars(
                select(FleetNodeRecord)
                .where(FleetNodeRecord.enabled.is_(True))
                .order_by(FleetNodeRecord.name)
            )
        ).all()
        methods = {
            row.node_id: row
            for row in (
                await session.scalars(
                    select(FleetMethodRecord).where(
                        FleetMethodRecord.method == "wireguard",
                        FleetMethodRecord.configured_at.is_not(None),
                    )
                )
            ).all()
        }
        jobs = (
            await session.scalars(
                select(FleetOperationRecord).where(
                    FleetOperationRecord.kind == "CHECK",
                    FleetOperationRecord.request_key.startswith("hour:"),
                    FleetOperationRecord.created_at >= since,
                    FleetOperationRecord.created_at < until,
                )
            )
        ).all()
        observations = {
            row.operation_id: row.data
            for row in (
                await session.scalars(
                    select(FleetObservationRecord).where(
                        FleetObservationRecord.operation_id.in_([job.id for job in jobs])
                    )
                )
            ).all()
        }
    rows = []
    for node in nodes:
        method = methods.get(node.id)
        if method is None or method.configured_at is None or method.configured_at >= until:
            continue
        expected = max(0, int((until - max(since, method.configured_at)).total_seconds() // 3600))
        selected = [job for job in jobs if job.node_id == node.id]
        evidence = [observations[job.id] for job in selected if job.id in observations]
        result = assess(expected, evidence, sum(job.id not in observations for job in selected))
        rows.append(
            {
                "node_id": str(node.id),
                "name": node.name,
                "country_code": node.country_code,
                **result,
            }
        )
    return {
        "since": since.isoformat(),
        "until": until.isoformat(),
        "generated_at": datetime.now(UTC).isoformat(),
        "passed": bool(rows) and all(row["passed"] for row in rows),
        "nodes": rows,
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only scheduled fleet acceptance report")
    parser.add_argument("--since", required=True)
    parser.add_argument("--until", required=True)
    args = parser.parse_args()
    postgres = Postgres(Settings())
    try:
        value = await report(
            postgres, datetime.fromisoformat(args.since), datetime.fromisoformat(args.until)
        )
        print(json.dumps(value))
    finally:
        await postgres.close()


if __name__ == "__main__":
    asyncio.run(main())
