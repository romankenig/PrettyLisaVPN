"""Replaceable SMTP adapter and a database-backed retry/purge worker."""

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from typing import Protocol
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import delete, select

from prettylisavpn.config import Settings
from prettylisavpn.connections import Postgres
from prettylisavpn.emailing.timeweb import AiosmtplibTransport, SmtpTransport
from prettylisavpn.support.model import SupportAttachmentRecord, SupportRequestRecord

logger = logging.getLogger(__name__)


class SupportWorkerPort(Protocol):
    async def run(self, stop: asyncio.Event) -> None: ...


class SupportMailPort(Protocol):
    async def send(
        self, request: SupportRequestRecord, files: list[SupportAttachmentRecord]
    ) -> None: ...


class SupportSmtpMailer:
    def __init__(self, transport: SmtpTransport) -> None:
        self.transport = transport

    @classmethod
    def from_settings(cls, settings: Settings) -> "SupportSmtpMailer | None":
        secret = settings.support_smtp_password
        if secret is None or not secret.get_secret_value():
            return None
        return cls(
            AiosmtplibTransport(
                host=settings.email_smtp_host,
                port=settings.email_smtp_port,
                tls_mode=settings.email_smtp_tls_mode,
                username="app-helper@prettylisavpn.com",
                password=secret.get_secret_value(),
                connection_timeout_seconds=settings.email_connection_timeout_seconds,
                send_timeout_seconds=settings.email_send_timeout_seconds,
            )
        )

    async def send(
        self, request: SupportRequestRecord, files: list[SupportAttachmentRecord]
    ) -> None:
        payload = request.payload
        if payload is None:
            raise ValueError("Support content expired")
        message = EmailMessage()
        message["From"] = "PrettyLisaVPN <app-helper@prettylisavpn.com>"
        message["To"] = "help@prettylisavpn.com"
        message["Reply-To"] = payload["reply_email"]
        message["Subject"] = f"[PrettyLisaVPN support {request.request_id}] {payload['subject']}"
        message_id = uuid5(NAMESPACE_URL, f"{request.user_id}:{request.request_id}")
        message["Message-ID"] = f"<support.{message_id}@prettylisavpn.com>"
        message["Date"] = request.created_at
        message.set_content(
            f"Request: {request.request_id}\n\n{payload['description']}\n\n"
            + "Technical data (user supplied, session IDs ownership checked):\n"
            + json.dumps(payload["diagnostics"], ensure_ascii=False, indent=2)
        )
        for file in files:
            message.add_attachment(
                file.data,
                maintype="image",
                subtype="png",
                filename=f"screenshot-{file.position + 1}.png",
            )
        await self.transport.send(
            message, sender="app-helper@prettylisavpn.com", recipient="help@prettylisavpn.com"
        )


class SupportWorker:
    def __init__(self, postgres: Postgres, mailer: SupportMailPort | None) -> None:
        self.postgres = postgres
        self.mailer = mailer

    async def deliver_one(self) -> bool:
        if self.mailer is None:
            return False
        async with self.postgres.session() as session, session.begin():
            row = await session.scalar(
                select(SupportRequestRecord)
                .where(
                    SupportRequestRecord.status.in_(["ACCEPTED", "RETRYING"]),
                    SupportRequestRecord.next_attempt_at <= datetime.now(UTC),
                    SupportRequestRecord.payload.is_not(None),
                    SupportRequestRecord.created_at > datetime.now(UTC) - timedelta(days=30),
                )
                .order_by(SupportRequestRecord.next_attempt_at)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if row is None:
                return False
            files = list(
                await session.scalars(
                    select(SupportAttachmentRecord)
                    .where(
                        SupportAttachmentRecord.user_id == row.user_id,
                        SupportAttachmentRecord.request_id == row.request_id,
                    )
                    .order_by(SupportAttachmentRecord.position)
                )
            )
            row.attempts += 1
            try:
                # The lock survives SMTP; another worker skips it. A crash after SMTP DATA
                # can resend the same Message-ID, but can never create a second ticket.
                async with asyncio.timeout(20):
                    await self.mailer.send(row, files)
            except Exception:
                logger.warning("support_delivery_failed")
                row.status = "FAILED" if row.attempts >= 8 else "RETRYING"
                row.next_attempt_at = datetime.now(UTC) + timedelta(
                    seconds=min(3600, 30 * 2 ** (row.attempts - 1))
                )
            else:
                row.status = "SENT"
                row.sent_at = datetime.now(UTC)
            return True

    async def purge(self) -> None:
        async with self.postgres.session() as session, session.begin():
            rows = await session.scalars(
                select(SupportRequestRecord)
                .where(
                    SupportRequestRecord.created_at < datetime.now(UTC) - timedelta(days=30),
                    SupportRequestRecord.payload.is_not(None),
                )
                .limit(100)
                .with_for_update(skip_locked=True)
            )
            for row in rows:
                await session.execute(
                    delete(SupportAttachmentRecord).where(
                        SupportAttachmentRecord.user_id == row.user_id,
                        SupportAttachmentRecord.request_id == row.request_id,
                    )
                )
                row.payload = None
                row.status = "EXPIRED"

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                await self.purge()
                delivered = await self.deliver_one()
            except Exception:
                logger.warning("support_worker_unavailable")
                delivered = False
            try:
                await asyncio.wait_for(stop.wait(), timeout=0.1 if delivered else 5)
            except TimeoutError:
                pass
