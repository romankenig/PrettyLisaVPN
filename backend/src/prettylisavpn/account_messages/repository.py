"""PostgreSQL access; callers own transaction boundaries."""

from collections.abc import AsyncGenerator
from datetime import datetime
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from prettylisavpn.account_messages.domain import MessageContext, Publication
from prettylisavpn.account_messages.model import (
    MessageReceiptRecord,
    MessageRecord,
    MessageRevisionRecord,
)
from prettylisavpn.subscriptions.domain import SubscriptionPlan


class MessageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def lock_message(self, message_id: UUID, *, create: bool = False) -> MessageRecord | None:
        if create:
            await self.session.execute(
                insert(MessageRecord).values(id=message_id).on_conflict_do_nothing()
            )
        record: MessageRecord | None = await self.session.scalar(
            select(MessageRecord).where(MessageRecord.id == message_id).with_for_update()
        )
        return record

    async def revision(self, message_id: UUID, revision: int) -> MessageRevisionRecord | None:
        return await self.session.get(MessageRevisionRecord, (message_id, revision))

    async def receipt(
        self, user_id: UUID, message_id: UUID, revision: int
    ) -> MessageReceiptRecord | None:
        record: MessageReceiptRecord | None = await self.session.scalar(
            select(MessageReceiptRecord)
            .where(
                MessageReceiptRecord.user_id == user_id,
                MessageReceiptRecord.message_id == message_id,
                MessageReceiptRecord.revision == revision,
            )
            .with_for_update()
        )
        return record

    async def delivered(self, user_id: UUID, message_id: UUID, revision: int) -> None:
        await self.session.execute(
            insert(MessageReceiptRecord)
            .values(
                user_id=user_id,
                message_id=message_id,
                revision=revision,
            )
            .on_conflict_do_nothing()
        )

    async def candidates(
        self, user_id: UUID, context: MessageContext, plan: SubscriptionPlan, now: datetime
    ) -> AsyncGenerator[MessageRevisionRecord]:
        rev, receipt = MessageRevisionRecord, MessageReceiptRecord
        read = (
            select(receipt.message_id)
            .where(
                receipt.user_id == user_id,
                receipt.message_id == rev.message_id,
                receipt.revision >= rev.acknowledgement_floor,
                receipt.revision <= rev.revision,
                receipt.acknowledged_at.is_not(None),
            )
            .exists()
        )
        statement = (
            select(rev)
            .join(MessageRecord, MessageRecord.id == rev.message_id)
            .where(
                MessageRecord.active.is_(True),
                MessageRecord.current_revision == rev.revision,
                rev.schema_version == context.schema_version,
                or_(rev.starts_at.is_(None), rev.starts_at <= now),
                or_(rev.expires_at.is_(None), rev.expires_at > now),
                or_(rev.user_ids.is_(None), rev.user_ids.contains([str(user_id)])),
                or_(rev.plans.is_(None), rev.plans.contains([plan.value])),
                rev.platforms.op("?")(context.platform.value),
                ~read,
            )
            .order_by(rev.priority.desc(), rev.message_id)
        )
        stream = await self.session.stream_scalars(statement.execution_options(yield_per=100))
        try:
            async for record in stream:
                yield record
        finally:
            await stream.close()

    async def store_revision(self, payload: Publication, floor: int, publisher: str) -> None:
        self.session.add(
            MessageRevisionRecord(
                message_id=payload.id,
                revision=payload.revision,
                acknowledgement_floor=floor,
                schema_version=payload.schema_version,
                priority=payload.priority,
                starts_at=payload.starts_at,
                expires_at=payload.expires_at,
                user_ids=[str(value) for value in payload.user_ids] if payload.user_ids else None,
                plans=[value.value for value in payload.plans] if payload.plans else None,
                platforms={
                    key.value: value.model_dump() for key, value in payload.platforms.items()
                },
                payload=payload.model_dump(mode="json"),
                publisher=publisher,
            )
        )
        await self.session.flush()
