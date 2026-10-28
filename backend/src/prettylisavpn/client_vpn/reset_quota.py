"""Server-only operator CLI. No client/API can reset its own Free allowance."""

import argparse
import asyncio
import json
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select

from prettylisavpn.client_vpn.model import ClientLeaseRecord, FreeQuotaResetRecord
from prettylisavpn.client_vpn.quota import ClientQuotaRepository
from prettylisavpn.config import Settings
from prettylisavpn.connections import Postgres
from prettylisavpn.fleet.domain import FleetError
from prettylisavpn.legacy_vpn.sessions import FreeVpnUsageRecord
from prettylisavpn.subscriptions.domain import SubscriptionPlan
from prettylisavpn.subscriptions.repository import SubscriptionRepository
from prettylisavpn.users.model import UserRecord


async def reset(
    postgres: Postgres, email: str, request_id: UUID, now: datetime
) -> dict[str, object]:
    async with postgres.session() as session, session.begin():
        user = await session.scalar(
            select(UserRecord).where(UserRecord.email == email.strip().lower()).with_for_update()
        )
        if user is None:
            raise FleetError("ACCOUNT_NOT_FOUND", 404)
        previous = await session.get(FreeQuotaResetRecord, request_id)
        if previous:
            if previous.user_id != user.id:
                raise FleetError("QUOTA_RESET_CONFLICT")
            return {"reset": True, "repeated": True, "reset_at": previous.reset_at.isoformat()}
        subscription = await SubscriptionRepository(session).get_by_user_id(user.id)
        if not subscription or subscription.effective_plan(now) != SubscriptionPlan.FREE:
            raise FleetError("QUOTA_RESET_FREE_ONLY")
        if await session.scalar(
            select(FreeQuotaResetRecord.id).where(
                FreeQuotaResetRecord.user_id == user.id,
                FreeQuotaResetRecord.day == now.astimezone(UTC).date(),
            )
        ):
            raise FleetError("QUOTA_RESET_ALREADY_APPLIED")
        # Confirm cleanup first: never grant another hour over an uncertain reservation.
        await ClientQuotaRepository(session).remaining_free_seconds(user.id, now)
        if await session.scalar(
            select(ClientLeaseRecord.id)
            .where(
                ClientLeaseRecord.user_id == user.id,
                ClientLeaseRecord.removed_at.is_(None),
            )
            .limit(1)
        ) or await session.scalar(
            select(FreeVpnUsageRecord.session_id)
            .where(
                FreeVpnUsageRecord.user_id == user.id,
                FreeVpnUsageRecord.released_at.is_(None),
            )
            .limit(1)
        ):
            raise FleetError("QUOTA_RESET_CLEANUP_REQUIRED")
        session.add(
            FreeQuotaResetRecord(
                id=request_id, user_id=user.id, day=now.astimezone(UTC).date(), reset_at=now
            )
        )
        return {
            "reset": True,
            "repeated": False,
            "reset_at": now.isoformat(),
            "available_seconds": 3600,
        }


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    parser.add_argument("--request-id", type=UUID, required=True)
    args = parser.parse_args()
    postgres = Postgres(Settings())
    try:
        print(json.dumps(await reset(postgres, args.email, args.request_id, datetime.now(UTC))))
    except FleetError as error:
        print(json.dumps({"error": error.code}))
        raise SystemExit(1) from None
    finally:
        await postgres.close()


if __name__ == "__main__":
    asyncio.run(main())
