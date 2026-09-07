"""User domain values and entity."""

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID


class UserStatus(StrEnum):
    ACTIVE = "ACTIVE"
    BLOCKED = "BLOCKED"


def normalize_email(email: str) -> str:
    """Return the canonical representation used for identity and uniqueness."""
    return email.strip().casefold()


@dataclass(frozen=True, slots=True)
class User:
    id: UUID
    email: str
    status: UserStatus
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "email", normalize_email(self.email))
        for field_name in ("created_at", "updated_at"):
            value = getattr(self, field_name)
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{field_name} must be timezone-aware")
            object.__setattr__(self, field_name, value.astimezone(UTC))
