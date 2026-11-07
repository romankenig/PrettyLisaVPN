"""Short-lived billing-only browser sessions; no VPN device or bearer token in URLs."""

import hashlib
import re
import secrets
from typing import Protocol
from uuid import UUID

from redis.asyncio import Redis

from prettylisavpn.auth.service import BlockedUserError, InvalidOtpError, OtpVerifier
from prettylisavpn.auth.session_service import InvalidSessionError
from prettylisavpn.connections import Postgres
from prettylisavpn.demo.domain import RegistrationRequiredError, is_demo_email
from prettylisavpn.subscriptions.repository import SubscriptionRepository
from prettylisavpn.users.domain import UserStatus, normalize_email
from prettylisavpn.users.model import UserRecord
from prettylisavpn.users.repository import UserRepository
from prettylisavpn.users.service import UserService

WEB_ORIGIN = "https://prettylisavpn.com"
COOKIE = "__Host-prettylisa-billing"
SESSION_TTL = 7200
HANDOFF_TTL = 60


class WebTokens(Protocol):
    async def issue(self, kind: str, user_id: UUID, ttl: int) -> str: ...
    async def resolve(self, kind: str, token: str, *, consume: bool = False) -> UUID: ...
    async def revoke(self, token: str) -> None: ...


def key(kind: str, token: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
        raise InvalidSessionError
    return "billing:web:" + kind + ":" + hashlib.sha256(token.encode()).hexdigest()


class RedisWebTokens:
    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    async def issue(self, kind: str, user_id: UUID, ttl: int) -> str:
        token = secrets.token_urlsafe(32)
        await self.redis.set(key(kind, token), str(user_id), ex=ttl)
        return token

    async def resolve(self, kind: str, token: str, *, consume: bool = False) -> UUID:
        cache_key = key(kind, token)
        value = await self.redis.getdel(cache_key) if consume else await self.redis.get(cache_key)
        if value is None:
            raise InvalidSessionError
        return UUID(value)

    async def revoke(self, token: str) -> None:
        await self.redis.delete(key("session", token))


class BillingWebSessions:
    def __init__(self, postgres: Postgres, otp: OtpVerifier, tokens: WebTokens) -> None:
        self.postgres, self.otp, self.tokens = postgres, otp, tokens

    async def _active(self, user_id: UUID) -> UUID:
        async with self.postgres.session() as session:
            user = await session.get(UserRecord, user_id)
            if user is None:
                raise InvalidSessionError
            if is_demo_email(user.email):
                raise RegistrationRequiredError
            if user.status == UserStatus.BLOCKED:
                raise BlockedUserError
        return user_id

    async def authenticate(self, token: str | None) -> UUID:
        if token is None:
            raise InvalidSessionError
        return await self._active(await self.tokens.resolve("session", token))

    async def email(self, user_id: UUID) -> str:
        async with self.postgres.session() as session:
            user = await session.get(UserRecord, user_id)
            if user is None or user.status == UserStatus.BLOCKED:
                raise InvalidSessionError
            return user.email

    async def login(self, email: str, code: str) -> str:
        email = normalize_email(email)
        if is_demo_email(email):
            raise InvalidOtpError
        if not await self.otp.verify(email, code):
            raise InvalidOtpError
        async with self.postgres.session() as session, session.begin():
            user, _, _ = await UserService(
                UserRepository(session), SubscriptionRepository(session)
            ).find_or_create_with_subscription(email)
            if is_demo_email(user.email):
                raise RegistrationRequiredError
            if user.status == UserStatus.BLOCKED:
                raise BlockedUserError
        return await self.tokens.issue("session", user.id, SESSION_TTL)

    async def handoff(self, user_id: UUID) -> str:
        await self._active(user_id)
        token = await self.tokens.issue("handoff", user_id, HANDOFF_TTL)
        # Fragment is removed before any navigation; it is never sent in an HTTP URL.
        return WEB_ORIGIN + "/account/#handoff=" + token

    async def exchange(self, token: str) -> str:
        user_id = await self.tokens.resolve("handoff", token, consume=True)
        await self._active(user_id)
        return await self.tokens.issue("session", user_id, SESSION_TTL)
