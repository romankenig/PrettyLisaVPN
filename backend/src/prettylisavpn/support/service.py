"""Account-scoped idempotency, quotas and ownership verification."""

import asyncio
import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from prettylisavpn.auth.session_service import AccessIdentity, AuthenticatedSessionHandler
from prettylisavpn.auth_sessions.model import AuthSessionRecord
from prettylisavpn.connections import Postgres
from prettylisavpn.support.domain import Receipt, Report, Status, SupportError
from prettylisavpn.support.images import TOTAL_BYTES, Screenshot
from prettylisavpn.support.model import SupportAttachmentRecord, SupportRequestRecord
from prettylisavpn.users.model import UserRecord
from prettylisavpn.vpn_sessions.model import VpnSessionRecord


def fingerprint(report: Report, files: list[tuple[bytes, str]]) -> bytes:
    digest = hashlib.sha256()
    digest.update(json.dumps(report.model_dump(mode="json"), sort_keys=True).encode())
    for data, media_type in files:
        digest.update(media_type.encode())
        digest.update(hashlib.sha256(data).digest())
    return digest.digest()


def receipt(record: SupportRequestRecord) -> Receipt:
    return Receipt(request_id=record.request_id, status=cast(Status, record.status))


class SupportService:
    def __init__(self, postgres: Postgres, auth: AuthenticatedSessionHandler) -> None:
        self.postgres = postgres
        self.auth = auth
        self.upload_slots = asyncio.Semaphore(2)

    async def get(self, identity: AccessIdentity, request_id: UUID) -> Receipt:
        try:
            async with self.postgres.session() as session:
                row = await session.get(SupportRequestRecord, (identity.user_id, request_id))
                if row is None:
                    raise SupportError("SUPPORT_NOT_FOUND", 404)
                return receipt(row)
        except SQLAlchemyError:
            raise SupportError("SUPPORT_UNAVAILABLE", 503) from None

    async def accept(
        self, identity: AccessIdentity, report: Report, digest: bytes, files: list[Screenshot]
    ) -> Receipt:
        if len(files) > 3 or sum(len(f.data) for f in files) > TOTAL_BYTES:
            raise SupportError("ATTACHMENT_REJECTED", 422)
        try:
            async with self.postgres.session() as session, session.begin():
                # Serializes quotas and concurrent submissions for one account, including retries.
                user = await session.scalar(
                    select(UserRecord.id).where(UserRecord.id == identity.user_id).with_for_update()
                )
                if user is None:
                    raise SupportError("AUTH_INVALID", 401)
                old = await session.get(SupportRequestRecord, (identity.user_id, report.request_id))
                if old is not None:
                    if old.fingerprint != digest:
                        raise SupportError("IDEMPOTENCY_CONFLICT", 409)
                    return receipt(old)
                now = datetime.now(UTC)
                for interval, limit in ((timedelta(hours=1), 5), (timedelta(days=1), 20)):
                    count = await session.scalar(
                        select(func.count())
                        .select_from(SupportRequestRecord)
                        .where(
                            SupportRequestRecord.user_id == identity.user_id,
                            SupportRequestRecord.created_at > now - interval,
                        )
                    )
                    if (count or 0) >= limit:
                        raise SupportError("RATE_LIMITED", 429)
                sanitized = report.model_copy(deep=True)
                diagnostics = sanitized.diagnostics
                if diagnostics is not None:
                    if diagnostics.auth_session_id is not None:
                        owned = await session.scalar(
                            select(AuthSessionRecord.id).where(
                                AuthSessionRecord.id == diagnostics.auth_session_id,
                                AuthSessionRecord.user_id == identity.user_id,
                            )
                        )
                        if owned is None:
                            diagnostics.auth_session_id = None
                    if diagnostics.vpn.session_id is not None:
                        owned = await session.scalar(
                            select(VpnSessionRecord.id).where(
                                VpnSessionRecord.id == diagnostics.vpn.session_id,
                                VpnSessionRecord.user_id == identity.user_id,
                            )
                        )
                        if owned is None:
                            diagnostics.vpn.session_id = None
                row = SupportRequestRecord(
                    user_id=identity.user_id,
                    request_id=report.request_id,
                    fingerprint=digest,
                    payload=sanitized.model_dump(mode="json"),
                    status="ACCEPTED",
                    attempts=0,
                    created_at=now,
                    next_attempt_at=now,
                )
                session.add(row)
                await session.flush()
                for position, file in enumerate(files):
                    session.add(
                        SupportAttachmentRecord(
                            user_id=identity.user_id,
                            request_id=report.request_id,
                            position=position,
                            data=file.data,
                            media_type=file.media_type,
                        )
                    )
                return receipt(row)
        except SQLAlchemyError:
            raise SupportError("SUPPORT_UNAVAILABLE", 503) from None
