"""Atomic PostgreSQL catalogue snapshot, independent of payment providers."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
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
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    group_id: Mapped[UUID] = mapped_column(
        ForeignKey("client_groups.id"), nullable=False, index=True
    )


class SubscriptionPriceRecord(Base):
    """Immutable contract price, separate from the mutable acquisition catalogue."""

    __tablename__ = "subscription_prices"
    __table_args__ = (
        CheckConstraint(
            "amount_minor > 0 AND amount_minor <= 1000000000000",
            name="ck_subscription_prices_amount",
        ),
        CheckConstraint("currency IN ('RUB', 'USD')", name="ck_subscription_prices_currency"),
    )
    subscription_id: Mapped[UUID] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="CASCADE"), primary_key=True
    )
    group_id: Mapped[UUID] = mapped_column(ForeignKey("client_groups.id"), nullable=False)
    offer_id: Mapped[UUID] = mapped_column(nullable=False)
    catalog_revision: Mapped[UUID] = mapped_column(nullable=False)
    offer_document: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    locked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class BillingContractRecord(Base):
    """Append-only confirmed contracts; new contracts never overwrite prior prices."""

    __tablename__ = "billing_contracts"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    subscription_id: Mapped[UUID] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False
    )
    group_id: Mapped[UUID] = mapped_column(ForeignKey("client_groups.id"), nullable=False)
    catalog_revision: Mapped[UUID] = mapped_column(nullable=False)
    offer_document: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    locked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (
        CheckConstraint(
            "amount_minor > 0 AND amount_minor <= 1000000000000", name="ck_billing_contracts_amount"
        ),
        CheckConstraint("currency IN ('RUB', 'USD')", name="ck_billing_contracts_currency"),
    )


class BillingAccountRecord(Base):
    __tablename__ = "billing_accounts"
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    contract_id: Mapped[UUID | None] = mapped_column(ForeignKey("billing_contracts.id"))
    provider_name: Mapped[str | None] = mapped_column(String(64))
    mandate_reference: Mapped[str | None] = mapped_column(String(200))
    method_label: Mapped[str | None] = mapped_column(String(100))


class BillingOperationRecord(Base):
    __tablename__ = "billing_operations"
    __table_args__ = (
        UniqueConstraint("user_id", "request_id", name="uq_billing_operations_user_request"),
        CheckConstraint(
            "status IN ('PENDING', 'SUCCEEDED', 'FAILED', 'CANCELED')",
            name="ck_billing_operations_status",
        ),
        Index(
            "uq_billing_operations_user_pending",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'PENDING'"),
        ),
        Index(
            "ix_billing_operations_retry",
            "next_attempt_at",
            postgresql_where=text("status = 'PENDING'"),
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    request_id: Mapped[UUID] = mapped_column(nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    command: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    quote: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    provider_name: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")
    redirect_url: Mapped[str | None] = mapped_column(String(2048))
    claim_token: Mapped[UUID | None] = mapped_column()
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
