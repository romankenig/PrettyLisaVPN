"""Durable verified inbox, separate from subscription settlement and charge admission."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from prettylisavpn.billing.cardlink import BillStatus, CardlinkError, ExpectedBill, Notification
from prettylisavpn.billing.model import (
    BillingOperationRecord,
    CardlinkBillRecord,
    CardlinkReceiptRecord,
)
from prettylisavpn.connections import Postgres


class PostgresCardlinkReceipts:
    def __init__(self, postgres: Postgres):
        self.postgres = postgres

    async def expected(self, notification: Notification) -> ExpectedBill:
        async with self.postgres.session() as session:
            row = await session.scalar(
                select(BillingOperationRecord)
                .join(
                    CardlinkBillRecord, CardlinkBillRecord.operation_id == BillingOperationRecord.id
                )
                .where(
                    BillingOperationRecord.id == notification.operation_id,
                    BillingOperationRecord.provider_name == "cardlink",
                    CardlinkBillRecord.bill_id == notification.bill_id,
                )
            )
            if (
                row is None
                or row.command.get("action") not in ("SUBSCRIBE", "RENEW")
                or type(row.quote.get("amount_minor")) is not int
                or row.command.get("currency") not in ("RUB", "USD")
            ):
                raise CardlinkError("CARDLINK_ORDER_NOT_FOUND", 404)
            return ExpectedBill(
                row.id, notification.bill_id, row.quote["amount_minor"], row.command["currency"]
            )

    async def record(self, expected: ExpectedBill, status: BillStatus) -> None:
        async with self.postgres.session() as session, session.begin():
            # Keep the binding alive until commit; never acknowledge an uncommitted receipt.
            binding = await session.scalar(
                select(CardlinkBillRecord)
                .where(
                    CardlinkBillRecord.operation_id == expected.operation_id,
                    CardlinkBillRecord.bill_id == expected.bill_id,
                )
                .with_for_update()
            )
            if binding is None:
                raise CardlinkError("CARDLINK_ORDER_NOT_FOUND", 404)
            await session.execute(
                insert(CardlinkReceiptRecord)
                .values(
                    operation_id=expected.operation_id,
                    status=status,
                    verified_at=datetime.now(UTC),
                )
                .on_conflict_do_nothing()
            )
