"""Refresh-token lifecycle for authentication sessions."""

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from prettylisavpn.auth_sessions.domain import (
    AuthSession,
    InvalidAuthSessionError,
    IssuedAuthSession,
)
from prettylisavpn.auth_sessions.repository import AuthSessionRepository

REFRESH_TOKEN_BYTES = 48


class AuthSessionService:
    def __init__(self, repository: AuthSessionRepository, refresh_token_ttl: timedelta) -> None:
        if refresh_token_ttl <= timedelta(0):
            raise ValueError("refresh_token_ttl must be positive")
        self._repository = repository
        self._refresh_token_ttl = refresh_token_ttl

    async def issue(self, user_id: UUID, device_id: UUID) -> IssuedAuthSession:
        now = datetime.now(UTC)
        refresh_token = self._generate_refresh_token()
        auth_session = AuthSession(
            id=uuid4(),
            user_id=user_id,
            device_id=device_id,
            refresh_token_hash=self.hash_refresh_token(refresh_token),
            expires_at=now + self._refresh_token_ttl,
            revoked_at=None,
            created_at=now,
            updated_at=now,
        )
        persisted = await self._repository.add(auth_session)
        return IssuedAuthSession(session=persisted, refresh_token=refresh_token)

    async def rotate(self, session_id: UUID, refresh_token: str) -> IssuedAuthSession:
        auth_session = await self._repository.get_for_update(session_id)
        now = datetime.now(UTC)
        if (
            auth_session is None
            or not auth_session.is_active(now)
            or not hmac.compare_digest(
                auth_session.refresh_token_hash,
                self.hash_refresh_token(refresh_token),
            )
        ):
            raise InvalidAuthSessionError

        new_refresh_token = self._generate_refresh_token()
        rotated = AuthSession(
            id=auth_session.id,
            user_id=auth_session.user_id,
            device_id=auth_session.device_id,
            refresh_token_hash=self.hash_refresh_token(new_refresh_token),
            expires_at=now + self._refresh_token_ttl,
            revoked_at=None,
            created_at=auth_session.created_at,
            updated_at=now,
        )
        await self._repository.rotate(
            rotated.id,
            rotated.refresh_token_hash,
            rotated.expires_at,
            rotated.updated_at,
        )
        return IssuedAuthSession(session=rotated, refresh_token=new_refresh_token)

    async def revoke(self, session_id: UUID) -> bool:
        return await self._repository.revoke(session_id, datetime.now(UTC))

    async def revoke_device_sessions(self, device_id: UUID) -> int:
        return await self._repository.revoke_for_device(device_id, datetime.now(UTC))

    @staticmethod
    def hash_refresh_token(refresh_token: str) -> bytes:
        return hashlib.sha256(refresh_token.encode()).digest()

    @staticmethod
    def _generate_refresh_token() -> str:
        return secrets.token_urlsafe(REFRESH_TOKEN_BYTES)
