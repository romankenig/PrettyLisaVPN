"""Durable daily observations and atomically published private aggregate snapshots."""

from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from prettylisavpn.database import Base


class ActivityRecord(Base):
    __tablename__ = "product_activity_days"
    __table_args__ = (
        CheckConstraint(
            "plan IN ('DEMO','FREE','PREMIUM','PLATINUM','UNKNOWN')", name="ck_activity_plan"
        ),
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
    app_versions_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AppActivityRecord(Base):
    """Latest reported app version per active device/day, without request details."""

    __tablename__ = "product_app_activity_days"
    __table_args__ = (Index("ix_app_activity_day", "day"),)
    device_id: Mapped[UUID] = mapped_column(
        ForeignKey("devices.id", ondelete="CASCADE"), primary_key=True
    )
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    platform: Mapped[str] = mapped_column(String(32))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    app_version: Mapped[str | None] = mapped_column(String(100))
    version_observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SessionSilenceRecord(Base):
    """Counter-only first-silence evidence; no destination or packet data."""

    __tablename__ = "product_session_silence"
    lease_id: Mapped[UUID] = mapped_column(
        ForeignKey("client_wireguard_leases.id", ondelete="CASCADE"), primary_key=True
    )
    observed_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    quiet_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_silence_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    complete: Mapped[bool] = mapped_column(Boolean)
