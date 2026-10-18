"""Authenticated, consistent subscription and catalogue read model."""

from datetime import UTC, datetime
from typing import Protocol

from pydantic import ValidationError
from sqlalchemy import literal, select
from sqlalchemy.exc import SQLAlchemyError

from prettylisavpn.auth.session_service import AuthenticatedSessionHandler
from prettylisavpn.billing.domain import (
    DEFAULT_GROUP_ID,
    Catalog,
    CurrentPrice,
    Overview,
    overview_for,
)
from prettylisavpn.billing.model import (
    BillingCatalogRecord,
    ClientGroupMembershipRecord,
    SubscriptionPriceRecord,
)
from prettylisavpn.connections import Postgres
from prettylisavpn.subscriptions.model import SubscriptionRecord
from prettylisavpn.subscriptions.repository import SubscriptionRepository


class BillingUnavailableError(RuntimeError):
    pass


class BillingOverviewPort(Protocol):
    async def overview(self, access_token: str) -> Overview: ...


class BillingOverviewService:
    def __init__(self, postgres: Postgres, authenticated_sessions: AuthenticatedSessionHandler) -> None:
        self.postgres = postgres
        self.authenticated_sessions = authenticated_sessions

    async def overview(self, access_token: str) -> Overview:
        identity = await self.authenticated_sessions.authenticate(access_token)
        try:
            async with self.postgres.session() as session:
                # One SQL statement: prices and subscription come from the same MVCC snapshot.
                row = (await session.execute(
                    select(SubscriptionRecord, BillingCatalogRecord, ClientGroupMembershipRecord, SubscriptionPriceRecord)
                    .outerjoin(BillingCatalogRecord, literal(True))
                    .outerjoin(ClientGroupMembershipRecord, ClientGroupMembershipRecord.user_id == SubscriptionRecord.user_id)
                    .outerjoin(SubscriptionPriceRecord, SubscriptionPriceRecord.subscription_id == SubscriptionRecord.id)
                    .where(SubscriptionRecord.user_id == identity.user_id)
                )).one_or_none()
                if row is None:
                    raise BillingUnavailableError
                subscription_record, catalog_record, membership, price = row
                subscription = SubscriptionRepository._to_domain(subscription_record)
                catalog = Catalog.model_validate(catalog_record.document) if catalog_record else Catalog()
                return overview_for(subscription, catalog, catalog_record.revision if catalog_record else None, datetime.now(UTC), group_id=membership.group_id if membership else DEFAULT_GROUP_ID,
                    current_price=CurrentPrice(amount_minor=price.amount_minor, currency=price.currency) if price else None)
        except (SQLAlchemyError, ValidationError, ValueError):
            raise BillingUnavailableError from None
