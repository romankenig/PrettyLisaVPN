from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from prettylisavpn.auth.events import DatabaseProductEventSink
from prettylisavpn.auth.service import (
    OtpDeliveryUnavailableError,
    OtpRateLimitedError,
    OtpStorageUnavailableError,
    RequestOtpService,
)
from prettylisavpn.config import Settings
from prettylisavpn.emailing.domain import (
    EmailAuthenticationError,
    EmailDeliveryError,
    EmailProviderUnavailableError,
    EmailRecipientRejectedError,
)
from prettylisavpn.main import create_app
from prettylisavpn.otp import IssuedOtp, OtpServiceUnavailableError
from prettylisavpn.product_events.domain import ProductEventName


def settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)


def dependency() -> AsyncMock:
    result = AsyncMock()
    result.ping.return_value = True
    return result


class FailingPostgres:
    @asynccontextmanager
    async def session(self):
        raise RuntimeError("private-database-detail")
        yield


def issued_otp() -> IssuedOtp:
    return IssuedOtp(code="123456", expires_at=datetime.now(UTC) + timedelta(minutes=5))


async def test_request_service_normalizes_email_sends_code_and_records_safe_events():
    otp = AsyncMock()
    otp.request.return_value = issued_otp()
    email_provider = AsyncMock()
    events = AsyncMock()
    service = RequestOtpService(otp, email_provider, events)

    await service.request(" User@Example.COM ", "192.0.2.1")

    otp.request.assert_awaited_once_with("user@example.com", "192.0.2.1")
    email_provider.send.assert_awaited_once()
    outbound = email_provider.send.await_args.args[0]
    assert outbound.recipient == "user@example.com"
    assert "123456" in outbound.text_body
    assert [call.args[0] for call in events.record.await_args_list] == [
        ProductEventName.OTP_REQUESTED,
        ProductEventName.OTP_SENT,
    ]


async def test_request_service_exposes_rate_limit_without_sending():
    otp = AsyncMock()
    otp.request.return_value = None
    email_provider = AsyncMock()
    service = RequestOtpService(otp, email_provider, AsyncMock())

    with pytest.raises(OtpRateLimitedError):
        await service.request("user@example.com", "192.0.2.2")

    email_provider.send.assert_not_awaited()


async def test_request_service_discards_code_after_provider_failure_without_retry():
    otp = AsyncMock()
    otp.request.return_value = issued_otp()
    email_provider = AsyncMock()
    email_provider.send.side_effect = EmailProviderUnavailableError("unavailable")
    service = RequestOtpService(otp, email_provider, AsyncMock())

    with pytest.raises(OtpDeliveryUnavailableError):
        await service.request("user@example.com", "192.0.2.3")

    email_provider.send.assert_awaited_once()
    otp.discard.assert_awaited_once_with("user@example.com")


@pytest.mark.parametrize(
    ("provider_error", "safe_log"),
    [
        (EmailAuthenticationError("private-auth-detail"), "authentication"),
        (EmailRecipientRejectedError("private-recipient-detail"), "recipient_rejected"),
        (EmailProviderUnavailableError("private-network-detail"), "unavailable"),
        (EmailDeliveryError("private-delivery-detail"), "delivery"),
    ],
)
async def test_request_service_logs_only_safe_provider_failure_category(
    provider_error, safe_log, caplog
):
    otp = AsyncMock()
    otp.request.return_value = issued_otp()
    email_provider = AsyncMock()
    email_provider.send.side_effect = provider_error
    service = RequestOtpService(otp, email_provider, AsyncMock())

    with pytest.raises(OtpDeliveryUnavailableError):
        await service.request("user@example.com", "192.0.2.3")

    assert f"otp_email_delivery_failed_{safe_log}" in caplog.text
    assert "private-" not in caplog.text
    assert "user@example.com" not in caplog.text
    assert "123456" not in caplog.text


async def test_discard_failure_does_not_replace_provider_failure():
    otp = AsyncMock()
    otp.request.return_value = issued_otp()
    otp.discard.side_effect = OtpServiceUnavailableError("private-valkey-detail")
    email_provider = AsyncMock()
    email_provider.send.side_effect = EmailProviderUnavailableError("private-smtp-detail")
    service = RequestOtpService(otp, email_provider, AsyncMock())

    with pytest.raises(OtpDeliveryUnavailableError) as captured:
        await service.request("user@example.com", "192.0.2.3")

    assert "private" not in str(captured.value)


