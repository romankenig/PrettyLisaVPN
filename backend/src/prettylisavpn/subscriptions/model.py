"""SQLAlchemy mapping for subscriptions."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from prettylisavpn.database import Base
from prettylisavpn.subscriptions.domain import SubscriptionPlan, SubscriptionStatus


def utc_now() -> datetime:
    return datetime.now(UTC)


class SubscriptionRecord(Base):
    __tablename__ = "subscriptions"
    __table_args__ = (
        CheckConstraint(
            "current_period_end IS NULL OR current_period_end > current_period_start",
            name="ck_subscriptions_period",
        ),
        CheckConstraint(
            "plan <> 'FREE' OR NOT auto_renew",
            name="ck_subscriptions_free_no_auto_renew",
        ),
        CheckConstraint(
            "status <> 'CANCELED' OR NOT auto_renew",
            name="ck_subscriptions_canceled_no_auto_renew",
        ),
        Index(
            "ix_subscriptions_status_current_period_end",
            "status",
            "current_period_end",
            postgresql_where=text("current_period_end IS NOT NULL"),
        ),
        UniqueConstraint("user_id", name="uq_subscriptions_user_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    plan: Mapped[SubscriptionPlan] = mapped_column(
        Enum(SubscriptionPlan, name="subscription_plan"),
        default=SubscriptionPlan.FREE,
        server_default=SubscriptionPlan.FREE.value,
    )
    status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(SubscriptionStatus, name="subscription_status"),
        default=SubscriptionStatus.ACTIVE,
        server_default=SubscriptionStatus.ACTIVE.value,
    )
    current_period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    auto_renew: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, server_default=func.now()
    )
