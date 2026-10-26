"""Preserve historical Free usage in /me; placeholder attempts allocate nothing."""

import math
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import case, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from prettylisavpn.legacy_vpn.enums import VpnSessionStatus
from prettylisavpn.legacy_vpn.sessions import FreeVpnUsageRecord, VpnSessionRecord
from prettylisavpn.subscriptions.entitlements import FREE_ENTITLEMENTS


class LegacyQuotaRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def settle_free_usage(self, user_id: UUID | None = None) -> None:
        """Return unused budget only after the node acknowledges peer removal."""
        ended = (
            select(func.least(VpnSessionRecord.peer_removed_at, VpnSessionRecord.expires_at))
            .where(
                VpnSessionRecord.id == FreeVpnUsageRecord.session_id,
                VpnSessionRecord.peer_removed_at.is_not(None),
                VpnSessionRecord.status.in_(
                    (
                        VpnSessionStatus.EXPIRED,
                        VpnSessionStatus.DISCONNECTED,
                        VpnSessionStatus.FAILED,
                    )
                ),
            )
            .scalar_subquery()
        )
        conditions = [] if user_id is None else [FreeVpnUsageRecord.user_id == user_id]
        await self._session.execute(
            update(FreeVpnUsageRecord)
            .where(*conditions, FreeVpnUsageRecord.released_at.is_(None), ended.is_not(None))
            .values(released_at=ended)
        )

    async def remaining_free_seconds(self, user_id: UUID, at: datetime) -> int:
        """Caller locks the account before checking and reserving its UTC budget."""
        if at.tzinfo is None or at.utcoffset() is None:
            raise ValueError("at must be timezone-aware")
        await self.settle_free_usage(user_id)
        row = FreeVpnUsageRecord
        seconds = case(
            (
                row.released_at.is_(None),
                func.extract("epoch", row.reserved_until - row.reserved_from),
            ),
            (row.activated_at.is_(None), 0),
            else_=func.greatest(
                0,
                func.extract(
                    "epoch",
                    func.least(row.released_at, row.reserved_until)
                    - func.greatest(row.activated_at, row.reserved_from),
                ),
            ),
        )
        consumed = await self._session.scalar(
            select(func.coalesce(func.sum(seconds), 0)).where(
                row.user_id == user_id, row.day == at.astimezone(UTC).date()
            )
        )
        limit = FREE_ENTITLEMENTS.daily_vpn_limit_seconds
        assert limit is not None
        return max(0, math.floor(limit - float(consumed or 0)))
