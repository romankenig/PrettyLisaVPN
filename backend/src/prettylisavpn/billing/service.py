"""Consistent account-scoped billing read model shared by quote admission."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol, cast
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import literal, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from prettylisavpn.auth.session_service import AuthenticatedSessionHandler
from prettylisavpn.billing.domain import (
    DEFAULT_GROUP_ID,
    Catalog,
    CurrentPrice,
    Offer,
    Overview,
    PaymentMethod,
    overview_for,
)
from prettylisavpn.billing.model import (
    BillingAccountRecord,
    BillingCatalogRecord,
    BillingContractRecord,
    BillingOperationRecord,
    ClientGroupMembershipRecord,
    SubscriptionPriceRecord,
)
from prettylisavpn.billing.operations_domain import Action, Currency
from prettylisavpn.billing.provider import BillingProvider, route_capabilities, validate_provider
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


async def read_context(
    session: AsyncSession, user_id: UUID, provider: BillingProvider | None, at: datetime
) -> OverviewContext:
    row = (
        await session.execute(
            select(
                SubscriptionRecord,
                BillingCatalogRecord,
                ClientGroupMembershipRecord,
                SubscriptionPriceRecord,
                BillingAccountRecord,
                BillingContractRecord,
                BillingOperationRecord,
            )
            .select_from(SubscriptionRecord)
            .outerjoin(BillingCatalogRecord, literal(True))
            .outerjoin(
                ClientGroupMembershipRecord,
                ClientGroupMembershipRecord.user_id == SubscriptionRecord.user_id,
            )
            .outerjoin(
                SubscriptionPriceRecord,
                SubscriptionPriceRecord.subscription_id == SubscriptionRecord.id,
            )
            .outerjoin(
                BillingAccountRecord, BillingAccountRecord.user_id == SubscriptionRecord.user_id
            )
            .outerjoin(
                BillingContractRecord, BillingContractRecord.id == BillingAccountRecord.contract_id
            )
            .outerjoin(
                BillingOperationRecord,
                (BillingOperationRecord.user_id == SubscriptionRecord.user_id)
                & (BillingOperationRecord.status == "PENDING"),
            )
            .where(SubscriptionRecord.user_id == user_id)
        )
    ).one_or_none()
    if row is None:
        raise BillingUnavailableError
    record, catalog_record, membership, legacy_price, account, contract, pending = row
    price = contract or legacy_price
    offer = Offer.model_validate(price.offer_document) if price else None
    if (
        price
        and offer
        and (
            price.subscription_id != record.id
            or getattr(offer.prices, price.currency).amount_minor != price.amount_minor
        )
    ):
        raise ValueError("Invalid contract price")
    if legacy_price and not contract and offer and offer.id != legacy_price.offer_id:
        raise ValueError("Invalid legacy contract")
    group_id = membership.group_id if membership else DEFAULT_GROUP_ID
    subscription = SubscriptionRepository._to_domain(record)
    catalog = Catalog.model_validate(catalog_record.document) if catalog_record else Catalog()
    new_contract_required = bool(
        (price is None and subscription.plan in (SubscriptionPlan.FREE, SubscriptionPlan.PLATINUM))
        or (account and account.renewal_canceled_at is not None)
    )
    purchase_action: Action = "SUBSCRIBE" if new_contract_required else "RENEW"
    locked_currency = (
        cast(Currency, price.currency) if purchase_action == "RENEW" and price else None
    )
    routes = route_capabilities(provider, purchase_action, locked_currency)
    method_currency: Currency = cast(Currency, price.currency) if price else "RUB"
    ours = bool(
        account
        and provider
        and account.provider_name == provider.name
        and account.mandate_reference
    )
    method = (
        PaymentMethod(
            provider=account.provider_name,
            label=account.method_label,
            kind=cast("Literal['CARD', 'SBP', 'UNKNOWN']", account.method_kind or "UNKNOWN"),
            card_brand=cast(
                "Literal['visa', 'mastercard', 'mir', 'unknown'] | None", account.card_brand
            ),
            card_last4=account.card_last4,
        )
        if account and account.provider_name and account.mandate_reference and account.method_label
        else None
    )
    foreign_mandate = bool(
        account
        and provider
        and account.mandate_reference
        and account.provider_name != provider.name
    )
    actions: list[Action] = []
    if provider and not pending and not foreign_mandate:
        if ours and subscription.auto_renew and provider.supports("CANCEL", None, method_currency):
            actions.append("CANCEL")
        if not subscription.auto_renew or ours:
            if (
                new_contract_required
                and not (account and account.mandate_reference)
                and catalog.offers_for(group_id, at)
                and any(cap.currencies for cap in routes)
            ):
                actions.append("SUBSCRIBE")
            elif not new_contract_required and price and offer:
                if any(cap.currencies for cap in routes):
                    actions.append("RENEW")
                if (
                    ours
                    and provider.supports("CHANGE_METHOD", None, method_currency)
                    and any(
                        method_currency in cap.recurring_currencies for cap in provider.capabilities
                    )
                ):
                    actions.append("CHANGE_METHOD")
    overview = overview_for(
        subscription,
        catalog,
        catalog_record.revision if catalog_record else None,
        at,
        group_id=group_id,
        current_price=CurrentPrice(amount_minor=price.amount_minor, currency=price.currency)
        if price
        else None,
        contract_offer=offer,
        pending_id=pending.id if pending else None,
        actions=actions,
        payment_method=method,
        operations_available=provider is not None or pending is not None,
        provider_mode="SANDBOX"
        if provider is not None and provider.sandbox
        else "LIVE"
        if provider is not None
        else "DISABLED",
        payment_routes=routes,
        next_charge_at=account.next_charge_at if account else None,
        new_contract_required=new_contract_required,
    )
    return OverviewContext(
        overview,
        record,
        group_id,
        catalog_record.revision if catalog_record else None,
        account,
        price,
    )


class BillingOverviewService:
    def __init__(
        self,
        postgres: Postgres,
        authenticated_sessions: AuthenticatedSessionHandler,
        provider: BillingProvider | None = None,
    ) -> None:
        validate_provider(provider)
        self.postgres = postgres
        self.authenticated_sessions = authenticated_sessions
        self.provider = provider

    async def overview(self, access_token: str) -> Overview:
        identity = await self.authenticated_sessions.authenticate(access_token)
        return await self.overview_for_account(identity.user_id)

    async def overview_for_account(self, user_id: UUID) -> Overview:
        try:
            async with self.postgres.session() as session:
                return (
                    await read_context(session, user_id, self.provider, datetime.now(UTC))
                ).overview
        except (SQLAlchemyError, ValidationError, ValueError):
            raise BillingUnavailableError from None
