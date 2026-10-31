"""Operator-maintained service catalog, never browsing observations."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, String, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from prettylisavpn.database import Base


class TrafficServiceRecord(Base):
    __tablename__ = "traffic_services"
    __table_args__ = (
        CheckConstraint("category IN ('popular', 'whitelist')", name="ck_traffic_service_category"),
        CheckConstraint("jsonb_typeof(domains) = 'array'", name="ck_traffic_service_domains"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    icon: Mapped[str] = mapped_column(String(40))
    category: Mapped[str] = mapped_column(String(16), server_default="popular")
    domains: Mapped[list[str]] = mapped_column(JSONB)
    enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
