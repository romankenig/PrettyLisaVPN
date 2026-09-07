"""Subscription domain values and entity."""

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4


class SubscriptionPlan(StrEnum):
    FREE = "FREE"
    PREMIUM = "PREMIUM"


class SubscriptionStatus(StrEnum):
    ACTIVE = "ACTIVE"
    CANCELED = "CANCELED"
    EXPIRED = "EXPIRED"


@dataclass(frozen=True, slots=True)
class Subscription:
    id: UUID
    user_id: UUID
    plan: SubscriptionPlan
    status: SubscriptionStatus
    current_period_start: datetime
    current_period_end: datetime | None
    auto_renew: bool
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        for field_name in (
            "current_period_start",
            "current_period_end",
            "created_at",
            "updated_at",
        ):
            value = getattr(self, field_name)
            if value is None:
                continue
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{field_name} must be timezone-aware")
            object.__setattr__(self, field_name, value.astimezone(UTC))
        if (
            self.current_period_end is not None
            and self.current_period_end <= self.current_period_start
        ):
            raise ValueError("current_period_end must be after current_period_start")
        if self.plan is SubscriptionPlan.FREE and self.auto_renew:
            raise ValueError("FREE subscriptions cannot auto-renew")

    @classmethod
    def new_free(cls, user_id: UUID, now: datetime) -> "Subscription":
        return cls(
            id=uuid4(),
            user_id=user_id,
            plan=SubscriptionPlan.FREE,
            status=SubscriptionStatus.ACTIVE,
            current_period_start=now,
            current_period_end=None,
            auto_renew=False,
            created_at=now,
            updated_at=now,
        )

    def is_active(self, at: datetime) -> bool:
        if at.tzinfo is None or at.utcoffset() is None:
            raise ValueError("at must be timezone-aware")
        normalized_at = at.astimezone(UTC)
        return self.status is SubscriptionStatus.ACTIVE and (
            self.current_period_end is None or self.current_period_end > normalized_at
        )
