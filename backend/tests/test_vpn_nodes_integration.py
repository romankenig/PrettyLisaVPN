"""VPN node persistence tests against local Compose PostgreSQL or CI."""

import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from ipaddress import IPv4Address
from uuid import uuid4

import pytest
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError

from prettylisavpn.config import Settings
from prettylisavpn.connections import Postgres
from prettylisavpn.vpn_nodes.domain import (
    VpnNode,
    VpnNodeHealthStatus,
    VpnNodeProvider,
    VpnNodeStatus,
)
from prettylisavpn.vpn_nodes.model import VpnNodeRecord
from prettylisavpn.vpn_nodes.profiles import NodeConnectionProfile, ProfileId
from prettylisavpn.vpn_nodes.repository import VpnNodeRepository

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1",
        reason="Set RUN_INTEGRATION_TESTS=1 with PostgreSQL running",
    ),
]


def make_node(**changes: object) -> VpnNode:
    now = datetime.now(UTC)
    node = VpnNode(
        id=uuid4(),
        name=f"vpn-node-{uuid4()}",
        provider=VpnNodeProvider.DIGITALOCEAN,
        provider_region="fra1",
        country_code="DE",
        city="Frankfurt",
        public_ipv4=IPv4Address("203.0.113.20"),
        private_ipv4=IPv4Address("10.116.0.3"),
        wireguard_port=51820,
        wireguard_public_key="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
        capacity=250,
        status=VpnNodeStatus.ACTIVE,
        last_seen_at=now,
        created_at=now,
        updated_at=now,
    )
    return replace(node, **changes)


async def delete_nodes(postgres: Postgres, *node_ids) -> None:
    async with postgres.session() as session:
        await session.execute(delete(VpnNodeRecord).where(VpnNodeRecord.id.in_(node_ids)))
        await session.commit()


async def test_round_trip_list_and_update_control_plane_metadata():
    postgres = Postgres(Settings())
    node = make_node(
        provider=VpnNodeProvider.NETCUP,
        provider_region="nuremberg",
        city="Nuremberg",
        connection_profiles=(
            NodeConnectionProfile(profile=ProfileId.WIREGUARD_UDP, ports=(51820,)),
            NodeConnectionProfile(profile=ProfileId.OPENVPN_TLS_TCP, ports=(443,)),
            NodeConnectionProfile(profile=ProfileId.MASQUE_QUIC, ports=(443,)),
        ),
        public_ipv4=IPv4Address("5.181.49.183"),
    )
    try:
        async with postgres.session() as session:
            created = await VpnNodeRepository(session).add(node)
            await session.commit()

        assert created == node
        async with postgres.session() as session:
            repository = VpnNodeRepository(session)
            assert await repository.get(node.id) == node
            assert await repository.get_by_name(f"  {node.name}  ") == node
            assert node in await repository.list_all()

            updated = replace(
                node,
                status=VpnNodeStatus.DRAINING,
                health_status=VpnNodeHealthStatus.HEALTHY,
                capacity=200,
                connection_profiles=(),
                is_available_for_free=True,
                last_seen_at=node.last_seen_at + timedelta(seconds=30),
                health_checked_at=node.updated_at + timedelta(seconds=30),
                updated_at=node.updated_at + timedelta(seconds=30),
            )
            assert await repository.update(updated) == updated
            await session.commit()

        async with postgres.session() as session:
            repository = VpnNodeRepository(session)
            assert await repository.get(node.id) == updated
            health_checked_at = node.updated_at + timedelta(seconds=60)
            health_updated = await repository.update_health(
                node.id,
                VpnNodeHealthStatus.UNHEALTHY,
                health_checked_at,
                updated.last_seen_at,
            )
            await session.commit()

            assert health_updated is not None
            assert health_updated.status is VpnNodeStatus.DRAINING
            assert health_updated.capacity == 200
            assert health_updated.is_available_for_free is True
            assert health_updated.health_status is VpnNodeHealthStatus.UNHEALTHY
            assert health_updated.health_checked_at == health_checked_at
    finally:
        await delete_nodes(postgres, node.id)
        await postgres.close()


@pytest.mark.parametrize(
    "duplicate_field",
    ["name", "public_endpoint", "wireguard_public_key"],
)
async def test_unique_node_identity_constraints(duplicate_field: str):
    postgres = Postgres(Settings())
    first = make_node()
    second_changes: dict[str, object] = {
        "name": f"vpn-node-{uuid4()}",
        "public_ipv4": IPv4Address("203.0.113.21"),
        "wireguard_public_key": "AQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
    }
    if duplicate_field == "name":
        second_changes["name"] = first.name
    elif duplicate_field == "public_endpoint":
        second_changes["public_ipv4"] = first.public_ipv4
    else:
        second_changes["wireguard_public_key"] = first.wireguard_public_key
    second = make_node(**second_changes)
    try:
        async with postgres.session() as session:
            await VpnNodeRepository(session).add(first)
            await session.commit()

        with pytest.raises(IntegrityError):
            async with postgres.session() as session:
                await VpnNodeRepository(session).add(second)
    finally:
        await delete_nodes(postgres, first.id, second.id)
        await postgres.close()


async def test_database_rejects_invalid_capacity_outside_domain_layer():
    postgres = Postgres(Settings())
    node = make_node()
    try:
        with pytest.raises(IntegrityError):
            async with postgres.session() as session:
                session.add(
                    VpnNodeRecord(
                        id=node.id,
                        name=node.name,
                        provider=node.provider,
                        provider_region=node.provider_region,
                        country_code=node.country_code,
                        city=node.city,
                        public_ipv4=node.public_ipv4,
                        private_ipv4=node.private_ipv4,
                        wireguard_port=node.wireguard_port,
                        wireguard_public_key=node.wireguard_public_key,
                        capacity=0,
                        status=node.status,
                        last_seen_at=node.last_seen_at,
                        created_at=node.created_at,
                        updated_at=node.updated_at,
                    )
                )
                await session.flush()
    finally:
        await delete_nodes(postgres, node.id)
        await postgres.close()


def test_schema_has_no_private_key_or_provider_token_columns():
    column_names = set(VpnNodeRecord.__table__.columns.keys())

    assert "wireguard_private_key" not in column_names
    assert "provider_token" not in column_names
    assert "digitalocean_token" not in column_names
