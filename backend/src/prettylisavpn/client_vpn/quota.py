"""One shared UTC budget, including usage retained from the previous implementation."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from prettylisavpn.client_vpn.domain import reserved_seconds
from prettylisavpn.client_vpn.model import ClientLeaseRecord
from prettylisavpn.legacy_vpn.quota import LegacyQuotaRepository


class ClientQuotaRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def remaining_free_seconds(self, user_id: UUID, at: datetime) -> int:
        remaining = await LegacyQuotaRepository(self.session).remaining_free_seconds(user_id, at)
        start = at.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        rows = await self.session.scalars(
            select(ClientLeaseRecord).where(
                ClientLeaseRecord.user_id == user_id,
                ClientLeaseRecord.is_free.is_(True),
                ClientLeaseRecord.created_at >= start,
                ClientLeaseRecord.created_at < start + timedelta(days=1),
            )
        )
        consumed = sum(
            reserved_seconds(row.created_at, row.expires_at, row.activated_at, row.removed_at)
            for row in rows
        )
        return max(0, remaining - consumed)
