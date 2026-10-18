"""Persist admission BEFORE provider IO. Retries never create another payment key."""

from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError

from prettylisavpn.auth.session_service import AuthenticatedSessionHandler
from prettylisavpn.billing.model import BillingOperationRecord
from prettylisavpn.billing.operations_domain import BillingCommand, BillingOperation
from prettylisavpn.billing.provider import BillingProvider, validate_provider
from prettylisavpn.billing.service import BillingUnavailableError, read_context
from prettylisavpn.billing.worker import BillingWorker
from prettylisavpn.connections import Postgres
from prettylisavpn.subscriptions.model import SubscriptionRecord


class BillingConflictError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code


class BillingDisabledError(RuntimeError):
    pass


class BillingOperationNotFoundError(RuntimeError):
    pass


class BillingOperationsPort(Protocol):
    async def start(self, token: str, command: BillingCommand) -> BillingOperation: ...
    async def get(self, token: str, operation_id: UUID) -> BillingOperation: ...


def public_operation(row: BillingOperationRecord) -> BillingOperation:
    return BillingOperation.model_validate(
        {"id": row.id, "status": row.status, "redirect_url": row.redirect_url}
    )


class BillingOperationsService:
    def __init__(
        self,
        postgres: Postgres,
        auth: AuthenticatedSessionHandler,
        provider: BillingProvider | None = None,
    ) -> None:
        validate_provider(provider)
        self.postgres, self.auth, self.provider = postgres, auth, provider
        self.worker = BillingWorker(postgres, provider)

    async def start(self, token: str, command: BillingCommand) -> BillingOperation:
        identity = await self.auth.authenticate(token)
        try:
            async with self.postgres.session() as session, session.begin():
                # Same lock order as catalogue publication/legacy price confirmation.
                await session.execute(text("SELECT pg_advisory_xact_lock(903115991)"))
                subscription = await session.scalar(
                    select(SubscriptionRecord)
                    .where(SubscriptionRecord.user_id == identity.user_id)
                    .with_for_update()
                )
                if subscription is None:
                    raise BillingUnavailableError
                existing = await session.scalar(
                    select(BillingOperationRecord).where(
                        BillingOperationRecord.user_id == identity.user_id,
                        BillingOperationRecord.request_id == command.request_id,
                    )
                )
                if existing is not None:
                    if existing.fingerprint != command.fingerprint():
                        raise BillingConflictError("BILLING_IDEMPOTENCY_CONFLICT")
                    operation_id = existing.id
                else:
                    if self.provider is None:
                        raise BillingDisabledError
                    context = await read_context(
                        session, identity.user_id, self.provider, datetime.now(UTC)
                    )
                    overview = context.overview
                    if overview.pending_operation_id is not None:
                        raise BillingConflictError("BILLING_OPERATION_IN_PROGRESS")
                    if overview.revision != command.expected_revision:
                        raise BillingConflictError("BILLING_REVISION_CHANGED")
                    if command.action not in overview.actions:
                        raise BillingConflictError("BILLING_ACTION_UNAVAILABLE")
                    if not self.provider.supports(
                        command.action, command.payment_route, command.currency
                    ):
                        raise BillingConflictError("BILLING_ROUTE_UNAVAILABLE")
                    offer = next(
                        (offer for offer in overview.offers if offer.id == command.offer_id), None
                    )
                    purchase = command.action in ("SUBSCRIBE", "RENEW")
                    if purchase and (
                        offer is None or command.payment_route not in self.provider.routes
                    ):
                        raise BillingConflictError("BILLING_OFFER_UNAVAILABLE")
                    if command.action == "RENEW" and (
                        overview.current_price is None
                        or overview.current_price.currency != command.currency
                    ):
                        raise BillingConflictError("BILLING_CURRENCY_LOCKED")
                    if purchase and not any(
                        cap.id == command.payment_route and command.currency in cap.currencies
                        for cap in overview.payment_routes
                    ):
                        raise BillingConflictError("BILLING_ROUTE_UNAVAILABLE")
                    now = datetime.now(UTC)
                    quote = {
                        "recurring_supported": any(
                            cap.id == command.payment_route
                            and command.currency in cap.recurring_currencies
                            for cap in overview.payment_routes
                        )
                        if purchase
                        else command.action == "CHANGE_METHOD",
                        "subscription_id": str(subscription.id),
                        "subscription_updated_at": subscription.updated_at.isoformat(),
                        "group_id": str(
                            context.price.group_id
                            if command.action == "RENEW" and context.price
                            else context.group_id
                        ),
                        "catalog_revision": str(
                            context.price.catalog_revision
                            if command.action == "RENEW" and context.price
                            else context.catalog_revision
                        ),
                        "offer": offer.model_dump(mode="json") if offer else None,
                        "amount_minor": getattr(offer.prices, command.currency).amount_minor
                        if offer
                        else None,
                        "previous_mandate_reference": context.account.mandate_reference
                        if context.account
                        else None,
                    }
                    operation_id = uuid4()
                    session.add(
                        BillingOperationRecord(
                            id=operation_id,
                            user_id=identity.user_id,
                            request_id=command.request_id,
                            fingerprint=command.fingerprint(),
                            command=command.model_dump(mode="json"),
                            quote=quote,
                            provider_name=self.provider.name,
                            status="PENDING",
                            next_attempt_at=now,
                            created_at=now,
                            attempts=0,
                        )
                    )
            # Transaction is durably committed before the first external call.
            await self.worker.process(operation_id)
            return await self._get_owned(identity.user_id, operation_id)
        except SQLAlchemyError:
            raise BillingUnavailableError from None

    async def _get_owned(self, user_id: UUID, operation_id: UUID) -> BillingOperation:
        async with self.postgres.session() as session:
            row = await session.scalar(
                select(BillingOperationRecord).where(
                    BillingOperationRecord.id == operation_id,
                    BillingOperationRecord.user_id == user_id,
                )
            )
            if row is None:
                raise BillingOperationNotFoundError
            return public_operation(row)

    async def get(self, token: str, operation_id: UUID) -> BillingOperation:
        identity = await self.auth.authenticate(token)
        try:
            await self._get_owned(identity.user_id, operation_id)
            await self.worker.process(operation_id)
            return await self._get_owned(identity.user_id, operation_id)
        except SQLAlchemyError:
            raise BillingUnavailableError from None
