"""Account-wide delivery/ACK orchestration and trusted operator publishing."""

from contextlib import aclosing
from datetime import UTC, datetime
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from prettylisavpn.account_messages.domain import (
    MAX_RESPONSE_BYTES, MessageContext, MessagesResponse, Publication, PublicationReceipt, Receipt, encoded_size,
)
from prettylisavpn.account_messages.repository import MessageRepository
from prettylisavpn.account_messages.version import Version
from prettylisavpn.auth.session_service import AuthenticatedSessionHandler
from prettylisavpn.connections import Postgres
from prettylisavpn.devices.domain import DevicePlatform
from prettylisavpn.devices.repository import DeviceRepository
from prettylisavpn.subscriptions.domain import SubscriptionPlan
from prettylisavpn.subscriptions.repository import SubscriptionRepository


class MessageNotFoundError(LookupError):
    pass


class MessagesUnavailableError(RuntimeError):
    pass


class PublicationConflictError(ValueError):
    pass


class AccountMessagesService:
    def __init__(self, postgres: Postgres, auth: AuthenticatedSessionHandler) -> None:
        self.postgres, self.auth = postgres, auth

    async def list_messages(self, token: str, context: MessageContext) -> MessagesResponse:
        identity = await self.auth.authenticate(token)
        result = MessagesResponse(messages=[])
        if context.platform is DevicePlatform.WINDOWS:
            if Version.parse(context.app_version) < Version.parse("0.8.0"):
                return result
        now = datetime.now(UTC)
        try:
            async with self.postgres.session() as session, session.begin():
                device = await DeviceRepository(session).get(identity.device_id)
                if device is None or device.platform is not context.platform:
                    return result
                subscription = await SubscriptionRepository(session).get_by_user_id(identity.user_id)
                plan = (
                    subscription.plan if subscription and subscription.is_active(now)
                    else SubscriptionPlan.FREE
                )
                repository = MessageRepository(session)
                async with aclosing(repository.candidates(identity.user_id, context, plan, now)) as rows:
                    async for row in rows:
                        publication = Publication.model_validate(row.payload)
                        if not publication.platforms[context.platform].contains(context.app_version):
                            continue
                        message = publication.localized(context.locale)
                        candidate = MessagesResponse(messages=[*result.messages, message])
                        if encoded_size(candidate) > MAX_RESPONSE_BYTES:
                            break
                        result = candidate
                        if len(result.messages) == 10:
                            break
                for message in result.messages:
                    # Offering a revision authorizes its later ACK; this is NOT a read flag.
                    await repository.delivered(identity.user_id, message.id, message.revision)
        except (SQLAlchemyError, ValidationError):
            raise MessagesUnavailableError from None
        return result

    async def acknowledge(self, token: str, message_id: UUID, revision: int) -> Receipt:
        identity = await self.auth.authenticate(token)
        now = datetime.now(UTC)
        try:
            async with self.postgres.session() as session, session.begin():
                repository = MessageRepository(session)
                message = await repository.lock_message(message_id)
                offered = await repository.receipt(identity.user_id, message_id, revision)
                if offered is not None and offered.acknowledged_at is not None:
                    return Receipt(id=message_id, revision=revision)
                if message is None or not message.active or message.current_revision != revision:
                    raise MessageNotFoundError
                row = await repository.revision(message_id, revision)
                if offered is None or row is None:
                    raise MessageNotFoundError
                if (row.starts_at is not None and row.starts_at > now) or (
                    row.expires_at is not None and row.expires_at <= now
                ):
                    raise MessageNotFoundError
                if row.user_ids is not None and str(identity.user_id) not in row.user_ids:
                    raise MessageNotFoundError
                offered.acknowledged_at = now
        except SQLAlchemyError:
            raise MessagesUnavailableError from None
        return Receipt(id=message_id, revision=revision)


class MessagePublicationService:
    """Only called by the server-side CLI. There is no public write endpoint."""

    def __init__(self, postgres: Postgres) -> None:
        self.postgres = postgres

    async def publish(self, payload: Publication, publisher: str) -> PublicationReceipt:
        if not publisher.strip() or len(publisher) > 120:
            raise ValueError("Publisher identity is required")
        async with self.postgres.session() as session, session.begin():
            repository = MessageRepository(session)
            message = await repository.lock_message(payload.id, create=True)
            assert message is not None
            existing = await repository.revision(payload.id, payload.revision)
            if existing is not None:
                if existing.payload != payload.model_dump(mode="json"):
                    raise PublicationConflictError("Published revisions are immutable")
                # A retry must not reactivate a withdrawn message or replace a newer revision.
                return PublicationReceipt(id=payload.id, revision=payload.revision)
            if payload.revision != message.current_revision + 1:
                raise PublicationConflictError("Revision must advance by one")
            previous = await repository.revision(payload.id, message.current_revision)
            floor = (
                payload.revision if payload.redisplay_after_ack or previous is None
                else previous.acknowledgement_floor
            )
            await repository.store_revision(payload, floor, publisher)
            message.current_revision = payload.revision
            message.active = True
        return PublicationReceipt(id=payload.id, revision=payload.revision)

    async def withdraw(self, message_id: UUID) -> None:
        async with self.postgres.session() as session, session.begin():
            message = await MessageRepository(session).lock_message(message_id)
            if message is None:
                raise MessageNotFoundError
            message.active = False
