"""Durable daily observations and atomically published private aggregate snapshots."""

from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from prettylisavpn.database import Base


class ActivityRecord(Base):
    __tablename__ = "product_activity_days"
    __table_args__ = (
        CheckConstraint("plan IN ('FREE','PREMIUM','PLATINUM','UNKNOWN')", name="ck_activity_plan"),
        Index("ix_product_activity_day", "day"),
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    plan: Mapped[str] = mapped_column(String(16))


class AnalyticsSnapshotRecord(Base):
    __tablename__ = "product_analytics_snapshots"
    through_date: Mapped[date] = mapped_column(Date, primary_key=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    data: Mapped[dict[str, Any]] = mapped_column(JSONB)


class AnalyticsCollectionRecord(Base):
    __tablename__ = "product_analytics_collection"
    __table_args__ = (CheckConstraint("id = 1", name="ck_analytics_collection_singleton"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
