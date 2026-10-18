"""Consistent account-scoped billing read model shared by quote admission."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import literal, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from prettylisavpn.auth.session_service import AuthenticatedSessionHandler
from prettylisavpn.billing.domain import DEFAULT_GROUP_ID, Catalog, CurrentPrice, Offer, Overview, PaymentMethod, overview_for
from prettylisavpn.billing.model import BillingAccountRecord, BillingCatalogRecord, BillingContractRecord, BillingOperationRecord, ClientGroupMembershipRecord, SubscriptionPriceRecord
from prettylisavpn.billing.operations_domain import Action
from prettylisavpn.billing.provider import BillingProvider, validate_provider
from prettylisavpn.connections import Postgres
from prettylisavpn.subscriptions.domain import SubscriptionPlan
from prettylisavpn.subscriptions.model import SubscriptionRecord
from prettylisavpn.subscriptions.repository import SubscriptionRepository


class BillingUnavailableError(RuntimeError):
    pass


class BillingOverviewPort(Protocol):
    async def overview(self, access_token: str) -> Overview: ...


@dataclass
class OverviewContext:
    overview: Overview
    subscription: SubscriptionRecord
    group_id: UUID
    catalog_revision: UUID | None
    account: BillingAccountRecord | None
    price: BillingContractRecord | SubscriptionPriceRecord | None


async def read_context(session: AsyncSession, user_id: UUID, provider: BillingProvider | None, at: datetime) -> OverviewContext:
    row = (await session.execute(
        select(SubscriptionRecord, BillingCatalogRecord, ClientGroupMembershipRecord, SubscriptionPriceRecord,
               BillingAccountRecord, BillingContractRecord, BillingOperationRecord)
        .select_from(SubscriptionRecord)
        .outerjoin(BillingCatalogRecord, literal(True))
        .outerjoin(ClientGroupMembershipRecord, ClientGroupMembershipRecord.user_id == SubscriptionRecord.user_id)
        .outerjoin(SubscriptionPriceRecord, SubscriptionPriceRecord.subscription_id == SubscriptionRecord.id)
        .outerjoin(BillingAccountRecord, BillingAccountRecord.user_id == SubscriptionRecord.user_id)
        .outerjoin(BillingContractRecord, BillingContractRecord.id == BillingAccountRecord.contract_id)
        .outerjoin(BillingOperationRecord, (BillingOperationRecord.user_id == SubscriptionRecord.user_id) & (BillingOperationRecord.status == "PENDING"))
        .where(SubscriptionRecord.user_id == user_id)
    )).one_or_none()
    if row is None:
        raise BillingUnavailableError
    record, catalog_record, membership, legacy_price, account, contract, pending = row
    price = contract or legacy_price
    offer = Offer.model_validate(price.offer_document) if price else None
    if price and offer and (price.subscription_id != record.id or getattr(offer.prices, price.currency).amount_minor != price.amount_minor):
        raise ValueError("Invalid contract price")
    if legacy_price and not contract and offer and offer.id != legacy_price.offer_id:
        raise ValueError("Invalid legacy contract")
    group_id = membership.group_id if membership else DEFAULT_GROUP_ID
    subscription = SubscriptionRepository._to_domain(record)
    catalog = Catalog.model_validate(catalog_record.document) if catalog_record else Catalog()
    effective = subscription.effective_plan(at)
    ours = bool(account and provider and account.provider_name == provider.name and account.mandate_reference)
    method = PaymentMethod(provider=account.provider_name, label=account.method_label) if account and account.provider_name and account.mandate_reference and account.method_label and effective is not SubscriptionPlan.FREE else None
    actions: list[Action] = []
    if provider and not pending and subscription.plan is not SubscriptionPlan.PLATINUM:
        if ours and subscription.auto_renew:
            actions.append("CANCEL")
        if not subscription.auto_renew or ours:
            if effective is SubscriptionPlan.FREE and catalog.offers_for(group_id, at) and provider.routes:
                actions.append("SUBSCRIBE")
            elif effective is SubscriptionPlan.PREMIUM and price and offer:
                if provider.routes:
                    actions.append("RENEW")
                actions.append("CHANGE_METHOD")
    overview = overview_for(subscription, catalog, catalog_record.revision if catalog_record else None, at,
        group_id=group_id, current_price=CurrentPrice(amount_minor=price.amount_minor, currency=price.currency) if price else None,
        contract_offer=offer, pending_id=pending.id if pending else None, actions=actions, payment_method=method,
        operations_available=provider is not None or pending is not None)
    return OverviewContext(overview, record, group_id, catalog_record.revision if catalog_record else None, account, price)


class BillingOverviewService:
    def __init__(self, postgres: Postgres, authenticated_sessions: AuthenticatedSessionHandler, provider: BillingProvider | None = None) -> None:
        validate_provider(provider)
        self.postgres = postgres
        self.authenticated_sessions = authenticated_sessions
        self.provider = provider

    async def overview(self, access_token: str) -> Overview:
        identity = await self.authenticated_sessions.authenticate(access_token)
        try:
            async with self.postgres.session() as session:
                return (await read_context(session, identity.user_id, self.provider, datetime.now(UTC))).overview
        except (SQLAlchemyError, ValidationError, ValueError):
            raise BillingUnavailableError from None
