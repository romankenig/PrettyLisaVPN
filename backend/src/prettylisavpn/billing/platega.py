"""Monthly SBP provider and crash-safe settlement of authenticated charge evidence."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.exc import SQLAlchemyError

from prettylisavpn.billing.domain import RouteCapability
from prettylisavpn.billing.model import BillingAccountRecord, BillingOperationRecord
from prettylisavpn.billing.operations_domain import (
    Action,
    Currency,
    PaymentRoute,
    ProviderMandate,
    ProviderRequest,
    ProviderResult,
    next_month,
)
from prettylisavpn.billing.platega_api import (
    PlategaPort,
    PlategaSubscription,
    PlategaUnavailable,
    description_for,
    subscription_url,
)
from prettylisavpn.billing.platega_model import PlategaAgreementRecord, PlategaChargeRecord
from prettylisavpn.connections import Postgres
from prettylisavpn.subscriptions.domain import SubscriptionPlan, SubscriptionStatus
from prettylisavpn.subscriptions.model import SubscriptionRecord
from prettylisavpn.users.model import UserRecord


class PlategaBillingProvider:
    name = "platega"
    sandbox = False
    routes: frozenset[PaymentRoute] = frozenset({"SBP"})
    capabilities: tuple[RouteCapability, ...] = (
        RouteCapability(id="SBP", currencies=("RUB",), recurring_currencies=("RUB",)),
    )
    redirect_hosts: frozenset[str] = frozenset({"pay.platega.io"})

    def __init__(self, postgres: Postgres, api: PlategaPort) -> None:
        self.postgres, self.api = postgres, api

    def supports(self, action: Action, route: PaymentRoute | None, currency: Currency) -> bool:
        return currency == "RUB" and (
            (action == "SUBSCRIBE" and route == "SBP") or (action == "CANCEL" and route is None)
        )

    def supports_amount(self, route: PaymentRoute, currency: Currency, amount_minor: int) -> bool:
        return route == "SBP" and currency == "RUB" and amount_minor > 0 and amount_minor % 100 == 0

    async def reconcile(self, request: ProviderRequest) -> ProviderResult:
        if request.action == "CANCEL":
            return await self._cancel(request)
        if (
            not self.supports(request.action, request.payment_route, request.currency)
            or request.amount_minor is None
        ):
            raise ValueError("Unsupported Platega operation")
        if request.previous_mandate_reference:
            raise ValueError("An active authority must be canceled before a new subscription")
        first_create = False
        async with self.postgres.session() as session, session.begin():
            operation = await session.scalar(
                select(BillingOperationRecord)
                .where(BillingOperationRecord.id == request.operation_id)
                .with_for_update()
            )
            if (
                operation is None
                or operation.user_id != request.account_id
                or operation.provider_name != self.name
                or operation.quote["amount_minor"] != request.amount_minor
            ):
                raise ValueError("Invalid Platega operation binding")
            row = await session.get(PlategaAgreementRecord, request.operation_id)
            if row is None:
                row = PlategaAgreementRecord(
                    operation_id=request.operation_id,
                    user_id=request.account_id,
                    create_started_at=datetime.now(UTC),
                )
                session.add(row)
                first_create = True
            user = await session.get(UserRecord, request.account_id)
            if user is None:
                raise ValueError("Account unavailable")
            email = user.email
        # The create fence above is committed even if the process dies before HTTP.
        if row.provider_id is None:
            if first_create:
                created = await self.api.create(request.operation_id, request.amount_minor, email)
                provider_id = created.id
            else:
                matches = await self.api.recover(
                    request.operation_id, row.create_started_at - timedelta(minutes=5)
                )
                if len(matches) != 1:
                    return ProviderResult(operation_id=request.operation_id, status="PENDING")
                provider_id = matches[0].id
            async with self.postgres.session() as session, session.begin():
                current = await session.get(
                    PlategaAgreementRecord, request.operation_id, with_for_update=True
                )
                if current is None or current.provider_id not in (None, provider_id):
                    raise ValueError("Provider binding changed")
                current.provider_id = provider_id
        else:
            provider_id = row.provider_id
        authority = await self.refresh_agreement(request.operation_id)
        async with self.postgres.session() as session:
            row = await session.get(PlategaAgreementRecord, request.operation_id)
            charge = (
                await session.get(PlategaChargeRecord, row.first_payment_id)
                if row and row.first_payment_id
                else None
            )
        if charge and charge.status == "CONFIRMED" and charge.verified_at:
            if authority.status not in ("Active", "PastDue", "Cancelled"):
                return ProviderResult(operation_id=request.operation_id, status="PENDING")
            return ProviderResult(
                operation_id=request.operation_id,
                status="SUCCEEDED",
                amount_minor=charge.amount_minor,
                currency="RUB",
                mandate=ProviderMandate(
                    reference=str(provider_id),
                    label="СБП — привязанный счёт",
                    kind="SBP",
                    next_charge_at=authority.next_charge_at,
                )
                if authority.status != "Cancelled"
                else None,
                renewal_canceled=authority.status == "Cancelled",
            )
        # A subscription status or success URL alone is never proof of payment.
        if authority.status == "Failed" and authority.successful_charges == 0:
            return ProviderResult(operation_id=request.operation_id, status="FAILED")
        if authority.status == "Cancelled":
            # Reconcile pending receipts before releasing the account for a fresh purchase.
            async with self.postgres.session() as session:
                pending = await session.scalar(
                    select(PlategaChargeRecord.id).where(
                        PlategaChargeRecord.agreement_id == request.operation_id,
                        PlategaChargeRecord.verified_at.is_(None),
                    )
                )
            if pending is None and authority.successful_charges == 0:
                return ProviderResult(operation_id=request.operation_id, status="CANCELED")
        return ProviderResult(
            operation_id=request.operation_id,
            status="PENDING",
            redirect_url=subscription_url(provider_id)
            if authority.status == "PendingAgreement"
            else None,
        )

    async def _cancel(self, request: ProviderRequest) -> ProviderResult:
        if not request.previous_mandate_reference:
            raise ValueError("No Platega authority to cancel")
        provider_id = UUID(request.previous_mandate_reference)
        async with self.postgres.session() as session:
            row = await session.scalar(
                select(PlategaAgreementRecord).where(
                    PlategaAgreementRecord.provider_id == provider_id,
                    PlategaAgreementRecord.user_id == request.account_id,
                )
            )
        if row is None:
            raise ValueError("Unknown Platega authority")
        await self.api.cancel(
            provider_id
        )  # Documented idempotent operation; retry uses the same ID.
        authority = await self.api.subscription(provider_id)
        if authority.status != "Cancelled":
            return ProviderResult(operation_id=request.operation_id, status="PENDING")
        return ProviderResult(
            operation_id=request.operation_id,
            status="SUCCEEDED",
            recurring_stopped=True,
            previous_mandate_revoked=True,
            renewal_canceled=True,
        )

    async def refresh_agreement(self, operation_id: UUID) -> PlategaSubscription:
        async with self.postgres.session() as session:
            row = await session.get(PlategaAgreementRecord, operation_id)
            operation = await session.get(BillingOperationRecord, operation_id)
            if row is None or row.provider_id is None or operation is None:
                raise PlategaUnavailable
        authority = await self.api.subscription(row.provider_id)
        if authority.amount_minor != operation.quote[
            "amount_minor"
        ] or authority.description != description_for(operation_id):
            raise PlategaUnavailable
        async with self.postgres.session() as session, session.begin():
            subscription = await session.scalar(
                select(SubscriptionRecord)
                .where(SubscriptionRecord.user_id == row.user_id)
                .with_for_update()
            )
            current = await session.get(PlategaAgreementRecord, operation_id, with_for_update=True)
            if current is None:
                raise PlategaUnavailable
            current.state, current.next_charge_at, current.checked_at = (
                authority.status,
                authority.next_charge_at,
                datetime.now(UTC),
            )
            account = await session.get(BillingAccountRecord, row.user_id)
            if (
                account
                and subscription
                and operation.status == "SUCCEEDED"
                and account.provider_name == self.name
                and account.mandate_reference == str(row.provider_id)
            ):
                account.next_charge_at = (
                    authority.next_charge_at if authority.status == "Active" else None
                )
                if authority.status == "Cancelled":
                    pending = await session.scalar(
                        select(BillingOperationRecord).where(
                            BillingOperationRecord.user_id == row.user_id,
                            BillingOperationRecord.status == "PENDING",
                        )
                    )
                    if pending is None:
                        self._clear_method(account)
                        account.renewal_canceled_at = datetime.now(UTC)
                        subscription.auto_renew, subscription.status = (
                            False,
                            SubscriptionStatus.CANCELED,
                        )
                        subscription.updated_at = datetime.now(UTC)
        if authority.successful_charges:
            await self.recover_receipts(operation_id, authority, operation.quote["amount_minor"])
        return authority

    async def recover_receipts(
        self, operation_id: UUID, authority: PlategaSubscription, amount: int
    ) -> None:
        async with self.postgres.session() as session:
            count = await session.scalar(
                select(func.count())
                .select_from(PlategaChargeRecord)
                .where(
                    PlategaChargeRecord.agreement_id == operation_id,
                    PlategaChargeRecord.verified_at.is_not(None),
                    PlategaChargeRecord.status == "CONFIRMED",
                )
            )
        if (count or 0) >= authority.successful_charges:
            return
        receipts = await self.api.recover_payments(operation_id, authority.created_at)
        async with self.postgres.session() as session, session.begin():
            agreement = await session.get(
                PlategaAgreementRecord, operation_id, with_for_update=True
            )
            if agreement is None:
                raise PlategaUnavailable
            for receipt in receipts:
                if receipt.amount_minor != amount or receipt.description != description_for(
                    operation_id
                ):
                    raise PlategaUnavailable
                existing = await session.get(PlategaChargeRecord, receipt.id, with_for_update=True)
                if existing is not None:
                    if existing.agreement_id != operation_id or existing.amount_minor != amount:
                        raise PlategaUnavailable
                    continue
                session.add(
                    PlategaChargeRecord(
                        id=receipt.id,
                        agreement_id=operation_id,
                        amount_minor=amount,
                        currency="RUB",
                        status="PENDING",
                        received_at=datetime.now(UTC),
                    )
                )

    @staticmethod
    def _clear_method(account: BillingAccountRecord) -> None:
        account.provider_name = account.mandate_reference = account.method_label = None
        account.method_kind = account.card_brand = account.card_last4 = None
        account.next_charge_at = None

    async def verify_charge(self, payment_id: UUID) -> None:
        async with self.postgres.session() as session:
            row = await session.get(PlategaChargeRecord, payment_id)
            agreement = await session.get(PlategaAgreementRecord, row.agreement_id) if row else None
            operation = await session.get(BillingOperationRecord, row.agreement_id) if row else None
            if row is None or agreement is None or operation is None:
                raise PlategaUnavailable
        receipt = await self.api.payment(payment_id)
        if (
            receipt.amount_minor != row.amount_minor
            or receipt.amount_minor != operation.quote["amount_minor"]
            or receipt.currency != row.currency
        ):
            raise PlategaUnavailable
        async with self.postgres.session() as session, session.begin():
            current_agreement = await session.get(
                PlategaAgreementRecord, row.agreement_id, with_for_update=True
            )
            current = await session.get(PlategaChargeRecord, payment_id, with_for_update=True)
            if current is None or current_agreement is None:
                raise PlategaUnavailable
            current.status, current.verified_at = receipt.status, datetime.now(UTC)
            if receipt.status == "CONFIRMED" and operation.status in ("FAILED", "CANCELED"):
                current.review_required = True
            if receipt.status == "CONFIRMED" and current_agreement.first_payment_id is None:
                current_agreement.first_payment_id = payment_id
            if receipt.status in ("CHARGEBACKED", "PARTIALLY_REFUNDED", "DISPUTED"):
                current.review_required = True

    async def apply_recurring(self, payment_id: UUID) -> None:
        async with self.postgres.session() as session, session.begin():
            charge = await session.get(PlategaChargeRecord, payment_id)
            agreement = (
                await session.get(PlategaAgreementRecord, charge.agreement_id) if charge else None
            )
            if charge is None or agreement is None:
                return
            subscription = await session.scalar(
                select(SubscriptionRecord)
                .where(SubscriptionRecord.user_id == agreement.user_id)
                .with_for_update()
            )
            charge = await session.get(
                PlategaChargeRecord, payment_id, populate_existing=True, with_for_update=True
            )
            operation = await session.get(BillingOperationRecord, agreement.operation_id)
            if (
                charge is None
                or charge.applied_at
                or charge.review_required
                or charge.status != "CONFIRMED"
                or charge.verified_at is None
                or subscription is None
                or operation is None
                or operation.status != "SUCCEEDED"
            ):
                return
            if payment_id == agreement.first_payment_id:
                charge.applied_at = operation.completed_at
                return  # First payment was atomically projected by BillingWorker.
            now = datetime.now(UTC)
            subscription.current_period_end = next_month(
                max(now, subscription.current_period_end or now)
            )
            if subscription.plan is SubscriptionPlan.FREE:
                subscription.current_period_start = now
            if subscription.plan is not SubscriptionPlan.PLATINUM:
                subscription.plan = SubscriptionPlan.PREMIUM
            subscription.status = (
                SubscriptionStatus.ACTIVE
                if subscription.auto_renew
                else SubscriptionStatus.CANCELED
            )
            subscription.updated_at = now
            charge.applied_at = now

    async def run_once(self, stop: asyncio.Event | None = None) -> None:
        cutoff = datetime.now(UTC) - timedelta(seconds=60)
        async with self.postgres.session() as session:
            charges = list(
                await session.scalars(
                    select(PlategaChargeRecord.id)
                    .where(
                        PlategaChargeRecord.review_required.is_(False),
                        or_(
                            PlategaChargeRecord.verified_at.is_(None),
                            (PlategaChargeRecord.status == "PENDING")
                            & (PlategaChargeRecord.verified_at < cutoff),
                            (PlategaChargeRecord.status == "CONFIRMED")
                            & PlategaChargeRecord.applied_at.is_(None),
                        ),
                    )
                    .order_by(PlategaChargeRecord.received_at)
                    .limit(100)
                )
            )
            agreements = list(
                await session.scalars(
                    select(PlategaAgreementRecord.operation_id)
                    .where(
                        PlategaAgreementRecord.provider_id.is_not(None),
                        or_(
                            PlategaAgreementRecord.checked_at.is_(None),
                            PlategaAgreementRecord.checked_at < cutoff,
                        ),
                    )
                    .order_by(PlategaAgreementRecord.checked_at.asc().nullsfirst())
                    .limit(20)
                )
            )
        for payment_id in charges:
            if stop is not None and stop.is_set():
                return
            try:
                await self.verify_charge(payment_id)
                await self.apply_recurring(payment_id)
            except (PlategaUnavailable, SQLAlchemyError, ValueError):
                pass  # Durable receipt remains pending; never log a provider payload.
        for operation_id in agreements:
            if stop is not None and stop.is_set():
                return
            try:
                await self.refresh_agreement(operation_id)
            except (PlategaUnavailable, SQLAlchemyError, ValueError):
                pass

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
