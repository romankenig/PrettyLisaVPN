"""Authentication session domain values."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class AuthSession:
    id: UUID
    user_id: UUID
    device_id: UUID
    refresh_token_hash: bytes
    expires_at: datetime
    revoked_at: datetime | None
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        if len(self.refresh_token_hash) != 32:
            raise ValueError("refresh_token_hash must be a SHA-256 digest")
        for field_name in ("expires_at", "revoked_at", "created_at", "updated_at"):
            value = getattr(self, field_name)
            if value is None:
                continue
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{field_name} must be timezone-aware")
            object.__setattr__(self, field_name, value.astimezone(UTC))

    def is_active(self, at: datetime) -> bool:
        if at.tzinfo is None or at.utcoffset() is None:
            raise ValueError("at must be timezone-aware")
        return self.revoked_at is None and self.expires_at > at.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class IssuedAuthSession:
    session: AuthSession
    refresh_token: str = field(repr=False)


class InvalidAuthSessionError(Exception):
    """The session or supplied refresh token cannot be used."""
