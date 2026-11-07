"""Anonymous acquisition prices; private groups and contract prices never leave this port."""

from datetime import UTC, datetime
from typing import Protocol

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from prettylisavpn.billing.domain import DEFAULT_GROUP_ID, Catalog, Offer, StrictModel
from prettylisavpn.billing.model import BillingCatalogRecord
from prettylisavpn.billing.service import BillingUnavailableError
from prettylisavpn.connections import Postgres


class PublicCatalog(StrictModel):
    offers: list[Offer]


class PublicCatalogPort(Protocol):
    async def read(self) -> PublicCatalog: ...


class PublicCatalogService:
    def __init__(self, postgres: Postgres) -> None:
        self.postgres = postgres

    async def read(self) -> PublicCatalog:
        try:
            async with self.postgres.session() as session:
                row = await session.get(BillingCatalogRecord, 1)
                catalog = Catalog.model_validate(row.document) if row else Catalog()
                return PublicCatalog(offers=catalog.offers_for(DEFAULT_GROUP_ID, datetime.now(UTC)))
        except (SQLAlchemyError, ValidationError, ValueError):
            raise BillingUnavailableError from None
