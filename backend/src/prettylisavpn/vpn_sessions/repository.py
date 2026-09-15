"""Async persistence operations for VPN session state and address ownership."""

from datetime import datetime
from ipaddress import IPv4Address
from uuid import UUID

from sqlalchemy import or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from prettylisavpn.vpn_sessions.domain import VpnSession, VpnSessionStatus
from prettylisavpn.vpn_sessions.model import VpnSessionRecord


class VpnSessionRepository:
    _ADDRESS_ALLOCATION_LOCK_ID = 6_492_765_921_147_037_073

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

    async def get_live_for_device(self, device_id: UUID, at: datetime) -> VpnSession | None:
        statement = select(VpnSessionRecord).where(
            VpnSessionRecord.device_id == device_id,
            VpnSessionRecord.status.in_((VpnSessionStatus.PENDING, VpnSessionStatus.ACTIVE)),
            or_(VpnSessionRecord.expires_at.is_(None), VpnSessionRecord.expires_at > at),
        )
        record = await self._session.scalar(statement)
        return self._to_domain(record) if record is not None else None

    async def acquire_address_allocation_lock(self) -> None:
        """Serialize allocation until the caller's surrounding transaction completes."""
        await self._session.execute(
            text("SELECT pg_advisory_xact_lock(:lock_id)"),
            {"lock_id": self._ADDRESS_ALLOCATION_LOCK_ID},
        )

    async def expire_allocations(self, at: datetime) -> None:
        await self._session.execute(
            update(VpnSessionRecord)
            .where(
                VpnSessionRecord.status.in_((VpnSessionStatus.PENDING, VpnSessionStatus.ACTIVE)),
                VpnSessionRecord.expires_at.is_not(None),
                VpnSessionRecord.expires_at <= at,
            )
            .values(status=VpnSessionStatus.EXPIRED, updated_at=at)
        )

    async def list_live_allocated_ipv4(self, at: datetime) -> set[IPv4Address]:
        statement = select(VpnSessionRecord.allocated_client_ipv4).where(
            VpnSessionRecord.status.in_((VpnSessionStatus.PENDING, VpnSessionStatus.ACTIVE)),
            or_(VpnSessionRecord.expires_at.is_(None), VpnSessionRecord.expires_at > at),
        )
        return set(await self._session.scalars(statement))

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