async def test_request_service_maps_otp_storage_failure():
    otp = AsyncMock()
    otp.request.side_effect = OtpServiceUnavailableError("private-valkey-detail")
    service = RequestOtpService(otp, AsyncMock(), AsyncMock())

    with pytest.raises(OtpStorageUnavailableError) as captured:
        await service.request("user@example.com", "192.0.2.4")

    assert "private-valkey-detail" not in str(captured.value)


async def test_request_service_fails_before_generating_code_without_email_provider():
    otp = AsyncMock()
    service = RequestOtpService(otp, None, AsyncMock())

    with pytest.raises(OtpDeliveryUnavailableError):
        await service.request("user@example.com", "192.0.2.5")

    otp.request.assert_not_awaited()


async def test_product_event_storage_failure_does_not_break_flow_or_log_details(caplog):
    sink = DatabaseProductEventSink(FailingPostgres())

    await sink.record(ProductEventName.OTP_REQUESTED)

    assert "product_event_recording_failed" in caplog.text
    assert "private-database-detail" not in caplog.text


def api_client(*, otp: AsyncMock, email_provider: AsyncMock | None = None):
    postgres = dependency()
    valkey = dependency()
    events = AsyncMock()
    app = create_app(
        settings(),
        postgres=postgres,
        valkey=valkey,
        otp_service=otp,
        email_provider=email_provider if email_provider is not None else AsyncMock(),
        product_events=events,
    )
    return TestClient(app), events


@pytest.mark.parametrize(
    "email",
    [
        "User@Example.COM",
        "user@example.ru",
        "user@example.org",
        "user@subdomain.example.net",
    ],
)
def test_request_otp_accepts_valid_domains_with_generic_response(email):
    otp = AsyncMock()
    otp.request.return_value = issued_otp()
    client, _ = api_client(otp=otp)

    with client:
        response = client.post("/auth/request-otp", json={"email": email})

    assert response.status_code == 202
    assert response.json() == {"status": "accepted"}
    assert "123456" not in response.text


@pytest.mark.parametrize("email", ["not-an-email", "user@", "user@example", "@example.com"])
def test_request_otp_rejects_invalid_email(email):
    otp = AsyncMock()
    client, _ = api_client(otp=otp)

    with client:
        response = client.post("/auth/request-otp", json={"email": email})

    assert response.status_code == 422
    assert response.json() == {"error": {"code": "validation_error"}}
    otp.request.assert_not_awaited()


@pytest.mark.parametrize(
    ("service_error", "status_code", "error_code"),
    [
        (None, 429, "otp_rate_limited"),
        (OtpServiceUnavailableError("secret"), 503, "otp_service_unavailable"),
    ],
)
def test_request_otp_returns_stable_otp_error_codes(service_error, status_code, error_code):
    otp = AsyncMock()
    if service_error is None:
        otp.request.return_value = None
    else:
        otp.request.side_effect = service_error
    client, _ = api_client(otp=otp)

    with client:
        response = client.post("/auth/request-otp", json={"email": "user@example.com"})

    assert response.status_code == status_code
    assert response.json() == {"error": {"code": error_code}}
    assert "secret" not in response.text


def test_request_otp_maps_provider_failure_and_never_exposes_code(caplog):
    otp = AsyncMock()
    otp.request.return_value = issued_otp()
    email_provider = AsyncMock()
    email_provider.send.side_effect = EmailProviderUnavailableError("smtp-private-detail")
    client, events = api_client(otp=otp, email_provider=email_provider)

    with client:
        response = client.post("/auth/request-otp", json={"email": "user@example.com"})

    assert response.status_code == 503
    assert response.json() == {"error": {"code": "email_service_unavailable"}}
    assert "123456" not in response.text + caplog.text
    assert "smtp-private-detail" not in response.text + caplog.text
    otp.discard.assert_awaited_once()
    assert [call.args[0] for call in events.record.await_args_list] == [
        ProductEventName.OTP_REQUESTED
    ]


def test_request_otp_returns_stable_error_when_email_is_not_configured():
    otp = AsyncMock()
    postgres = dependency()
    valkey = dependency()
    app = create_app(
        settings(email_smtp_password=None),
        postgres=postgres,
        valkey=valkey,
        otp_service=otp,
        product_events=AsyncMock(),
    )

    with TestClient(app) as client:
        response = client.post("/auth/request-otp", json={"email": "user@example.com"})

    assert response.status_code == 503
    assert response.json() == {"error": {"code": "email_service_unavailable"}}
    otp.request.assert_not_awaited()
