"""Authenticated application activity; versions are reported, never inferred."""

import asyncio
import logging
from collections import Counter
from contextvars import ContextVar
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import case, func, select, text
from sqlalchemy.dialects.postgresql import insert
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Receive, Scope, Send

from prettylisavpn.account_messages.version import Version
from prettylisavpn.connections import Postgres
from prettylisavpn.devices.domain import DeviceStatus
from prettylisavpn.devices.model import DeviceRecord
from prettylisavpn.product_analytics.activity import is_test_account
from prettylisavpn.product_analytics.domain import day
from prettylisavpn.product_analytics.model import AnalyticsCollectionRecord, AppActivityRecord
from prettylisavpn.users.model import UserRecord

logger = logging.getLogger(__name__)
client_version: ContextVar[str | None] = ContextVar("client_app_version", default=None)


def normalized_version(value: str | None) -> str | None:
    if not value or len(value) > 100:
        return None
    try:
        Version.parse(value)
    except ValueError:
        return None
    # Build metadata is not a different product version; retain prerelease identity.
    return value.split("+", 1)[0]


class AppVersionContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        token = client_version.set(
            normalized_version(Headers(scope=scope).get("x-prettylisavpn-app-version"))
        )
        try:
            await self.app(scope, receive, send)
        finally:
            client_version.reset(token)


class AppActivitySink(Protocol):
    async def record(self, user_id: UUID, device_id: UUID, version: str | None) -> None: ...


async def record_app_activity(
    sink: AppActivitySink | None,
    user_id: UUID,
    device_id: UUID,
    version: str | None = None,
) -> None:
    if sink is None:
        return
    try:
        async with asyncio.timeout(0.5):
            await sink.record(
                user_id, device_id, normalized_version(version or client_version.get())
            )
    except Exception:
        logger.warning("app_activity_recording_failed")


def app_version_report(
    now: datetime, started_at: datetime | None, rows: list[AppActivityRecord]
) -> dict[str, Any]:
    dates = [day(now) - timedelta(days=offset) for offset in range(30, -1, -1)]
    points = []
    for on in dates:
        platforms: dict[str, Any] | None = None
        if started_at is not None and on >= day(started_at):
            platforms = {}
            active = [row for row in rows if row.day == on and row.observed_at <= now]
            for platform in sorted({row.platform for row in active}):
                devices = [row for row in active if row.platform == platform]
                users = {(row.user_id, row.app_version or "UNKNOWN") for row in devices}
                platforms[platform] = {
                    "users": dict(sorted(Counter(version for _, version in users).items())),
                    "devices": dict(
                        sorted(Counter(row.app_version or "UNKNOWN" for row in devices).items())
                    ),
                    "active_users": len({row.user_id for row in devices}),
                }
        points.append({"date": on.isoformat(), "partial": on == day(now), "platforms": platforms})
    return {
        "schema": 1,
        "timezone": "GMT+3",
        "generated_at": now.isoformat(),
        "collection_started_at": started_at.isoformat() if started_at else None,
        "from_date": dates[0].isoformat(),
        "through_date": dates[-1].isoformat(),
        "points": points,
    }


class AppVersionAnalytics:
    def __init__(self, postgres: Postgres) -> None:
        self.postgres = postgres

    async def record(
        self, user_id: UUID, device_id: UUID, version: str | None, *, now: datetime | None = None
    ) -> None:
        now = now or datetime.now(UTC)
        version = normalized_version(version)
        async with self.postgres.session() as session, session.begin():
            user = await session.get(UserRecord, user_id)
            device = await session.get(DeviceRecord, device_id)
            if (
                user is None
                or is_test_account(user.email)
                or device is None
                or device.user_id != user_id
                or device.status != DeviceStatus.ACTIVE
            ):
                return
            statement = insert(AppActivityRecord).values(
                user_id=user_id,
                device_id=device_id,
                day=day(now),
                platform=device.platform.value,
                observed_at=now,
                app_version=version,
                version_observed_at=now if version else None,
            )
            newer_version = statement.excluded.version_observed_at.is_not(None) & (
                AppActivityRecord.version_observed_at.is_(None)
                | (AppActivityRecord.version_observed_at <= statement.excluded.version_observed_at)
            )
            await session.execute(
                statement.on_conflict_do_update(
                    index_elements=[AppActivityRecord.device_id, AppActivityRecord.day],
                    set_={
                        "observed_at": func.greatest(
                            AppActivityRecord.observed_at, statement.excluded.observed_at
                        ),
                        "app_version": case(
                            (newer_version, statement.excluded.app_version),
                            else_=AppActivityRecord.app_version,
                        ),
                        "version_observed_at": case(
                            (newer_version, statement.excluded.version_observed_at),
                            else_=AppActivityRecord.version_observed_at,
                        ),
                    },
                )
            )

    async def latest(self, now: datetime | None = None) -> dict[str, Any]:
        now = now or datetime.now(UTC)
        async with self.postgres.session() as session, session.begin():
            await session.execute(
                text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            )
            collection = await session.get(AnalyticsCollectionRecord, 1)
            users = {
                user.id
                for user in await session.scalars(select(UserRecord))
                if not is_test_account(user.email)
            }
            rows = list(
                await session.scalars(
                    select(AppActivityRecord).where(
                        AppActivityRecord.day >= day(now) - timedelta(days=30),
                        AppActivityRecord.day <= day(now),
                        AppActivityRecord.user_id.in_(users),
                    )
                )
            )
            return app_version_report(
                now, collection.app_versions_started_at if collection else None, rows
            )
