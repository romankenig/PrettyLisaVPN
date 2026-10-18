"""Async persistence operations for VPN session state and address ownership."""

import hashlib
import math
from dataclasses import replace
from datetime import UTC, datetime
from ipaddress import IPv4Address
from uuid import UUID

from sqlalchemy import case, func, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from prettylisavpn.subscriptions.domain import SubscriptionPlan
from prettylisavpn.subscriptions.entitlements import FREE_ENTITLEMENTS
from prettylisavpn.subscriptions.model import SubscriptionRecord
from prettylisavpn.subscriptions.repository import SubscriptionRepository
from prettylisavpn.vpn_sessions.domain import VpnSession, VpnSessionStatus
from prettylisavpn.vpn_sessions.model import FreeVpnUsageRecord, VpnSessionRecord


class VpnSessionRepository:
    _ADDRESS_ALLOCATION_LOCK_ID = 6_492_765_921_147_037_073

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def settle_free_usage(self, user_id: UUID | None = None) -> None:
        """Return unused budget only after the node acknowledges peer removal."""
        ended = (
            select(func.least(VpnSessionRecord.peer_removed_at, VpnSessionRecord.expires_at))
            .where(VpnSessionRecord.id == FreeVpnUsageRecord.session_id,
                   VpnSessionRecord.peer_removed_at.is_not(None),
                   VpnSessionRecord.status.in_((VpnSessionStatus.EXPIRED, VpnSessionStatus.DISCONNECTED, VpnSessionStatus.FAILED)))
            .scalar_subquery()
        )
        conditions = [] if user_id is None else [FreeVpnUsageRecord.user_id == user_id]
        await self._session.execute(update(FreeVpnUsageRecord).where(
            *conditions,
            FreeVpnUsageRecord.released_at.is_(None), ended.is_not(None)
        ).values(released_at=ended))

    async def remaining_free_seconds(self, user_id: UUID, at: datetime) -> int:
        """Caller locks the account before checking and reserving its UTC budget."""
        await self.settle_free_usage(user_id)
        row = FreeVpnUsageRecord
        seconds = case(
            (row.released_at.is_(None), func.extract('epoch', row.reserved_until - row.reserved_from)),
            (row.activated_at.is_(None), 0),
            else_=func.greatest(0, func.extract('epoch', func.least(row.released_at, row.reserved_until) - func.greatest(row.activated_at, row.reserved_from))),
        )
        consumed = await self._session.scalar(select(func.coalesce(func.sum(seconds), 0)).where(
            row.user_id == user_id, row.day == at.astimezone(UTC).date()
        ))
        limit = FREE_ENTITLEMENTS.daily_vpn_limit_seconds
        assert limit is not None
        return max(0, math.floor(limit - float(consumed or 0)))

    async def reserve_free_usage(self, vpn_session: VpnSession) -> None:
        assert vpn_session.expires_at is not None
        self._session.add(FreeVpnUsageRecord(
            session_id=vpn_session.id, user_id=vpn_session.user_id,
            day=vpn_session.started_at.date(), reserved_from=vpn_session.started_at,
            reserved_until=vpn_session.expires_at,
        ))
        await self._session.flush()

    async def activate_free_usage(self, session_id: UUID, at: datetime) -> None:
        await self._session.execute(update(FreeVpnUsageRecord).where(
            FreeVpnUsageRecord.session_id == session_id,
            FreeVpnUsageRecord.activated_at.is_(None),
        ).values(activated_at=at))

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
            peer_removed_at=vpn_session.peer_removed_at,
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

    async def acquire_peer_lock(self, public_key: str) -> None:
        # Shared by provisioning and cleanup across processes and app restarts.
        key = int.from_bytes(hashlib.sha256(public_key.encode()).digest()[:4], signed=True)
        await self._session.execute(
            text("SELECT pg_advisory_xact_lock(:namespace, :key)"),
            {"namespace": 1347573328, "key": key},
        )

    async def has_unremoved_public_key(self, public_key: str) -> bool:
        return (
            await self._session.scalar(
                select(VpnSessionRecord.id)
                .where(
                    VpnSessionRecord.client_wireguard_public_key == public_key,
                    VpnSessionRecord.peer_removed_at.is_(None),
                )
                .limit(1)
            )
            is not None
        )

    async def disconnect_device(self, user_id: UUID, device_id: UUID, at: datetime) -> None:
        # Terminal rows with peer_removed_at=NULL are the existing durable cleanup queue.
        await self._session.execute(
            update(VpnSessionRecord)
            .where(
                VpnSessionRecord.user_id == user_id,
                VpnSessionRecord.device_id == device_id,
                VpnSessionRecord.status.in_((VpnSessionStatus.PENDING, VpnSessionStatus.ACTIVE)),
            )
            .values(status=VpnSessionStatus.DISCONNECTED, disconnected_at=at, updated_at=at)
        )
        await self.settle_free_usage()

    async def list_device_cleanup(self, user_id: UUID, device_id: UUID) -> list[VpnSession]:
        records = await self._session.scalars(
            select(VpnSessionRecord)
            .where(
                VpnSessionRecord.user_id == user_id,
                VpnSessionRecord.device_id == device_id,
                VpnSessionRecord.peer_removed_at.is_(None),
                VpnSessionRecord.status.in_(
                    (
                        VpnSessionStatus.DISCONNECTED,
                        VpnSessionStatus.EXPIRED,
                        VpnSessionStatus.FAILED,
                    )
                ),
            )
            .order_by(VpnSessionRecord.id)
        )
        return [self._to_domain(record) for record in records]

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

    async def reconcile_paid_access(self, at: datetime, user_id: UUID | None = None) -> None:
        """Refresh paid deadlines from source of truth, including legacy unbounded peers.

        Lock only session rows, in a stable order. Terminal rows are never resurrected.
        Renewal committed before this check extends a live session's deadline.
        """
        statement = (
            select(VpnSessionRecord, SubscriptionRecord)
            .outerjoin(SubscriptionRecord, SubscriptionRecord.user_id == VpnSessionRecord.user_id)
            .where(
                VpnSessionRecord.plan_snapshot != SubscriptionPlan.FREE,
                VpnSessionRecord.status.in_((VpnSessionStatus.PENDING, VpnSessionStatus.ACTIVE)),
            )
            .order_by(VpnSessionRecord.id)
            .with_for_update(of=VpnSessionRecord)
        )
        if user_id is not None:
            statement = statement.where(VpnSessionRecord.user_id == user_id)
        for record, subscription_record in await self._session.execute(statement):
            current = self._to_domain(record)
            subscription = (
                SubscriptionRepository._to_domain(subscription_record)
                if subscription_record is not None else None
            )
            if subscription is not None and subscription.effective_plan(at) is not SubscriptionPlan.FREE:
                if current.expires_at != subscription.current_period_end:
                    await self.update(replace(current, expires_at=subscription.current_period_end, updated_at=at))
                continue
            deadline = subscription.current_period_end if subscription is not None else None
            if deadline is not None and current.started_at < deadline <= at:
                terminal = replace(current, status=VpnSessionStatus.EXPIRED, expires_at=deadline, updated_at=at)
            else:
                terminal = replace(current, status=VpnSessionStatus.FAILED, updated_at=at)
            await self.update(terminal)

    async def expire_allocations(self, at: datetime, user_id: UUID | None = None) -> None:
        conditions = [] if user_id is None else [VpnSessionRecord.user_id == user_id]
        await self._session.execute(
            update(VpnSessionRecord)
            .where(
                *conditions,
                VpnSessionRecord.plan_snapshot == SubscriptionPlan.FREE,
                VpnSessionRecord.status.in_((VpnSessionStatus.PENDING, VpnSessionStatus.ACTIVE)),
                VpnSessionRecord.expires_at.is_not(None),
                VpnSessionRecord.expires_at <= at,
            )
            .values(status=VpnSessionStatus.EXPIRED, updated_at=at)
        )
        await self.settle_free_usage()

    async def list_live_allocated_ipv4(self, at: datetime) -> set[IPv4Address]:
        # Never hand an address to another peer until remote deletion is acknowledged.
        statement = select(VpnSessionRecord.allocated_client_ipv4).where(
            VpnSessionRecord.peer_removed_at.is_(None)
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
                peer_removed_at=vpn_session.peer_removed_at,
                updated_at=vpn_session.updated_at,
            )
        )
        if not vpn_session.is_live():
            await self.settle_free_usage(vpn_session.user_id)
        return vpn_session

    async def get_owned_for_update(
        self, session_id: UUID, user_id: UUID, device_id: UUID
    ) -> VpnSession | None:
        statement = (
            select(VpnSessionRecord)
            .where(
                VpnSessionRecord.id == session_id,
                VpnSessionRecord.user_id == user_id,
                VpnSessionRecord.device_id == device_id,
            )
            .with_for_update()
        )
        record = await self._session.scalar(statement)
        return self._to_domain(record) if record is not None else None

    async def list_cleanup_pending(self) -> list[VpnSession]:
        records = await self._session.scalars(
            select(VpnSessionRecord)
            .where(
                VpnSessionRecord.status.in_(
                    (
                        VpnSessionStatus.EXPIRED,
                        VpnSessionStatus.DISCONNECTED,
                        VpnSessionStatus.FAILED,
                    )
                ),
                VpnSessionRecord.peer_removed_at.is_(None),
            )
            .order_by(VpnSessionRecord.updated_at, VpnSessionRecord.id)
        )
        return [self._to_domain(record) for record in records]

    async def list_active(self) -> list[VpnSession]:
        records = await self._session.scalars(
            select(VpnSessionRecord)
            .where(VpnSessionRecord.status == VpnSessionStatus.ACTIVE)
            .order_by(VpnSessionRecord.updated_at, VpnSessionRecord.id)
        )
        return [self._to_domain(record) for record in records]

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
            peer_removed_at=record.peer_removed_at,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )
