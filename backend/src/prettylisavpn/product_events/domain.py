"""Product event domain values and property allowlists."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID


class ProductEventName(StrEnum):
    OTP_REQUESTED = "otp_requested"
    OTP_SENT = "otp_sent"
    OTP_VERIFIED = "otp_verified"
    LOGIN_SUCCEEDED = "login_succeeded"
    LOGIN_FAILED = "login_failed"
    DEVICE_REGISTERED = "device_registered"
    DEVICE_REVOKED = "device_revoked"
    TOKEN_REFRESHED = "token_refreshed"
    LOGOUT = "logout"


PROPERTY_ALLOWLIST: dict[ProductEventName, dict[str, frozenset[str]]] = {
    ProductEventName.LOGIN_FAILED: {
        "reason": frozenset(
            {"invalid_otp", "expired_otp", "rate_limited", "user_blocked", "device_limit"}
        )
    },
    ProductEventName.DEVICE_REGISTERED: {
        "platform": frozenset(
            {
                "WINDOWS",
                "MACOS",
                "LINUX",
                "ANDROID",
                "IOS",
                "ANDROID_TV",
                "CHROME_EXTENSION",
            }
        )
    },
    ProductEventName.LOGOUT: {"scope": frozenset({"session", "device", "all"})},
}


def allowlisted_properties(
    event_name: ProductEventName, properties: Mapping[str, object] | None
) -> dict[str, str]:
    if not properties:
        return {}
    allowed = PROPERTY_ALLOWLIST.get(event_name, {})
    result: dict[str, str] = {}
    for key, allowed_values in allowed.items():
        value = properties.get(key)
        if isinstance(value, str) and value in allowed_values:
            result[key] = value
    return result


@dataclass(frozen=True, slots=True)
class ProductEvent:
    id: UUID
    user_id: UUID | None
    device_id: UUID | None
    event_name: ProductEventName
    properties: dict[str, str]
    occurred_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "properties",
            allowlisted_properties(self.event_name, self.properties),
        )
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")
        object.__setattr__(self, "occurred_at", self.occurred_at.astimezone(UTC))
