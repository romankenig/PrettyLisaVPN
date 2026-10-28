"""New fleet state; historical legacy_vpn tables are intentionally not reactivated."""

from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from prettylisavpn.database import Base


def now_utc() -> datetime:
    return datetime.now(UTC)


class ParameterContext(Protocol):
    def get_current_parameters(self) -> dict[str, object]: ...


def default_group(context: ParameterContext) -> str:
    return "FREE" if context.get_current_parameters().get("is_available_for_free") else "PREMIUM"


class FleetNodeRecord(Base):
    __tablename__ = "fleet_nodes"
    __table_args__ = (
        CheckConstraint("capacity > 0", name="ck_fleet_node_capacity"),
        CheckConstraint("country_code ~ '^[A-Z]{2}$'", name="ck_fleet_node_country"),
        CheckConstraint(
            "\"group\" IN ('INTERMEDIATE','FREE','PREMIUM')", name="ck_fleet_node_group"
        ),
        CheckConstraint(
            "is_available_for_free = (\"group\" = 'FREE')", name="ck_fleet_node_group_access"
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    country_code: Mapped[str] = mapped_column(String(2))
    host: Mapped[str] = mapped_column(String(45), unique=True)
    credential_ref: Mapped[str] = mapped_column(String(40))
    expected_egress_ips: Mapped[list[str]] = mapped_column(JSONB)
    capacity: Mapped[int] = mapped_column(Integer)
    is_available_for_free: Mapped[bool] = mapped_column(Boolean, default=False)
    group: Mapped[str] = mapped_column(String(16), default=default_group)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    lock_owner: Mapped[UUID | None]
    lock_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FleetMethodRecord(Base):
    __tablename__ = "fleet_methods"
    node_id: Mapped[UUID] = mapped_column(ForeignKey("fleet_nodes.id"), primary_key=True)
    method: Mapped[str] = mapped_column(String(32), primary_key=True)
    configuration: Mapped[dict[str, object]] = mapped_column(JSONB)
    state: Mapped[str] = mapped_column(String(32), default="REGISTERED")
    public_key: Mapped[str | None] = mapped_column(String(44))
    configured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)


class FleetOperationRecord(Base):
    __tablename__ = "fleet_operations"
    __table_args__ = (
        UniqueConstraint("node_id", "kind", "request_key", name="uq_fleet_operation_request"),
        Index("ix_fleet_operations_due", "status", "next_attempt_at"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    node_id: Mapped[UUID] = mapped_column(ForeignKey("fleet_nodes.id"))
    method: Mapped[str] = mapped_column(String(32))
    kind: Mapped[str] = mapped_column(String(20))
    request_key: Mapped[str] = mapped_column(String(100))
    parameters: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="QUEUED")
    result: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    claim_token: Mapped[UUID | None]
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_id: Mapped[UUID | None] = mapped_column(ForeignKey("fleet_nodes.id"))
    attempts: Mapped[int] = mapped_column(Integer, default=0)


class FleetObservationRecord(Base):
    __tablename__ = "fleet_observations"
    __table_args__ = (
        Index("ix_fleet_observation_history", "node_id", "observed_at"),
        CheckConstraint("quality BETWEEN 0 AND 100", name="ck_fleet_observation_quality"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    operation_id: Mapped[UUID] = mapped_column(ForeignKey("fleet_operations.id"), unique=True)
    node_id: Mapped[UUID] = mapped_column(ForeignKey("fleet_nodes.id"))
    source_id: Mapped[UUID | None] = mapped_column(ForeignKey("fleet_nodes.id"))
    method: Mapped[str] = mapped_column(String(32))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    data: Mapped[dict[str, object]] = mapped_column(JSONB)
    # Snapshot of the score at observation time. Legacy observations remain null.
    quality: Mapped[int | None] = mapped_column(Integer, nullable=True)
