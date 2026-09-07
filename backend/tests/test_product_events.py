from unittest.mock import AsyncMock
from uuid import uuid4

from prettylisavpn.product_events.domain import ProductEventName
from prettylisavpn.product_events.repository import ProductEventRepository
from prettylisavpn.product_events.service import ProductEventService


def test_supported_event_names():
    assert {event.value for event in ProductEventName} == {
        "otp_requested",
        "otp_sent",
        "otp_verified",
        "login_succeeded",
        "login_failed",
        "device_registered",
        "device_revoked",
        "token_refreshed",
        "logout",
    }


async def test_record_keeps_only_allowlisted_minimal_properties():
    repository = AsyncMock(spec=ProductEventRepository)
    repository.add.side_effect = lambda event: event

    recorded = await ProductEventService(repository).record(
        ProductEventName.DEVICE_REGISTERED,
        user_id=uuid4(),
        device_id=uuid4(),
        properties={
            "platform": "ANDROID",
            "otp_code": "123456",
            "access_token": "secret-access-token",
            "refresh_token": "secret-refresh-token",
            "password": "secret-password",
            "vpn_private_key": "secret-private-key",
            "visited_url": "https://private.example",
            "dns_query": "private.example",
            "packet_contents": "secret-packet",
            "serial_number": "secret-serial",
        },
    )

    assert recorded is not None
    assert recorded.properties == {"platform": "ANDROID"}
    repository.add.assert_awaited_once_with(recorded)


async def test_record_drops_unrecognized_allowlisted_values():
    repository = AsyncMock(spec=ProductEventRepository)
    repository.add.side_effect = lambda event: event

    recorded = await ProductEventService(repository).record(
        ProductEventName.LOGIN_FAILED,
        properties={"reason": "token=secret-value", "email": "private@example.com"},
    )

    assert recorded is not None
    assert recorded.properties == {}


async def test_analytics_failure_is_safe_and_does_not_log_exception(caplog):
    repository = AsyncMock(spec=ProductEventRepository)
    repository.add.side_effect = RuntimeError("secret-refresh-token https://private.example")

    recorded = await ProductEventService(repository).record(ProductEventName.LOGIN_SUCCEEDED)

    assert recorded is None
    assert "product_event_recording_failed" in caplog.text
    assert "secret-refresh-token" not in caplog.text
    assert "private.example" not in caplog.text
