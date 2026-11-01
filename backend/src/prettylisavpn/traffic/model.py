"""Operator-maintained service catalog, never browsing observations."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, String, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from prettylisavpn.database import Base


class TrafficServiceRecord(Base):
    __tablename__ = "traffic_services"
    __table_args__ = (
        CheckConstraint("category IN ('popular', 'whitelist')", name="ck_traffic_service_category"),
        CheckConstraint("popularity_rank BETWEEN 1 AND 1000", name="ck_traffic_service_rank"),
        CheckConstraint("jsonb_typeof(domains) = 'array'", name="ck_traffic_service_domains"),
        CheckConstraint("jsonb_typeof(ipv4_cidrs) = 'array'", name="ck_traffic_service_networks"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    icon: Mapped[str] = mapped_column(String(40))
    category: Mapped[str] = mapped_column(String(16), server_default="popular")
    popularity_rank: Mapped[int | None] = mapped_column(Integer)
    domains: Mapped[list[str]] = mapped_column(JSONB)
    ipv4_cidrs: Mapped[list[str]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
