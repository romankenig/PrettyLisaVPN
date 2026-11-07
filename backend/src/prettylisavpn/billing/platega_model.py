"""Durable Platega request fence and minimal authenticated payment evidence."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from prettylisavpn.database import Base


class PlategaAgreementRecord(Base):
    __tablename__ = "billing_platega_agreements"
    operation_id: Mapped[UUID] = mapped_column(
        ForeignKey("billing_operations.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider_id: Mapped[UUID | None] = mapped_column(unique=True)
    create_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    first_payment_id: Mapped[UUID | None] = mapped_column(unique=True)
    state: Mapped[str | None] = mapped_column(String(32))
    next_charge_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PlategaChargeRecord(Base):
    __tablename__ = "billing_platega_charges"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    agreement_id: Mapped[UUID] = mapped_column(
        ForeignKey("billing_platega_agreements.operation_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_required: Mapped[bool] = mapped_column(nullable=False, default=False)
    __table_args__ = (
        CheckConstraint(
            "amount_minor > 0 AND amount_minor <= 1000000000000", name="ck_platega_charge_amount"
        ),
        CheckConstraint("currency = 'RUB'", name="ck_platega_charge_currency"),
        CheckConstraint(
            "status IN ('PENDING','CONFIRMED','CANCELED','CHARGEBACKED',"
            "'PARTIALLY_REFUNDED','DISPUTED')",
            name="ck_platega_charge_status",
        ),
    )
