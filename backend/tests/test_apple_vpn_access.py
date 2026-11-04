"""Apple admission shares the existing account/device/auth-session fences."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from prettylisavpn.auth.session_service import AccessIdentity
from prettylisavpn.client_vpn.service import principals_valid
from prettylisavpn.devices.domain import DevicePlatform, DeviceStatus
from prettylisavpn.users.domain import UserStatus


@pytest.mark.parametrize("platform", list(DevicePlatform))
@pytest.mark.parametrize("invalid", [None, "device", "user", "auth", "expired", "scope"])
async def test_platform_access_preserves_every_existing_fence(platform, invalid):
    now = datetime.now(UTC)
    identity = AccessIdentity(uuid4(), uuid4(), uuid4())
    user = SimpleNamespace(status=UserStatus.ACTIVE)
    device = SimpleNamespace(
        status=DeviceStatus.ACTIVE, platform=platform, user_id=identity.user_id
    )
    auth = SimpleNamespace(
        user_id=identity.user_id,
        device_id=identity.device_id,
        revoked_at=None,
        expires_at=now + timedelta(days=1),
    )
    if invalid == "device":
        device.status = DeviceStatus.REVOKED
    elif invalid == "user":
        user.status = UserStatus.BLOCKED
    elif invalid == "auth":
        auth.revoked_at = now
    elif invalid == "expired":
        auth.expires_at = now
    elif invalid == "scope":
        auth.device_id = uuid4()
    session = SimpleNamespace(get=AsyncMock(side_effect=[user, device, auth]))
    allowed = platform in (
        DevicePlatform.ANDROID,
        DevicePlatform.WINDOWS,
        DevicePlatform.IOS,
        DevicePlatform.MACOS,
    )
    assert await principals_valid(session, identity, now) == (allowed and invalid is None)
