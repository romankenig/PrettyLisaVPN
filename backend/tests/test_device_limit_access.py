from dataclasses import replace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from test_device_management import api_client, managed_device
from test_devices import device

from prettylisavpn.auth.session_service import InvalidSessionError, RevokedDeviceError
from prettylisavpn.devices.domain import DeviceLimitReachedError, DevicePlatform, DeviceStatus
from prettylisavpn.devices.repository import DeviceRepository
from prettylisavpn.devices.service import DeviceService


@pytest.mark.parametrize("platform", list(DevicePlatform))
async def test_opted_in_login_at_limit_creates_pending_device_without_active_slot(platform):
    repository = AsyncMock(spec=DeviceRepository)
    repository.lock_user.return_value = True
    repository.get_by_installation_for_update.return_value = None
    repository.count_active.return_value = 5
    repository.add.side_effect = lambda value: value
    pending, registered = await DeviceService(repository).register_with_result(
        uuid4(), uuid4(), platform, "New device", allow_device_management=True
    )
    assert pending.status is DeviceStatus.PENDING
    assert not pending.is_active() and pending.revoked_at is None and not registered


async def test_repeated_pending_installation_reuses_row_and_preserves_otp_timestamp():
    repository = AsyncMock(spec=DeviceRepository)
    existing = replace(device(status=DeviceStatus.PENDING), last_login_at=device().created_at)
    repository.lock_user.return_value = True
    repository.get_by_installation_for_update.return_value = existing
    repository.count_active.return_value = 5
    repository.update.side_effect = lambda value: value
    pending, registered = await DeviceService(repository).register_with_result(
        existing.user_id,
        existing.installation_id,
        existing.platform,
        "Renamed",
        allow_device_management=True,
    )
    assert pending.id == existing.id and pending.last_login_at == existing.last_login_at
    assert pending.status is DeviceStatus.PENDING and not registered
    repository.add.assert_not_awaited()


async def test_pending_device_can_be_explicitly_revoked():
    repository = AsyncMock(spec=DeviceRepository)
    repository.get_for_update.return_value = device(status=DeviceStatus.PENDING)
    repository.update.side_effect = lambda value: value
    assert await DeviceService(repository).revoke(uuid4())
    assert repository.update.await_args.args[0].status is DeviceStatus.REVOKED


def test_activation_endpoint_returns_current_device():
    service = AsyncMock()
    service.activate_current.return_value = managed_device(current=True)
    with api_client(service) as client:
        result = client.post("/devices/activate", headers={"Authorization": "Bearer token"})
    assert result.status_code == 200
    assert result.json()["is_current"] and result.json()["status"] == "ACTIVE"
    service.activate_current.assert_awaited_once_with("token")


@pytest.mark.parametrize(
    "error,status,code",
    [
        (DeviceLimitReachedError(), 409, "device_limit_reached"),
        (InvalidSessionError(), 401, "invalid_session"),
        (RevokedDeviceError(), 403, "device_revoked"),
    ],
)
def test_activation_endpoint_maps_failures(error, status, code):
    service = AsyncMock()
    service.activate_current.side_effect = error
    with api_client(service) as client:
        result = client.post("/devices/activate", headers={"Authorization": "Bearer token"})
    assert result.status_code == status
    assert result.json() == {"error": {"code": code}}


def test_activation_requires_authentication():
    service = AsyncMock()
    with api_client(service) as client:
        assert client.post("/devices/activate").status_code == 401
    service.activate_current.assert_not_awaited()
