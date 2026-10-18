"""Shared monthly offer contract; money is never converted or inferred."""

import hashlib
import json
from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictInt, model_validator

from prettylisavpn.subscriptions.domain import Subscription, SubscriptionPlan


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class Price(StrictModel):
    amount_minor: StrictInt = Field(gt=0, le=1_000_000_000_000)
    original_amount_minor: StrictInt | None = Field(default=None, gt=0, le=1_000_000_000_000)

    @model_validator(mode="after")
    def valid_discount(self) -> Self:
        if self.original_amount_minor is not None and self.original_amount_minor <= self.amount_minor:
            raise ValueError("Original price must exceed the offered price")
        return self


class Prices(StrictModel):
    RUB: Price
    USD: Price


class Offer(StrictModel):
    id: UUID
    plan: Literal["PREMIUM"] = "PREMIUM"
    period: Literal["MONTH"] = "MONTH"
    prices: Prices


DEFAULT_GROUP_ID = UUID("e3a7f90a-983a-4d5d-8f93-4d536e00be01")


class ScheduledOffer(StrictModel):
    group_id: UUID
    valid_from: AwareDatetime
    valid_to: AwareDatetime | None = None
    offer: Offer

    @model_validator(mode="after")
    def valid_window(self) -> Self:
        if self.valid_to is not None and self.valid_to <= self.valid_from:
            raise ValueError("valid_to must follow valid_from")
        return self

    def active(self, at: datetime) -> bool:
        return self.valid_from <= at and (self.valid_to is None or at < self.valid_to)


class Catalog(StrictModel):
    schema_version: Literal[1] = 1
    entries: list[ScheduledOffer] = Field(default_factory=list, max_length=1000)

    @model_validator(mode="after")
    def unambiguous(self) -> Self:
        ids: set[UUID] = set()
        for index, entry in enumerate(self.entries):
            if entry.offer.id in ids:
                raise ValueError("Offer IDs must be unique")
            ids.add(entry.offer.id)
            for other in self.entries[:index]:
                if entry.group_id == other.group_id and (
                    other.valid_to is None or entry.valid_from < other.valid_to
                ) and (entry.valid_to is None or other.valid_from < entry.valid_to):
                    raise ValueError("Group offer windows must not overlap")
        return self

    def offers_for(self, group_id: UUID, at: datetime) -> list[Offer]:
        if at.tzinfo is None or at.utcoffset() is None:
            raise ValueError("at must be timezone-aware")
        return [entry.offer for entry in self.entries if entry.group_id == group_id and entry.active(at)]


class CurrentPrice(StrictModel):
    amount_minor: StrictInt = Field(gt=0, le=1_000_000_000_000)
    currency: Literal["RUB", "USD"]


class Overview(StrictModel):
    revision: str
    pending_operation_id: None = None
    plan: SubscriptionPlan
    status: Literal["FREE", "ACTIVE", "CANCELED", "EXPIRED"]
    paid_until: datetime | None
    auto_renew: bool
    current_price: CurrentPrice | None = None
    payment_method: None = None
    offers: list[Offer]
    actions: list[Literal["SUBSCRIBE", "RENEW", "CHANGE_METHOD", "CANCEL"]] = Field(default_factory=list, max_length=0)
    payment_operations_available: Literal[False] = False


def overview_for(subscription: Subscription, catalog: Catalog, catalog_revision: UUID | None, at: datetime, *, group_id: UUID = DEFAULT_GROUP_ID, current_price: CurrentPrice | None = None) -> Overview:
    effective_plan = subscription.effective_plan(at)
    paid = effective_plan is not SubscriptionPlan.FREE
    if paid:
        status: Literal["FREE", "ACTIVE", "CANCELED", "EXPIRED"] = "ACTIVE" if subscription.auto_renew else "CANCELED"
    else:
        status = "FREE" if subscription.plan is SubscriptionPlan.FREE else "EXPIRED"
    snapshot = Overview(
        revision="pending",
        plan=effective_plan,
        status=status,
        paid_until=subscription.current_period_end if subscription.plan is not SubscriptionPlan.FREE else None,
        auto_renew=subscription.auto_renew,
        current_price=current_price if subscription.plan is not SubscriptionPlan.FREE else None,
        offers=[offer for offer in catalog.offers_for(group_id, at) if not paid or offer.plan == effective_plan.value],
    )
    identity = {
        "subscription_id": str(subscription.id),
        "group_id": str(group_id),
        "subscription_updated_at": subscription.updated_at.isoformat(),
        "catalog_revision": str(catalog_revision) if catalog_revision is not None else None,
        "overview": snapshot.model_dump(mode="json", exclude={"revision"}),
    }
    revision = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return snapshot.model_copy(update={"revision": revision})
