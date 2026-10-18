"""Leased, fenced reconciliation; unknown outcomes stay PENDING, never retry new keys."""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy import or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from prettylisavpn.billing.domain import Offer
from prettylisavpn.billing.model import (
    BillingAccountRecord,
    BillingContractRecord,
    BillingOperationRecord,
)
from prettylisavpn.billing.operations_domain import (
    BillingCommand,
    ProviderRequest,
    ProviderResult,
    next_month,
    safe_redirect,
)
from prettylisavpn.billing.provider import BillingProvider, validate_provider
from prettylisavpn.connections import Postgres
from prettylisavpn.subscriptions.domain import SubscriptionPlan, SubscriptionStatus
from prettylisavpn.subscriptions.model import SubscriptionRecord


class BillingWorkerPort(Protocol):
    async def run(self, stop: asyncio.Event) -> None: ...


class BillingWorker:
    def __init__(
        self, postgres: Postgres, provider: BillingProvider | None, *, timeout: float = 5
    ) -> None:
        validate_provider(provider)
        self.postgres, self.provider, self.timeout = postgres, provider, timeout

    async def process(self, operation_id: UUID) -> bool:
        if self.provider is None:
            return False
        now = datetime.now(UTC)
        async with self.postgres.session() as session, session.begin():
            row = await session.scalar(
                select(BillingOperationRecord)
                .where(
                    BillingOperationRecord.id == operation_id,
                    BillingOperationRecord.status == "PENDING",
                    BillingOperationRecord.provider_name == self.provider.name,
                    BillingOperationRecord.next_attempt_at <= now,
                    or_(
                        BillingOperationRecord.lease_until.is_(None),
                        BillingOperationRecord.lease_until <= now,
                    ),
                )
                .with_for_update(skip_locked=True)
            )
            if row is None:
                return False
            row.claim_token = uuid4()
            row.lease_until = now + timedelta(seconds=30)
            row.attempts += 1
        claim = row.claim_token
        try:
            command = BillingCommand.model_validate(row.command)
            request = ProviderRequest(
                operation_id=row.id,
                account_id=row.user_id,
                action=command.action,
                payment_route=command.payment_route,
                amount_minor=row.quote["amount_minor"],
                currency=command.currency,
                previous_mandate_reference=row.quote["previous_mandate_reference"],
            )
            result = await asyncio.wait_for(self.provider.reconcile(request), timeout=self.timeout)
            result = ProviderResult.model_validate(result.model_dump())
            redirect = safe_redirect(result.redirect_url, self.provider.redirect_hosts)
            if result.operation_id != row.id:
                raise ValueError("Receipt identity mismatch")
            if result.status == "SUCCEEDED":
                self._validate_confirmation(request, result)
            async with self.postgres.session() as session, session.begin():
                subscription = await session.scalar(
                    select(SubscriptionRecord)
                    .where(SubscriptionRecord.user_id == row.user_id)
                    .with_for_update()
                )
                current = await session.scalar(
                    select(BillingOperationRecord)
                    .where(BillingOperationRecord.id == row.id)
                    .with_for_update()
                )
                if current is None or current.status != "PENDING" or current.claim_token != claim:
                    return False
                if result.status == "SUCCEEDED":
                    if (
                        subscription is None
                        or str(subscription.id) != current.quote["subscription_id"]
                        or subscription.updated_at.isoformat()
                        != current.quote["subscription_updated_at"]
                    ):
                        current.last_error = "SUBSCRIPTION_CHANGED"
                        current.claim_token = current.lease_until = None
                        current.next_attempt_at = datetime.now(UTC) + timedelta(seconds=60)
                        return True
                    await self._apply(session, subscription, current, command, result)
                current.status = result.status
                current.redirect_url = redirect if result.status == "PENDING" else None
                current.claim_token = current.lease_until = None
                current.last_error = None
                current.next_attempt_at = datetime.now(UTC) + timedelta(seconds=5)
                if result.status != "PENDING":
                    current.completed_at = datetime.now(UTC)
            return True
        except asyncio.CancelledError:
            # The accepted provider call may have completed: leave the durable lease for recovery.
            raise
        except (ValueError, SQLAlchemyError, TimeoutError, OSError):
            await self._defer(row.id, claim, "PROVIDER_OR_PERSISTENCE_UNAVAILABLE")
            return True
        except Exception:
            # Never turn an unknown provider outcome into a terminal failure or log its payload.
            await self._defer(row.id, claim, "PROVIDER_UNAVAILABLE")
            return True

    @staticmethod
    def _validate_confirmation(request: ProviderRequest, result: ProviderResult) -> None:
        if request.amount_minor != result.amount_minor:
            raise ValueError("Receipt amount mismatch")
        if request.amount_minor is not None and request.currency != result.currency:
            raise ValueError("Receipt currency mismatch")
        if request.action == "CANCEL" and (
            result.mandate is not None
            or not result.recurring_stopped
            or not result.previous_mandate_revoked
        ):
            raise ValueError("Cancellation not confirmed")
        if request.action == "CHANGE_METHOD" and result.mandate is None:
            raise ValueError("New mandate not confirmed")
        if (
            request.action in ("SUBSCRIBE", "RENEW")
            and request.payment_route in ("CRYPTO", "ALIPAY_WECHAT")
            and result.mandate is not None
        ):
            raise ValueError("Route does not support recurring payments")
        previous = request.previous_mandate_reference
        replacement = result.mandate.reference if result.mandate else None
        if (
            previous
            and previous != replacement
            and (not result.recurring_stopped or not result.previous_mandate_revoked)
        ):
            raise ValueError("Previous mandate not revoked")

    async def _apply(
        self,
        session: AsyncSession,
        subscription: SubscriptionRecord,
        row: BillingOperationRecord,
        command: BillingCommand,
        result: ProviderResult,
    ) -> None:
        account = await session.get(BillingAccountRecord, row.user_id)
        if account is None:
            account = BillingAccountRecord(user_id=row.user_id)
            session.add(account)
        now = datetime.now(UTC)
        if command.action in ("SUBSCRIBE", "RENEW"):
            if command.action == "SUBSCRIBE" or account.contract_id is None:
                offer = Offer.model_validate(row.quote["offer"])
                contract = BillingContractRecord(
                    id=row.id,
                    subscription_id=subscription.id,
                    group_id=UUID(row.quote["group_id"]),
                    catalog_revision=UUID(row.quote["catalog_revision"]),
                    offer_document=offer.model_dump(mode="json"),
                    amount_minor=row.quote["amount_minor"],
                    currency=command.currency,
                    locked_at=now,
                )
                session.add(contract)
                await session.flush()
                account.contract_id = contract.id
            if command.action == "SUBSCRIBE":
                subscription.current_period_start = now
                subscription.current_period_end = next_month(now)
            else:
                subscription.current_period_end = next_month(
                    max(now, subscription.current_period_end or now)
                )
            subscription.plan = SubscriptionPlan.PREMIUM
        account.provider_name = row.provider_name if result.mandate else None
        account.mandate_reference = result.mandate.reference if result.mandate else None
        account.method_label = result.mandate.label if result.mandate else None
        subscription.auto_renew = result.mandate is not None
        subscription.status = (
            SubscriptionStatus.ACTIVE if subscription.auto_renew else SubscriptionStatus.CANCELED
        )
        subscription.updated_at = now

    async def _defer(self, operation_id: UUID, claim: UUID | None, code: str) -> None:
        try:
            async with self.postgres.session() as session, session.begin():
                row = await session.scalar(
                    select(BillingOperationRecord)
                    .where(BillingOperationRecord.id == operation_id)
                    .with_for_update()
                )
                if row is not None and row.status == "PENDING" and row.claim_token == claim:
                    row.claim_token = row.lease_until = None
                    row.last_error = code
                    row.next_attempt_at = datetime.now(UTC) + timedelta(
                        seconds=min(60, 2 ** min(row.attempts, 5))
                    )
        except SQLAlchemyError:
            pass  # Persisted lease expiry is the recovery mechanism if PostgreSQL is down.

    async def run_once(self, stop: asyncio.Event | None = None) -> None:
        if self.provider is None:
            return
        async with self.postgres.session() as session:
            ids = list(
                await session.scalars(
                    select(BillingOperationRecord.id)
                    .where(
                        BillingOperationRecord.status == "PENDING",
                        BillingOperationRecord.provider_name == self.provider.name,
                        BillingOperationRecord.next_attempt_at <= datetime.now(UTC),
                        or_(
                            BillingOperationRecord.lease_until.is_(None),
                            BillingOperationRecord.lease_until <= datetime.now(UTC),
                        ),
                    )
                    .order_by(BillingOperationRecord.next_attempt_at)
                    .limit(20)
                )
            )
        for operation_id in ids:
            if stop is not None and stop.is_set():
                break
            await self.process(operation_id)

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                await self.run_once(stop)
            except SQLAlchemyError:
                pass
            try:
                await asyncio.wait_for(stop.wait(), timeout=5)
            except TimeoutError:
                pass
