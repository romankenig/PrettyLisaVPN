"""Reinstallation reuses the same quota principal; it never refunds an active grant."""

from collections.abc import Awaitable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Protocol, cast
from uuid import uuid4

from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import func, select, update
from sqlalchemy.exc import SQLAlchemyError

from prettylisavpn.auth.service import BlockedUserError, LoginResult
from prettylisavpn.auth.tokens import AccessTokenService
from prettylisavpn.auth_sessions.model import AuthSessionRecord
from prettylisavpn.auth_sessions.repository import AuthSessionRepository
from prettylisavpn.auth_sessions.service import AuthSessionService
from prettylisavpn.client_vpn.model import ClientLeaseRecord
from prettylisavpn.config import Settings
from prettylisavpn.connections import Postgres
from prettylisavpn.demo.domain import (
    DEMO_EMAIL_DOMAIN,
    DemoRateLimitedError,
    DemoUnavailableError,
    identity_digest,
)
from prettylisavpn.demo.model import DemoDeviceRecord
from prettylisavpn.devices.domain import DevicePlatform
from prettylisavpn.devices.repository import DeviceRepository
from prettylisavpn.devices.service import DeviceService
from prettylisavpn.subscriptions.domain import Subscription, SubscriptionPlan
from prettylisavpn.subscriptions.repository import SubscriptionRepository
from prettylisavpn.users.domain import User, UserStatus
from prettylisavpn.users.repository import UserRepository


class AdmissionLimit(Protocol):
    async def admit(self, ip_digest: str, device_digest: str) -> None: ...


class RedisAdmissionLimit:
    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    async def admit(self, ip_digest: str, device_digest: str) -> None:
        # Atomic fixed windows; no raw IPs or device identifiers in cache keys.
        script = """
        for i,key in ipairs(KEYS) do
          local count = redis.call('INCR', key)
          if count == 1 then redis.call('EXPIRE', key, 3600) end
          if count > tonumber(ARGV[i]) then return 0 end
        end
        return 1
        """
        try:
            allowed = int(
                await cast(
                    Awaitable[str],
                    self.redis.eval(
                        script,
                        2,
                        "demo:ip:" + ip_digest,
                        "demo:device:" + device_digest,
                        "30",
                        "10",
                    ),
                )
            )
        except RedisError:
            raise DemoUnavailableError from None
        if not allowed:
            raise DemoRateLimitedError


class DemoService:
    def __init__(self, postgres: Postgres, settings: Settings, limiter: AdmissionLimit) -> None:
        self.postgres, self.settings, self.limiter = postgres, settings, limiter

    async def login(
        self,
        device_key: str,
        client_ip: str,
        platform: DevicePlatform = DevicePlatform.ANDROID,
    ) -> LoginResult:
        if platform not in (DevicePlatform.ANDROID, DevicePlatform.WINDOWS):
            raise DemoUnavailableError
        if not self.settings.demo_enabled or self.settings.demo_identity_secret is None:
            raise DemoUnavailableError
        secret = self.settings.demo_identity_secret.get_secret_value()
        # Keep existing Android identities/quotas; namespace the new platform.
        scoped_key = device_key if platform is DevicePlatform.ANDROID else "windows:" + device_key
        digest = identity_digest(secret, scoped_key)
        await self.limiter.admit(identity_digest(secret, "ip:" + client_ip).hex(), digest.hex())
        now = datetime.now(UTC)
        user: User | None
        subscription: Subscription | None
        try:
            async with self.postgres.session() as session, session.begin():
                await session.execute(
                    select(
                        func.pg_advisory_xact_lock(int.from_bytes(digest[:8], "big", signed=True))
                    )
                )
                principal = await session.get(DemoDeviceRecord, digest)
                users, subscriptions = UserRepository(session), SubscriptionRepository(session)
                if principal is None:
                    user_id = uuid4()
                    user = await users.add(
                        User(user_id, f"{user_id}@{DEMO_EMAIL_DOMAIN}", UserStatus.ACTIVE, now, now)
                    )
                    subscription = await subscriptions.add(
                        replace(Subscription.new_free(user.id, now), plan=SubscriptionPlan.DEMO)
                    )
                    principal = DemoDeviceRecord(
                        identity_digest=digest, user_id=user.id, installation_id=uuid4()
                    )
                    session.add(principal)
                    await session.flush()
                else:
                    user = await users.get_by_id(principal.user_id, for_update=True)
                    subscription = await subscriptions.get_by_user_id(principal.user_id)
                    if user is None or user.status is UserStatus.BLOCKED:
                        raise BlockedUserError
                    if subscription is None or subscription.plan is not SubscriptionPlan.DEMO:
                        raise DemoUnavailableError
                device = await DeviceService(DeviceRepository(session)).register(
                    user.id,
                    principal.installation_id,
                    platform,
                    "Android DEMO" if platform is DevicePlatform.ANDROID else "Windows DEMO",
                )
                # A fresh installation cannot safely resume an old private tunnel key.
                # Retain its reservation until the worker confirms removal.
                await session.execute(
                    update(ClientLeaseRecord)
                    .where(
                        ClientLeaseRecord.user_id == user.id,
                        ClientLeaseRecord.removed_at.is_(None),
                    )
                    .values(status="REVOKING", code="VPN_ACCESS_ENDED", next_attempt_at=now)
                )
                await session.execute(
                    update(AuthSessionRecord)
                    .where(
                        AuthSessionRecord.user_id == user.id,
                        AuthSessionRecord.revoked_at.is_(None),
                    )
                    .values(revoked_at=now, updated_at=now)
                )
                auth = await AuthSessionService(
                    AuthSessionRepository(session),
                    timedelta(seconds=self.settings.refresh_token_ttl_seconds),
                ).issue(user.id, device.id)
                access = AccessTokenService(self.settings).issue(
                    user.id, device.id, auth.session.id
                )
        except SQLAlchemyError:
            raise DemoUnavailableError from None
        return LoginResult(user, subscription, device, auth, access)
