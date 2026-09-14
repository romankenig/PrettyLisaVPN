"""Async persistence operations for VPN session state."""

from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from prettylisavpn.vpn_sessions.domain import VpnSession, VpnSessionStatus
from prettylisavpn.vpn_sessions.model import VpnSessionRecord


class VpnSessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, vpn_session: VpnSession) -> VpnSession:
        record = VpnSessionRecord(
            id=vpn_session.id,
            user_id=vpn_session.user_id,
            device_id=vpn_session.device_id,
            vpn_node_id=vpn_session.vpn_node_id,
            client_wireguard_public_key=vpn_session.client_wireguard_public_key,
            allocated_client_ipv4=vpn_session.allocated_client_ipv4,
            plan_snapshot=vpn_session.plan_snapshot,
            status=vpn_session.status,
            started_at=vpn_session.started_at,
            expires_at=vpn_session.expires_at,
            disconnected_at=vpn_session.disconnected_at,
            created_at=vpn_session.created_at,
            updated_at=vpn_session.updated_at,
        )
        self._session.add(record)
        await self._session.flush()
        return self._to_domain(record)

    async def get(self, session_id: UUID) -> VpnSession | None:
        record = await self._session.get(VpnSessionRecord, session_id)
        return self._to_domain(record) if record is not None else None

    async def get_for_update(self, session_id: UUID) -> VpnSession | None:
        statement = (
            select(VpnSessionRecord).where(VpnSessionRecord.id == session_id).with_for_update()
        )
        record = await self._session.scalar(statement)
        return self._to_domain(record) if record is not None else None

    async def get_live_for_device(self, device_id: UUID) -> VpnSession | None:
        statement = select(VpnSessionRecord).where(
            VpnSessionRecord.device_id == device_id,
            VpnSessionRecord.status.in_((VpnSessionStatus.PENDING, VpnSessionStatus.ACTIVE)),
        )
        record = await self._session.scalar(statement)
        return self._to_domain(record) if record is not None else None

    async def list_by_user(self, user_id: UUID) -> list[VpnSession]:
        records = await self._session.scalars(
            select(VpnSessionRecord)
            .where(VpnSessionRecord.user_id == user_id)
            .order_by(VpnSessionRecord.created_at, VpnSessionRecord.id)
        )
        return [self._to_domain(record) for record in records]

    async def update(self, vpn_session: VpnSession) -> VpnSession:
        await self._session.execute(
            update(VpnSessionRecord)
            .where(VpnSessionRecord.id == vpn_session.id)
            .values(
                vpn_node_id=vpn_session.vpn_node_id,
                client_wireguard_public_key=vpn_session.client_wireguard_public_key,
                allocated_client_ipv4=vpn_session.allocated_client_ipv4,
                plan_snapshot=vpn_session.plan_snapshot,
                status=vpn_session.status,
                started_at=vpn_session.started_at,
                expires_at=vpn_session.expires_at,
                disconnected_at=vpn_session.disconnected_at,
                updated_at=vpn_session.updated_at,
            )
        )
        return vpn_session

    @staticmethod
    def _to_domain(record: VpnSessionRecord) -> VpnSession:
        return VpnSession(
            id=record.id,
            user_id=record.user_id,
            device_id=record.device_id,
            vpn_node_id=record.vpn_node_id,
            client_wireguard_public_key=record.client_wireguard_public_key,
            allocated_client_ipv4=record.allocated_client_ipv4,
            plan_snapshot=record.plan_snapshot,
            status=record.status,
            started_at=record.started_at,
            expires_at=record.expires_at,
            disconnected_at=record.disconnected_at,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )
