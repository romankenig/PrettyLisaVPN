"""One shared UTC budget, including usage retained from the previous implementation."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from prettylisavpn.client_vpn.domain import reserved_seconds
from prettylisavpn.client_vpn.model import ClientLeaseRecord, FreeQuotaResetRecord
from prettylisavpn.legacy_vpn.quota import LegacyQuotaRepository


@dataclass(frozen=True)
class FreeQuotaSnapshot:
    available_seconds: int
    usable_seconds: int
    running_sessions: int


class ClientQuotaRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def remaining_free_seconds(self, user_id: UUID, at: datetime) -> int:
        start = at.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        reset = await self.session.scalar(
            select(FreeQuotaResetRecord).where(
                FreeQuotaResetRecord.user_id == user_id,
                FreeQuotaResetRecord.day == start.date(),
                FreeQuotaResetRecord.reset_at <= at,
            )
        )
        remaining = (
            3600
            if reset
            else await LegacyQuotaRepository(self.session).remaining_free_seconds(user_id, at)
        )
        cutoff = reset.reset_at if reset else start
        rows = await self.session.scalars(
            select(ClientLeaseRecord).where(
                ClientLeaseRecord.user_id == user_id,
                ClientLeaseRecord.is_free.is_(True),
                ClientLeaseRecord.created_at >= cutoff,
                ClientLeaseRecord.created_at < start + timedelta(days=1),
            )
        )
        consumed = sum(
            reserved_seconds(
                row.created_at,
                row.quota_reserved_until or row.expires_at,
                row.activated_at,
                row.removed_at,
            )
            for row in rows
        )
        return max(0, remaining - consumed)

    async def display(self, user_id: UUID, at: datetime) -> FreeQuotaSnapshot:
        """Account balance includes unused time already reserved by any active device."""
        remaining = await self.remaining_free_seconds(user_id, at)
        running = (
            await self.session.scalars(
                select(ClientLeaseRecord).where(
                    ClientLeaseRecord.user_id == user_id,
                    ClientLeaseRecord.is_free.is_(True),
                    ClientLeaseRecord.status == "READY",
                    ClientLeaseRecord.removed_at.is_(None),
                    ClientLeaseRecord.expires_at > at,
                )
            )
        ).all()
        live = [row for row in running if (row.quota_reserved_until or row.expires_at) > at]
        usable = remaining + sum(
            max(0, int(((row.quota_reserved_until or row.expires_at) - at).total_seconds()))
            for row in live
        )
        return FreeQuotaSnapshot(remaining, min(3600, usable), len(live))
