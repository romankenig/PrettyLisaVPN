"""Provider-independent OTP issuance and verification backed by Valkey."""

import hashlib
import hmac
import secrets
from collections.abc import Awaitable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from ipaddress import ip_address
from typing import cast

from redis.asyncio import Redis

from prettylisavpn.config import Settings
from prettylisavpn.users.domain import normalize_email

ISSUE_SCRIPT = """
local cooldown_seconds = tonumber(ARGV[3])
if cooldown_seconds > 0 and redis.call('EXISTS', KEYS[2]) == 1 then
    return 0
end

local email_count = tonumber(redis.call('GET', KEYS[3]) or '0')
local ip_count = tonumber(redis.call('GET', KEYS[4]) or '0')
if email_count >= tonumber(ARGV[4]) or ip_count >= tonumber(ARGV[6]) then
    return 0
end

email_count = redis.call('INCR', KEYS[3])
if email_count == 1 then
    redis.call('EXPIRE', KEYS[3], tonumber(ARGV[5]))
end
ip_count = redis.call('INCR', KEYS[4])
if ip_count == 1 then
    redis.call('EXPIRE', KEYS[4], tonumber(ARGV[7]))
end

redis.call('HSET', KEYS[1], 'verifier', ARGV[1], 'attempts', 0)
redis.call('EXPIRE', KEYS[1], tonumber(ARGV[2]))
if cooldown_seconds > 0 then
    redis.call('SET', KEYS[2], '1', 'EX', cooldown_seconds)
end
return 1
"""

VERIFY_SCRIPT = """
if redis.call('EXISTS', KEYS[1]) == 0 then
    return 0
end

local stored_verifier = redis.call('HGET', KEYS[1], 'verifier')
if stored_verifier == ARGV[1] then
    redis.call('DEL', KEYS[1])
    return 1
end

local attempts = redis.call('HINCRBY', KEYS[1], 'attempts', 1)
if attempts >= tonumber(ARGV[2]) then
    redis.call('DEL', KEYS[1])
end
return 0
"""


@dataclass(frozen=True, slots=True)
class IssuedOtp:
    code: str = field(repr=False)
    expires_at: datetime


class OtpService:
    def __init__(self, client: Redis, settings: Settings) -> None:
        self._client = client
        self._secret = settings.otp_hmac_secret.get_secret_value().encode()
        self._ttl_seconds = settings.otp_ttl_seconds
        self._cooldown_seconds = settings.otp_request_cooldown_seconds
        self._email_request_limit = settings.otp_email_request_limit
        self._email_rate_window_seconds = settings.otp_email_rate_window_seconds
        self._ip_request_limit = settings.otp_ip_request_limit
        self._ip_rate_window_seconds = settings.otp_ip_rate_window_seconds
        self._max_verification_attempts = settings.otp_max_verification_attempts

    async def request(self, email: str, client_ip: str) -> IssuedOtp | None:
        normalized_email = normalize_email(email)
        normalized_ip = str(ip_address(client_ip.strip()))
        code = f"{secrets.randbelow(1_000_000):06d}"
        email_digest = self._identifier_digest("email", normalized_email)
        ip_digest = self._identifier_digest("ip", normalized_ip)
        accepted = int(
            await cast(
                Awaitable[str],
                self._client.eval(
                    ISSUE_SCRIPT,
                    4,
                    f"otp:challenge:{email_digest}",
                    f"otp:cooldown:{email_digest}",
                    f"otp:rate:email:{email_digest}",
                    f"otp:rate:ip:{ip_digest}",
                    self._otp_verifier(normalized_email, code),
                    str(self._ttl_seconds),
                    str(self._cooldown_seconds),
                    str(self._email_request_limit),
                    str(self._email_rate_window_seconds),
                    str(self._ip_request_limit),
                    str(self._ip_rate_window_seconds),
                ),
            ),
        )
        if accepted != 1:
            return None
        return IssuedOtp(
            code=code,
            expires_at=datetime.now(UTC) + timedelta(seconds=self._ttl_seconds),
        )

    async def verify(self, email: str, code: str) -> bool:
        normalized_email = normalize_email(email)
        email_digest = self._identifier_digest("email", normalized_email)
        verified = int(
            await cast(
                Awaitable[str],
                self._client.eval(
                    VERIFY_SCRIPT,
                    1,
                    f"otp:challenge:{email_digest}",
                    self._otp_verifier(normalized_email, code),
                    str(self._max_verification_attempts),
                ),
            ),
        )
        return verified == 1

    def _identifier_digest(self, kind: str, value: str) -> str:
        return hmac.new(
            self._secret,
            f"identifier:{kind}\0{value}".encode(),
            hashlib.sha256,
        ).hexdigest()

    def _otp_verifier(self, normalized_email: str, code: str) -> str:
        return hmac.new(
            self._secret,
            f"otp\0{normalized_email}\0{code}".encode(),
            hashlib.sha256,
        ).hexdigest()
