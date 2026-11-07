"""Bounded eight-day traffic history and a durable per-node counter baseline."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from prettylisavpn.database import Base


class TrafficCursorRecord(Base):
    __tablename__ = "fleet_traffic_cursors"
    node_id: Mapped[UUID] = mapped_column(
        ForeignKey("fleet_nodes.id", ondelete="CASCADE"), primary_key=True
    )
    data: Mapped[dict[str, Any]] = mapped_column(JSONB)


class TrafficIntervalRecord(Base):
    __tablename__ = "fleet_traffic_intervals"
    __table_args__ = (Index("ix_fleet_traffic_time", "end_at"),)
    node_id: Mapped[UUID] = mapped_column(
        ForeignKey("fleet_nodes.id", ondelete="CASCADE"), primary_key=True
    )
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    complete: Mapped[bool] = mapped_column(Boolean)
    data: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
