"""Refresh-token lifecycle for authentication sessions."""

import base64
import hashlib
import hmac
import secrets
from dataclasses import replace
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
    def __init__(
        self,
        repository: AuthSessionRepository,
        refresh_token_ttl: timedelta,
        *,
        rotation_secret: bytes | None = None,
    ) -> None:
        if refresh_token_ttl <= timedelta(0):
            raise ValueError("refresh_token_ttl must be positive")
        self._repository = repository
        self._refresh_token_ttl = refresh_token_ttl
        self._rotation_secret = rotation_secret

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
        auth_session = await self.validate_refresh_token(session_id, refresh_token)
        return await self.rotate_validated(auth_session)

    async def validate_refresh_token(
        self, session_id: UUID, refresh_token: str, rotation_id: UUID | None = None
    ) -> AuthSession:
        auth_session = await self._repository.get_for_update(session_id)
        now = datetime.now(UTC)
        if auth_session is None or not self.accepts_refresh(
            auth_session, refresh_token, now, rotation_id
        ):
            raise InvalidAuthSessionError
        return auth_session

    async def rotate_validated(
        self,
        auth_session: AuthSession,
        *,
        refresh_token: str | None = None,
        rotation_id: UUID | None = None,
    ) -> IssuedAuthSession:
        now = datetime.now(UTC)
        if rotation_id is not None:
            if refresh_token is None or not self.accepts_refresh(
                auth_session, refresh_token, now, rotation_id
            ):
                raise InvalidAuthSessionError
            new_refresh_token = self._rotation_token(auth_session.id, refresh_token, rotation_id)
            if not self.is_refresh_token_usable(auth_session, refresh_token, now):
                # Same operation after a lost response: retain the committed expiry
                # and successor. A new rotation or revocation invalidates this receipt.
                return IssuedAuthSession(session=auth_session, refresh_token=new_refresh_token)
        else:
            new_refresh_token = self._generate_refresh_token()
        rotated = replace(
            auth_session,
            refresh_token_hash=self.hash_refresh_token(new_refresh_token),
            expires_at=now + self._refresh_token_ttl,
            revoked_at=None,
            updated_at=now,
            previous_refresh_token_hash=auth_session.refresh_token_hash if rotation_id else None,
            refresh_rotation_id=rotation_id,
        )
        await self._repository.rotate(
            rotated.id,
            rotated.refresh_token_hash,
            rotated.expires_at,
            rotated.updated_at,
            previous_refresh_token_hash=rotated.previous_refresh_token_hash,
            refresh_rotation_id=rotated.refresh_rotation_id,
        )
        return IssuedAuthSession(session=rotated, refresh_token=new_refresh_token)

    def accepts_refresh(
        self,
        auth_session: AuthSession,
        refresh_token: str,
        at: datetime,
        rotation_id: UUID | None = None,
    ) -> bool:
        if self.is_refresh_token_usable(auth_session, refresh_token, at):
            return True
        if not (
            auth_session.is_active(at)
            and rotation_id is not None
            and self._rotation_secret
            and auth_session.refresh_rotation_id == rotation_id
            and auth_session.previous_refresh_token_hash is not None
        ):
            return False
        return hmac.compare_digest(
            auth_session.previous_refresh_token_hash, self.hash_refresh_token(refresh_token)
        ) and hmac.compare_digest(
            auth_session.refresh_token_hash,
            self.hash_refresh_token(
                self._rotation_token(auth_session.id, refresh_token, rotation_id)
            ),
        )

    def _rotation_token(self, session_id: UUID, token: str, rotation_id: UUID) -> str:
        if not self._rotation_secret:
            raise InvalidAuthSessionError
        payload = (
            b"PrettyLisaVPN/refresh-successor/v1\x00"
            + session_id.bytes
            + rotation_id.bytes
            + token.encode()
        )
        return (
            base64.urlsafe_b64encode(hmac.digest(self._rotation_secret, payload, "sha384"))
            .rstrip(b"=")
            .decode("ascii")
        )

    async def revoke(self, session_id: UUID) -> bool:
        return await self._repository.revoke(session_id, datetime.now(UTC))

    async def revoke_device_sessions(self, device_id: UUID) -> int:
        return await self._repository.revoke_for_device(device_id, datetime.now(UTC))

    @staticmethod
    def hash_refresh_token(refresh_token: str) -> bytes:
        return hashlib.sha256(refresh_token.encode()).digest()

    @classmethod
    def is_refresh_token_usable(
        cls, auth_session: AuthSession, refresh_token: str, at: datetime
    ) -> bool:
        return auth_session.is_active(at) and hmac.compare_digest(
            auth_session.refresh_token_hash,
            cls.hash_refresh_token(refresh_token),
        )

    @staticmethod
    def _generate_refresh_token() -> str:
        return secrets.token_urlsafe(REFRESH_TOKEN_BYTES)
