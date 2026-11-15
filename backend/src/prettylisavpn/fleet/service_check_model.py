"""One durable, restart-safe synthetic assessment per service and report day."""

from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Date, DateTime, Float, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from prettylisavpn.database import Base


class ServiceCheckRecord(Base):
    __tablename__ = "fleet_service_checks"
    __table_args__ = (Index("ix_service_check_due", "next_attempt_at"),)
    service_id: Mapped[UUID] = mapped_column(ForeignKey("traffic_services.id"), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    claim_token: Mapped[UUID | None]
    claim_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    score: Mapped[float | None] = mapped_column(Float)
    code: Mapped[str | None] = mapped_column(String(64))
