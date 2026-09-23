"""Import trusted operator E2E evidence. No public capability-write endpoint.

python -m prettylisavpn.vpn_nodes.import_profiles path/to/deployment.json
The deployment file contains node_id and profiles (DeployedConnectionProfile[]).
Keep this command restricted to trusted operators: JSON itself is not attestation.
"""

import argparse
import asyncio
import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from prettylisavpn.config import Settings
from prettylisavpn.vpn_nodes.deployment import DeployedConnectionProfile, ProfileHealth
from prettylisavpn.vpn_nodes.domain import VpnNode
from prettylisavpn.vpn_nodes.repository import VpnNodeRepository


class DeploymentImport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    node_id: UUID
    profiles: tuple[DeployedConnectionProfile, ...]


def validate_import(node: VpnNode, payload: DeploymentImport, now: datetime) -> VpnNode:
    if payload.node_id != node.id:
        raise ValueError("node identity mismatch")
    for profile in payload.profiles:
        if profile.health_status is ProfileHealth.E2E_VERIFIED and not profile.usable(
            node.id, node.public_ipv4, now
        ):
            raise ValueError("invalid or expired E2E evidence")
    return replace(node, deployed_profiles=payload.profiles, updated_at=now)


async def import_file(path: Path) -> None:
    payload = DeploymentImport.model_validate_json(await asyncio.to_thread(path.read_text))
    engine = create_async_engine(Settings().postgres_url.get_secret_value())
    try:
        async with async_sessionmaker(engine)() as session, session.begin():
            repo = VpnNodeRepository(session)
            node = await repo.get(payload.node_id)
            if node is None:
                raise ValueError("unknown node")
            await repo.update_deployed_profiles(validate_import(node, payload, datetime.now(UTC)))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("file", type=Path)
    args = parser.parse_args()
    try:
        asyncio.run(import_file(args.file))
    except Exception:
        print(json.dumps({"event": "profile_import_failed"}))
        raise SystemExit(1) from None
    print(json.dumps({"event": "profile_import_succeeded"}))
