import asyncio
import os
from uuid import uuid4

import pytest

from prettylisavpn.config import Settings
from prettylisavpn.connections import Valkey

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1", reason="Set RUN_INTEGRATION_TESTS=1"
    ),
]


def settings(**overrides: object) -> Settings:
    defaults: dict[str, object] = {
        "otp_hmac_secret": f"integration-test-otp-secret-{uuid4().hex}",
        "otp_ttl_seconds": 2,
        "otp_request_cooldown_seconds": 0,
        "otp_email_request_limit": 20,
        "otp_email_rate_window_seconds": 2,
        "otp_ip_request_limit": 20,
        "otp_ip_rate_window_seconds": 2,
        "otp_max_verification_attempts": 3,
    }
    defaults.update(overrides)
    return Settings(**defaults)


async def test_otp_expires():
    valkey = Valkey(settings(otp_ttl_seconds=1))
    try:
        issued = await valkey.otp.request("expiry@example.com", "192.0.2.1")
        assert issued is not None
        await asyncio.sleep(1.1)
        assert not await valkey.otp.verify("expiry@example.com", issued.code)
    finally:
        await valkey.close()


async def test_invalid_codes_exhaust_maximum_attempts():
    valkey = Valkey(settings(otp_max_verification_attempts=2))
    try:
        issued = await valkey.otp.request("attempts@example.com", "192.0.2.2")
        assert issued is not None
        invalid = "000001" if issued.code == "000000" else "000000"
        assert not await valkey.otp.verify("attempts@example.com", invalid)
        assert not await valkey.otp.verify("attempts@example.com", invalid)
        assert not await valkey.otp.verify("attempts@example.com", issued.code)
    finally:
        await valkey.close()


async def test_successful_code_cannot_be_replayed():
    valkey = Valkey(settings())
    try:
        issued = await valkey.otp.request("replay@example.com", "192.0.2.3")
        assert issued is not None
        assert await valkey.otp.verify("replay@example.com", issued.code)
        assert not await valkey.otp.verify("replay@example.com", issued.code)
    finally:
        await valkey.close()


async def test_only_one_concurrent_verification_consumes_code():
    valkey = Valkey(settings())
    try:
        issued = await valkey.otp.request("concurrent@example.com", "192.0.2.4")
        assert issued is not None
        results = await asyncio.gather(
            *(valkey.otp.verify("concurrent@example.com", issued.code) for _ in range(8))
        )
        assert results.count(True) == 1
        assert results.count(False) == 7
    finally:
        await valkey.close()


async def test_request_cooldown_is_enforced():
    valkey = Valkey(settings(otp_request_cooldown_seconds=2))
    try:
        assert await valkey.otp.request("cooldown@example.com", "192.0.2.5") is not None
        assert await valkey.otp.request("cooldown@example.com", "192.0.2.5") is None
    finally:
        await valkey.close()


async def test_per_email_request_limit_is_enforced():
    valkey = Valkey(settings(otp_email_request_limit=2))
    try:
        email = "email-limit@example.com"
        assert await valkey.otp.request(email, "192.0.2.6") is not None
        assert await valkey.otp.request(email, "192.0.2.7") is not None
        assert await valkey.otp.request(email, "192.0.2.8") is None
    finally:
        await valkey.close()


async def test_per_ip_request_limit_is_enforced():
    valkey = Valkey(settings(otp_ip_request_limit=2))
    try:
        client_ip = "192.0.2.9"
        assert await valkey.otp.request("ip-limit-1@example.com", client_ip) is not None
        assert await valkey.otp.request("ip-limit-2@example.com", client_ip) is not None
        assert await valkey.otp.request("ip-limit-3@example.com", client_ip) is None
    finally:
        await valkey.close()
