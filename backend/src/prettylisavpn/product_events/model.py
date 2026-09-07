"""SQLAlchemy mapping for product events."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Index, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from prettylisavpn.database import Base
from prettylisavpn.product_events.domain import ProductEventName


class ProductEventRecord(Base):
    __tablename__ = "product_events"
    __table_args__ = (
        CheckConstraint(
            "jsonb_typeof(properties) = 'object'",
            name="ck_product_events_properties_object",
        ),
        Index("ix_product_events_event_name_occurred_at", "event_name", "occurred_at"),
        Index("ix_product_events_user_id_occurred_at", "user_id", "occurred_at"),
        Index("ix_product_events_device_id_occurred_at", "device_id", "occurred_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    device_id: Mapped[UUID | None] = mapped_column(ForeignKey("devices.id", ondelete="SET NULL"))
    event_name: Mapped[ProductEventName] = mapped_column(
        Enum(
            ProductEventName,
            name="product_event_name",
            values_callable=lambda enum: [event.value for event in enum],
        )
    )
    properties: Mapped[dict[str, str]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
