"""Async persistence operations for VPN node metadata."""

from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from prettylisavpn.vpn_nodes.domain import VpnNode
from prettylisavpn.vpn_nodes.model import VpnNodeRecord


class VpnNodeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, node: VpnNode) -> VpnNode:
        record = VpnNodeRecord(
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
            capacity=node.capacity,
            status=node.status,
            last_seen_at=node.last_seen_at,
            created_at=node.created_at,
            updated_at=node.updated_at,
        )
        self._session.add(record)
        await self._session.flush()
        return self._to_domain(record)

    async def get(self, node_id: UUID) -> VpnNode | None:
        record = await self._session.get(VpnNodeRecord, node_id)
        return self._to_domain(record) if record is not None else None

    async def get_by_name(self, name: str) -> VpnNode | None:
        statement = select(VpnNodeRecord).where(VpnNodeRecord.name == name.strip())
        record = await self._session.scalar(statement)
        return self._to_domain(record) if record is not None else None

    async def list_all(self) -> list[VpnNode]:
        records = await self._session.scalars(
            select(VpnNodeRecord).order_by(VpnNodeRecord.created_at, VpnNodeRecord.id)
        )
        return [self._to_domain(record) for record in records]

    async def update(self, node: VpnNode) -> VpnNode:
        await self._session.execute(
            update(VpnNodeRecord)
            .where(VpnNodeRecord.id == node.id)
            .values(
                name=node.name,
                provider=node.provider,
                provider_region=node.provider_region,
                country_code=node.country_code,
                city=node.city,
                public_ipv4=node.public_ipv4,
                private_ipv4=node.private_ipv4,
                wireguard_port=node.wireguard_port,
                wireguard_public_key=node.wireguard_public_key,
                capacity=node.capacity,
                status=node.status,
                last_seen_at=node.last_seen_at,
                updated_at=node.updated_at,
            )
        )
        return node

    @staticmethod
    def _to_domain(record: VpnNodeRecord) -> VpnNode:
        return VpnNode(
            id=record.id,
            name=record.name,
            provider=record.provider,
            provider_region=record.provider_region,
            country_code=record.country_code,
            city=record.city,
            public_ipv4=record.public_ipv4,
            private_ipv4=record.private_ipv4,
            wireguard_port=record.wireguard_port,
            wireguard_public_key=record.wireguard_public_key,
            capacity=record.capacity,
            status=record.status,
            last_seen_at=record.last_seen_at,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )
