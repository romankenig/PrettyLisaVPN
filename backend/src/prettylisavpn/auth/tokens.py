"""Short-lived access-token issuance and validation."""

import hashlib
import hmac
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import jwt
from jwt import InvalidTokenError

from prettylisavpn.config import Settings

ACCESS_TOKEN_KEY_CONTEXT = b"prettylisavpn:access-token:v1"
ACCESS_TOKEN_ALGORITHM = "HS256"
ACCESS_TOKEN_AUDIENCE = "prettylisavpn-clients"
ACCESS_TOKEN_ISSUER = "prettylisavpn-backend"


@dataclass(frozen=True, slots=True)
class IssuedAccessToken:
    token: str = field(repr=False)
    expires_at: datetime
    expires_in_seconds: int


class InvalidAccessTokenError(Exception):
    """The supplied access token is invalid or expired."""


class AccessTokenService:
    def __init__(self, settings: Settings) -> None:
        root_secret = settings.otp_hmac_secret.get_secret_value().encode()
        self._signing_key = hmac.new(root_secret, ACCESS_TOKEN_KEY_CONTEXT, hashlib.sha256).digest()
        self._ttl = timedelta(seconds=settings.access_token_ttl_seconds)

    def issue(self, user_id: UUID, device_id: UUID, session_id: UUID) -> IssuedAccessToken:
        now = datetime.now(UTC)
        expires_at = now + self._ttl
        token = jwt.encode(
            {
                "sub": str(user_id),
                "device_id": str(device_id),
                "session_id": str(session_id),
                "type": "access",
                "iat": now,
                "exp": expires_at,
                "iss": ACCESS_TOKEN_ISSUER,
                "aud": ACCESS_TOKEN_AUDIENCE,
            },
            self._signing_key,
            algorithm=ACCESS_TOKEN_ALGORITHM,
        )
        return IssuedAccessToken(
            token=token,
            expires_at=expires_at,
            expires_in_seconds=int(self._ttl.total_seconds()),
        )

    def decode(self, token: str) -> dict[str, Any]:
        try:
            claims: dict[str, Any] = jwt.decode(
                token,
                self._signing_key,
                algorithms=[ACCESS_TOKEN_ALGORITHM],
                audience=ACCESS_TOKEN_AUDIENCE,
                issuer=ACCESS_TOKEN_ISSUER,
                options={"require": ["sub", "device_id", "session_id", "type", "iat", "exp"]},
            )
        except InvalidTokenError:
            raise InvalidAccessTokenError from None
        if claims.get("type") != "access":
            raise InvalidAccessTokenError
        return claims
