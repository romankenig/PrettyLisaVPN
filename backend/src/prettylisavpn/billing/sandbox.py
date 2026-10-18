"""Explicit development-only provider; no network calls or payment credentials.

Receipts and event deduplication survive process death. The separate provider
transaction models acceptance followed by a lost response or failed settlement.
Controls are available only to server operators through the CLI, never HTTP.
"""

import argparse
import asyncio
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from prettylisavpn.billing.model import (
    BillingOperationRecord,
    SandboxMandateRecord,
    SandboxNotificationRecord,
    SandboxPaymentRecord,
)
from prettylisavpn.billing.operations_domain import (
    Action,
    Currency,
    OperationStatus,
    PaymentRoute,
    ProviderMandate,
    ProviderRequest,
    ProviderResult,
)
from prettylisavpn.config import Settings
from prettylisavpn.connections import Postgres

TerminalStatus = Literal["SUCCEEDED", "FAILED", "CANCELED"]


def simulated_result(request: ProviderRequest, status: OperationStatus) -> ProviderResult:
    """Derive amounts from the accepted request, never from notification input."""
    succeeded = status == "SUCCEEDED"
    mandate = None
    if (
        succeeded
        and request.action != "CANCEL"
        and request.payment_route not in ("CRYPTO", "ALIPAY_WECHAT")
    ):
        reference = (
            request.previous_mandate_reference
            if request.action == "RENEW" and request.previous_mandate_reference
            else "sandbox-" + str(request.operation_id)
        )
        mandate = ProviderMandate(
            reference=reference,
            label="Тестовый способ оплаты — без списания",
        )
    revokes_previous = succeeded and (
        request.action == "CANCEL"
        or bool(
            request.previous_mandate_reference
            and (mandate is None or mandate.reference != request.previous_mandate_reference)
        )
    )
    return ProviderResult(
        operation_id=request.operation_id,
        status=status,
        amount_minor=request.amount_minor if succeeded else None,
        currency=request.currency if succeeded and request.amount_minor is not None else None,
        mandate=mandate,
        recurring_stopped=revokes_previous,
        previous_mandate_revoked=revokes_previous,
    )


class SandboxBillingProvider:
    name = "development-sandbox-v1"
    sandbox = True
    routes: frozenset[PaymentRoute] = frozenset({"MIR", "BANK_CARD", "ALIPAY_WECHAT", "CRYPTO"})
    redirect_hosts: frozenset[str] = frozenset()

    def __init__(self, postgres: Postgres, settings: Settings) -> None:
        if settings.environment not in ("development", "test"):
            raise ValueError("Sandbox billing requires development or test environment")
        self.postgres = postgres

    def supports(self, action: Action, route: PaymentRoute | None, currency: Currency) -> bool:
        return currency in ("RUB", "USD") and (
            route in self.routes if action in ("SUBSCRIBE", "RENEW") else route is None
        )

    async def reconcile(self, request: ProviderRequest) -> ProviderResult:
        document = request.model_dump(mode="json")
        async with self.postgres.session() as session, session.begin():
            await session.execute(
                insert(SandboxPaymentRecord)
                .values(
                    operation_id=request.operation_id,
                    request=document,
                    result=simulated_result(request, "PENDING").model_dump(mode="json"),
                )
                .on_conflict_do_nothing(index_elements=[SandboxPaymentRecord.operation_id])
            )
            row = await session.get(SandboxPaymentRecord, request.operation_id)
            if row is None or row.request != document:
                raise ValueError("Sandbox operation identity conflict")
            result = ProviderResult.model_validate(row.result)
        return result

    async def notify(
        self, operation_id: UUID, event_id: UUID, status: TerminalStatus
    ) -> ProviderResult:
        """Persist an authoritative simulated event; duplicates cannot change a receipt.

        Reusing an event UUID with another payload or changing a terminal outcome
        is rejected. A new event with the same terminal outcome is harmless.
        Settlement remains the responsibility of the normal leased billing worker.
        """
        if status not in ("SUCCEEDED", "FAILED", "CANCELED"):
            raise ValueError("Invalid sandbox notification status")
        async with self.postgres.session() as session, session.begin():
            row = await session.scalar(
                select(SandboxPaymentRecord)
                .where(SandboxPaymentRecord.operation_id == operation_id)
                .with_for_update()
            )
            if row is None:
                raise ValueError("Unknown sandbox operation")
            result = ProviderResult.model_validate(row.result)
            if result.status not in ("PENDING", status):
                raise ValueError("Sandbox terminal result conflict")
            await session.execute(
                insert(SandboxNotificationRecord)
                .values(event_id=event_id, operation_id=operation_id, status=status)
                .on_conflict_do_nothing(index_elements=[SandboxNotificationRecord.event_id])
            )
            event = await session.get(SandboxNotificationRecord, event_id)
            if event is None or event.operation_id != operation_id or event.status != status:
                raise ValueError("Sandbox notification identity conflict")
            if result.status == "PENDING":
                request = ProviderRequest.model_validate(row.request)
                result = simulated_result(request, status)
                if status == "SUCCEEDED":
                    await self._apply_mandate(session, request, result)
                row.result = result.model_dump(mode="json")
            await session.execute(
                update(BillingOperationRecord)
                .where(
                    BillingOperationRecord.id == operation_id,
                    BillingOperationRecord.provider_name == self.name,
                    BillingOperationRecord.status == "PENDING",
                )
                .values(next_attempt_at=datetime.now(UTC))
            )
        return result

    @staticmethod
    async def _apply_mandate(
        session: AsyncSession, request: ProviderRequest, result: ProviderResult
    ) -> None:
        previous = None
        if request.previous_mandate_reference:
            previous = await session.scalar(
                select(SandboxMandateRecord)
                .where(SandboxMandateRecord.reference == request.previous_mandate_reference)
                .with_for_update()
            )
            if (
                previous is None
                or previous.user_id != request.account_id
                or previous.status != "ACTIVE"
            ):
                raise ValueError("Sandbox mandate is unknown, foreign or revoked")
        replacement = result.mandate.reference if result.mandate else None
        if previous is not None and previous.reference != replacement:
            previous.status = "REVOKED"
        if result.mandate is not None and (
            previous is None or previous.reference != replacement
        ):
            session.add(
                SandboxMandateRecord(
                    reference=result.mandate.reference,
                    user_id=request.account_id,
                    status="ACTIVE",
                )
            )


async def deliver(
    settings: Settings, operation_id: UUID, event_id: UUID, status: TerminalStatus
) -> None:
    if settings.billing_provider != "sandbox":
        raise ValueError("Set BILLING_PROVIDER=sandbox explicitly before delivering test events")
    postgres = Postgres(settings)
    try:
        provider = SandboxBillingProvider(postgres, settings)
        await provider.notify(operation_id, event_id, status)
        # A live lease is deliberately preserved. The background worker will retry.
        from prettylisavpn.billing.worker import BillingWorker

        await BillingWorker(postgres, provider).process(operation_id)
    finally:
        await postgres.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="PrettyLisaVPN sandbox notification (no charge)")
    parser.add_argument("operation_id", type=UUID)
    parser.add_argument("status", choices=("SUCCEEDED", "FAILED", "CANCELED"))
    parser.add_argument("--event-id", type=UUID, required=True)
    args = parser.parse_args()
    asyncio.run(deliver(Settings(), args.operation_id, args.event_id, args.status))


if __name__ == "__main__":
    main()
