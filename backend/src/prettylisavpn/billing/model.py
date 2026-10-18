"""Atomic PostgreSQL catalogue snapshot, independent of payment providers."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Integer, BigInteger, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from prettylisavpn.database import Base


class BillingCatalogRecord(Base):
    __tablename__ = "billing_catalog"
    __table_args__ = (CheckConstraint("id = 1", name="ck_billing_catalog_singleton"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    revision: Mapped[UUID] = mapped_column(nullable=False)
    document: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ClientGroupRecord(Base):
    __tablename__ = "client_groups"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)


class ClientGroupMembershipRecord(Base):
    __tablename__ = "client_group_memberships"
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    group_id: Mapped[UUID] = mapped_column(ForeignKey("client_groups.id"), nullable=False, index=True)


class SubscriptionPriceRecord(Base):
    """Immutable contract price, separate from the mutable acquisition catalogue."""
    __tablename__ = "subscription_prices"
    __table_args__ = (
        CheckConstraint("amount_minor > 0 AND amount_minor <= 1000000000000", name="ck_subscription_prices_amount"),
        CheckConstraint("currency IN ('RUB', 'USD')", name="ck_subscription_prices_currency"),
    )
    subscription_id: Mapped[UUID] = mapped_column(ForeignKey("subscriptions.id", ondelete="CASCADE"), primary_key=True)
    group_id: Mapped[UUID] = mapped_column(ForeignKey("client_groups.id"), nullable=False)
    offer_id: Mapped[UUID] = mapped_column(nullable=False)
    catalog_revision: Mapped[UUID] = mapped_column(nullable=False)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    locked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
