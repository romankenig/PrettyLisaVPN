"""Async persistence operations for VPN node metadata."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from prettylisavpn.vpn_nodes.availability import VpnNodeCapacitySnapshot
from prettylisavpn.vpn_nodes.domain import VpnNode, VpnNodeHealthStatus, normalize_country_code
from prettylisavpn.vpn_nodes.model import VpnNodeRecord
from prettylisavpn.vpn_sessions.domain import VpnSessionStatus
from prettylisavpn.vpn_sessions.model import VpnSessionRecord


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
            is_available_for_free=node.is_available_for_free,
            status=node.status,
            last_seen_at=node.last_seen_at,
            health_status=node.health_status,
            health_checked_at=node.health_checked_at,
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

    async def list_capacity_snapshots(
        self,
        country_code: str | None = None,
        *,
        at: datetime,
        lock_nodes: bool = False,
    ) -> list[VpnNodeCapacitySnapshot]:
        statement = select(VpnNodeRecord).order_by(
            VpnNodeRecord.country_code, VpnNodeRecord.created_at, VpnNodeRecord.id
        )
        if country_code is not None:
            statement = statement.where(
                VpnNodeRecord.country_code == normalize_country_code(country_code)
            )
        if lock_nodes:
            statement = statement.with_for_update(of=VpnNodeRecord)
        records = list(await self._session.scalars(statement))
        if not records:
            return []

        node_ids = [record.id for record in records]
        count_statement = (
            select(
                VpnSessionRecord.vpn_node_id,
                func.count(VpnSessionRecord.id).label("live_sessions"),
            )
            .where(
                VpnSessionRecord.vpn_node_id.in_(node_ids),
                VpnSessionRecord.status.in_((VpnSessionStatus.PENDING, VpnSessionStatus.ACTIVE)),
                or_(VpnSessionRecord.expires_at.is_(None), VpnSessionRecord.expires_at > at),
            )
            .group_by(VpnSessionRecord.vpn_node_id)
        )
        counts = {
            node_id: live_sessions
            for node_id, live_sessions in (await self._session.execute(count_statement)).all()
        }
        return [
            VpnNodeCapacitySnapshot(self._to_domain(record), counts.get(record.id, 0))
            for record in records
        ]

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
                is_available_for_free=node.is_available_for_free,
                status=node.status,
                last_seen_at=node.last_seen_at,
                health_status=node.health_status,
                health_checked_at=node.health_checked_at,
                updated_at=node.updated_at,
            )
        )
        return node

    async def update_health(
        self,
        node_id: UUID,
        health_status: VpnNodeHealthStatus,
        health_checked_at: datetime,
        last_seen_at: datetime | None,
    ) -> VpnNode | None:
        statement = (
            update(VpnNodeRecord)
            .where(VpnNodeRecord.id == node_id)
            .values(
                health_status=health_status,
                health_checked_at=health_checked_at,
                last_seen_at=last_seen_at,
                updated_at=health_checked_at,
            )
            .returning(VpnNodeRecord)
        )
        record = await self._session.scalar(statement)
        return self._to_domain(record) if record is not None else None

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
            is_available_for_free=record.is_available_for_free,
            status=record.status,
            last_seen_at=record.last_seen_at,
            created_at=record.created_at,
            updated_at=record.updated_at,
            health_status=record.health_status,
            health_checked_at=record.health_checked_at,
        )
