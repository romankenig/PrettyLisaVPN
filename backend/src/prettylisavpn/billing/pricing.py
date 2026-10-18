"""Internal contract confirmation boundary; no public payment or mutation endpoint.

A future payment adapter must call this inside the same transaction that records
its confirmed subscription. Never infer historical prices from today's offers.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from prettylisavpn.billing.domain import DEFAULT_GROUP_ID, Catalog, CurrentPrice
from prettylisavpn.billing.model import (
    BillingCatalogRecord,
    ClientGroupMembershipRecord,
    SubscriptionPriceRecord,
)
from prettylisavpn.subscriptions.domain import SubscriptionPlan
from prettylisavpn.subscriptions.model import SubscriptionRecord
from prettylisavpn.subscriptions.repository import SubscriptionRepository


class PriceConfirmationError(ValueError):
    pass


async def lock_contract_price(
    session: AsyncSession,
    subscription_id: UUID,
    offer_id: UUID,
    currency: Literal["RUB", "USD"],
    expected_revision: UUID,
    at: datetime,
) -> CurrentPrice:
    if currency not in ("RUB", "USD") or at.tzinfo is None or at.utcoffset() is None:
        raise PriceConfirmationError("Invalid confirmation")
    await session.execute(text("SELECT pg_advisory_xact_lock(903115991)"))
    subscription = await session.scalar(
        select(SubscriptionRecord).where(SubscriptionRecord.id == subscription_id).with_for_update()
    )
    if (
        subscription is None
        or SubscriptionRepository._to_domain(subscription).effective_plan(at)
        is not SubscriptionPlan.PREMIUM
    ):
        raise PriceConfirmationError("Confirmed Premium period required")
    existing = await session.get(SubscriptionPriceRecord, subscription_id)
    if existing is not None:
        if (
            existing.offer_id != offer_id
            or existing.currency != currency
            or existing.catalog_revision != expected_revision
        ):
            raise PriceConfirmationError("Contract price is already fixed")
        return CurrentPrice(amount_minor=existing.amount_minor, currency=existing.currency)
    catalog = await session.get(BillingCatalogRecord, 1)
    if catalog is None or catalog.revision != expected_revision:
        raise PriceConfirmationError("Catalogue changed")
    membership = await session.get(ClientGroupMembershipRecord, subscription.user_id)
    group_id = membership.group_id if membership else DEFAULT_GROUP_ID
    offers = Catalog.model_validate(catalog.document).offers_for(group_id, at)
    offer = next((offer for offer in offers if offer.id == offer_id), None)
    if offer is None:
        raise PriceConfirmationError("Offer unavailable for account and date")
    price = getattr(offer.prices, currency)
    session.add(
        SubscriptionPriceRecord(
            subscription_id=subscription_id,
            group_id=group_id,
            offer_id=offer_id,
            offer_document=offer.model_dump(mode="json"),
            catalog_revision=expected_revision,
            amount_minor=price.amount_minor,
            currency=currency,
            locked_at=at,
        )
    )
    await session.flush()
    return CurrentPrice(amount_minor=price.amount_minor, currency=currency)
