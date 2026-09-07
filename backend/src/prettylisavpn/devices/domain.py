"""Device domain values and entity."""

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID


class DevicePlatform(StrEnum):
    WINDOWS = "WINDOWS"
    MACOS = "MACOS"
    LINUX = "LINUX"
    ANDROID = "ANDROID"
    IOS = "IOS"
    ANDROID_TV = "ANDROID_TV"
    CHROME_EXTENSION = "CHROME_EXTENSION"


class DeviceStatus(StrEnum):
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"


def normalize_device_name(device_name: str) -> str:
    normalized = device_name.strip()
    if not normalized:
        raise ValueError("device_name must not be empty")
    if len(normalized) > 255:
        raise ValueError("device_name must not exceed 255 characters")
    return normalized


@dataclass(frozen=True, slots=True)
class Device:
    id: UUID
    user_id: UUID
    installation_id: UUID
    platform: DevicePlatform
    device_name: str
    status: DeviceStatus
    created_at: datetime
    updated_at: datetime
    revoked_at: datetime | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "device_name", normalize_device_name(self.device_name))
        for field_name in ("created_at", "updated_at", "revoked_at"):
            value = getattr(self, field_name)
            if value is None:
                continue
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{field_name} must be timezone-aware")
            object.__setattr__(self, field_name, value.astimezone(UTC))
        if (self.status is DeviceStatus.ACTIVE) != (self.revoked_at is None):
            raise ValueError("status and revoked_at are inconsistent")

    def is_active(self) -> bool:
        return self.status is DeviceStatus.ACTIVE


class DeviceLimitReachedError(Exception):
    """The account already has the maximum number of active devices."""


class DeviceUserNotFoundError(Exception):
    """The user that would own the device does not exist."""
