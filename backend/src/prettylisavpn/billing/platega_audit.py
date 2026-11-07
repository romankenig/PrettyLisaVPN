"""Server-only reconciliation report; never changes access, charges or mandates.

Run with the deployment's database environment:
    python -m prettylisavpn.billing.platega_audit
Only opaque IDs and states are printed, never email, credentials or provider bodies.
"""

import asyncio
import json

from sqlalchemy import select

from prettylisavpn.billing.model import BillingOperationRecord
from prettylisavpn.billing.platega_model import PlategaAgreementRecord, PlategaChargeRecord
from prettylisavpn.config import Settings
from prettylisavpn.connections import Postgres


async def report(postgres: Postgres) -> dict[str, list[dict[str, str | None]]]:
    async with postgres.session() as session:
        charges = await session.scalars(
            select(PlategaChargeRecord).where(PlategaChargeRecord.review_required.is_(True))
        )
        pending = await session.execute(
            select(BillingOperationRecord, PlategaAgreementRecord)
            .outerjoin(
                PlategaAgreementRecord,
                PlategaAgreementRecord.operation_id == BillingOperationRecord.id,
            )
            .where(
                BillingOperationRecord.provider_name == "platega",
                BillingOperationRecord.status == "PENDING",
            )
        )
        return {
            "review_required": [
                {
                    "payment_id": str(row.id),
                    "operation_id": str(row.agreement_id),
                    "status": row.status,
                }
                for row in charges
            ],
            "pending": [
                {
                    "operation_id": str(operation.id),
                    "created_at": operation.created_at.isoformat(),
                    "subscription_id": str(agreement.provider_id)
                    if agreement and agreement.provider_id
                    else None,
                    "provider_state": agreement.state if agreement else None,
                }
                for operation, agreement in pending
            ],
        }


async def main() -> None:
    postgres = Postgres(Settings())
    try:
        print(json.dumps(await report(postgres), separators=(",", ":")))
    finally:
        await postgres.close()


if __name__ == "__main__":
    asyncio.run(main())
