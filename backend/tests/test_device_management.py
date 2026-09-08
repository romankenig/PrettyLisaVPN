from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from prettylisavpn.auth.session_service import InvalidSessionError
from prettylisavpn.config import Settings
from prettylisavpn.devices.domain import Device, DevicePlatform, DeviceStatus
from prettylisavpn.devices.management import DeviceNotFoundError, ManagedDevice
from prettylisavpn.main import create_app


def dependency() -> AsyncMock:
    result = AsyncMock()
    result.ping.return_value = True
    return result


def api_client(service: AsyncMock) -> TestClient:
    return TestClient(
        create_app(
            Settings(
                _env_file=None,
                otp_hmac_secret="device-management-test-secret-at-least-32-characters",
            ),
            postgres=dependency(),
            valkey=dependency(),
            otp_service=AsyncMock(),
            product_events=AsyncMock(),
            authenticated_sessions=AsyncMock(),
            device_management=service,
        )
    )


def managed_device(*, current: bool, status: DeviceStatus = DeviceStatus.ACTIVE) -> ManagedDevice:
    now = datetime.now(UTC)
    return ManagedDevice(
        device=Device(
            id=uuid4(),
            user_id=uuid4(),
            installation_id=uuid4(),
            platform=DevicePlatform.ANDROID,
            device_name="Pixel",
            status=status,
            created_at=now,
            updated_at=now,
            revoked_at=now if status is DeviceStatus.REVOKED else None,
        ),
        is_current=current,
    )


def test_list_devices_returns_device_metadata_and_current_flag():
    service = AsyncMock()
    managed = managed_device(current=True)
    service.list_devices.return_value = [managed]

    with api_client(service) as client:
        response = client.get("/devices", headers={"Authorization": "Bearer access-token"})

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": str(managed.device.id),
            "installation_id": str(managed.device.installation_id),
            "device_name": "Pixel",
            "platform": "ANDROID",
            "status": "ACTIVE",
            "created_at": managed.device.created_at.isoformat().replace("+00:00", "Z"),
            "updated_at": managed.device.updated_at.isoformat().replace("+00:00", "Z"),
            "revoked_at": None,
            "is_current": True,
        }
    ]
    service.list_devices.assert_awaited_once_with("access-token")


def test_revoke_current_device_returns_explicit_current_flag():
    service = AsyncMock()
    managed = managed_device(current=True, status=DeviceStatus.REVOKED)
    service.revoke_device.return_value = managed

    with api_client(service) as client:
        response = client.delete(
            f"/devices/{managed.device.id}",
            headers={"Authorization": "Bearer access-token"},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "revoked"
    assert response.json()["device"]["is_current"] is True
    assert response.json()["device"]["status"] == "REVOKED"


def test_revoke_unknown_or_unowned_device_uses_same_not_found_error():
    service = AsyncMock()
    service.revoke_device.side_effect = DeviceNotFoundError

    with api_client(service) as client:
        response = client.delete(
            f"/devices/{uuid4()}", headers={"Authorization": "Bearer access-token"}
        )

    assert response.status_code == 404
    assert response.json() == {"error": {"code": "device_not_found"}}


@pytest.mark.parametrize("method,path", [("get", "/devices"), ("delete", f"/devices/{uuid4()}")])
def test_device_endpoints_require_authentication(method: str, path: str):
    service = AsyncMock()
    with api_client(service) as client:
        response = getattr(client, method)(path)
    assert response.status_code == 401
    assert response.json() == {"error": {"code": "authentication_required"}}


def test_device_endpoint_maps_invalid_session():
    service = AsyncMock()
    service.list_devices.side_effect = InvalidSessionError
    with api_client(service) as client:
        response = client.get("/devices", headers={"Authorization": "Bearer secret-token"})
    assert response.status_code == 401
    assert response.json() == {"error": {"code": "invalid_session"}}
    assert "secret-token" not in response.text
