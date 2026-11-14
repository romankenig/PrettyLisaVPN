"""Observe the first ten continuous seconds without any counter increment."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from prettylisavpn.client_vpn.model import ClientLeaseRecord
from prettylisavpn.fleet.traffic import MAX_GAP, Snapshot, elapsed
from prettylisavpn.product_analytics.model import SessionSilenceRecord


def advance_silence(
    state: SessionSilenceRecord, start: datetime, end: datetime, moving: bool, valid: bool
) -> None:
    if state.first_silence_at is not None or end <= state.observed_until:
        return
    if not valid or abs((start - state.observed_until).total_seconds()) > 0.5:
        # A gap can conceal the first silence; never invent it from a later gap.
        state.complete = False
        state.quiet_since = None
    elif moving:
        state.quiet_since = None
    else:
        state.quiet_since = state.quiet_since or start
        if state.complete and (end - state.quiet_since).total_seconds() >= 10:
            state.first_silence_at = state.quiet_since
    state.observed_until = end


async def capture_silence(
    session: AsyncSession, previous: Snapshot | None, current: Snapshot
) -> None:
    if previous is None:
        return
    prior = {row.lease_id: row for row in previous.counters}
    current_rows = {row.lease_id: row for row in current.counters}
    leases = (
        await session.scalars(
            select(ClientLeaseRecord).where(
                ClientLeaseRecord.id.in_(prior.keys() | current_rows.keys()),
                ClientLeaseRecord.verified_at.is_not(None),
            )
        )
    ).all()
    states = {
        row.lease_id: row
        for row in await session.scalars(
            select(SessionSilenceRecord).where(
                SessionSilenceRecord.lease_id.in_([v.id for v in leases])
            )
        )
    }
    for lease in leases:
        assert lease.verified_at is not None
        old, new = prior.get(lease.id), current_rows.get(lease.id)
        end = datetime.fromtimestamp(new.at if new else current.at, UTC)
        if end <= lease.verified_at:
            continue
        start = datetime.fromtimestamp(old.at if old else previous.at, UTC)
        valid = bool(
            old
            and new
            and old.epoch == new.epoch
            and previous.boot == current.boot
            and elapsed(old.at, new.at, old.monotonic, new.monotonic)
            and new.download >= old.download
            and new.upload >= old.upload
        )
        state = states.get(lease.id)
        if state is None:
            state = SessionSilenceRecord(
                lease_id=lease.id,
                observed_until=max(start, lease.verified_at),
                complete=valid
                and start <= lease.verified_at
                and end.timestamp() - start.timestamp() <= MAX_GAP,
            )
            session.add(state)
        if lease.disconnected_at is not None and end > lease.disconnected_at:
            continue
        moving = bool(old and new and (new.download > old.download or new.upload > old.upload))
        advance_silence(state, max(start, lease.verified_at), end, moving, valid)
