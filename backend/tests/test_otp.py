from datetime import UTC
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError
from redis.exceptions import ConnectionError

from prettylisavpn.config import Settings
from prettylisavpn.otp import (
    ISSUE_SCRIPT,
    VERIFY_SCRIPT,
    OtpService,
    OtpServiceUnavailableError,
)

OTP_SECRET = "unit-test-otp-hmac-secret-with-adequate-length"


def settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, otp_hmac_secret=OTP_SECRET, **overrides)


async def test_request_issues_six_digit_code_without_exposing_sensitive_values():
    client = AsyncMock()
    client.eval.return_value = 1
    service = OtpService(client, settings())

    issued = await service.request(" User@Example.COM ", "2001:db8::1")

    assert issued is not None
    assert len(issued.code) == 6
    assert issued.code.isdecimal()
    assert issued.expires_at.tzinfo is UTC
    remaining_seconds = (issued.expires_at - issued.expires_at.now(UTC)).total_seconds()
    assert 299 <= remaining_seconds <= 300
    assert issued.code not in repr(issued)

    call = client.eval.await_args.args
    assert call[0] == ISSUE_SCRIPT
    assert call[1] == 4
    assert "User@Example.COM" not in call
    assert "user@example.com" not in call
    assert "2001:db8::1" not in call
    assert issued.code not in call
    assert len(call[6]) == 64


async def test_request_returns_same_non_disclosing_result_for_any_rejection():
    client = AsyncMock()
    client.eval.return_value = 0
    service = OtpService(client, settings())

    assert await service.request("unknown@example.com", "192.0.2.1") is None


@pytest.mark.parametrize(("script_result", "expected"), [(0, False), (1, True)])
async def test_verify_translates_atomic_script_result(script_result, expected):
    client = AsyncMock()
    client.eval.return_value = script_result
    service = OtpService(client, settings())

    assert await service.verify("USER@example.com", "123456") is expected
    call = client.eval.await_args.args
    assert call[0] == VERIFY_SCRIPT
    assert call[1] == 1
    assert "USER@example.com" not in call
    assert "user@example.com" not in call
    assert "123456" not in call
    assert len(call[3]) == 64


def test_verifiers_are_scoped_to_email_and_code():
    service = OtpService(AsyncMock(), settings())

    first = service._otp_verifier("first@example.com", "123456")
    assert first != service._otp_verifier("second@example.com", "123456")
    assert first != service._otp_verifier("first@example.com", "654321")


async def test_discard_removes_only_normalized_email_challenge():
    client = AsyncMock()
    service = OtpService(client, settings())

    await service.discard(" User@Example.COM ")

    client.delete.assert_awaited_once()
    key = client.delete.await_args.args[0]
    assert key.startswith("otp:challenge:")
    assert "user@example.com" not in key


@pytest.mark.parametrize("operation", ["request", "verify", "discard"])
async def test_valkey_failures_are_mapped_without_private_details(operation):
    client = AsyncMock()
    client.eval.side_effect = ConnectionError("redis://private-host")
    client.delete.side_effect = ConnectionError("redis://private-host")
    service = OtpService(client, settings())

    with pytest.raises(OtpServiceUnavailableError) as captured:
        if operation == "request":
            await service.request("user@example.com", "192.0.2.1")
        elif operation == "verify":
            await service.verify("user@example.com", "123456")
        else:
            await service.discard("user@example.com")

    assert "private-host" not in str(captured.value)


def test_default_otp_ttl_is_five_minutes():
    assert Settings(_env_file=None).otp_ttl_seconds == 300


@pytest.mark.parametrize(
    "overrides",
    [
        {"otp_hmac_secret": "too-short"},
        {"otp_ttl_seconds": 0},
        {"otp_request_cooldown_seconds": -1},
        {"otp_email_request_limit": 0},
        {"otp_ip_request_limit": 0},
        {"otp_max_verification_attempts": 0},
        {
            "environment": "production",
            "otp_hmac_secret": "local-development-otp-hmac-secret-change-me",
        },
    ],
)
def test_invalid_otp_configuration(overrides):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **overrides)
