"""Trusted operator CLI: publish prices, never grant access or start payments."""

import argparse
import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError

from prettylisavpn.billing.domain import Catalog
from prettylisavpn.billing.model import BillingCatalogRecord, ClientGroupRecord
from prettylisavpn.config import Settings
from prettylisavpn.connections import Postgres


class CatalogConflictError(RuntimeError):
    pass


async def publish_catalog(postgres: Postgres, catalog: Catalog, expected_revision: UUID | None = None) -> UUID:
    document = catalog.model_dump(mode="json")
    async with postgres.session() as session, session.begin():
        await session.execute(text("SELECT pg_advisory_xact_lock(903115991)"))
        group_ids = {entry.group_id for entry in catalog.entries}
        known_groups = set(await session.scalars(select(ClientGroupRecord.id).where(ClientGroupRecord.id.in_(group_ids))))
        if known_groups != group_ids:
            raise ValueError("Unknown client group")
        row = await session.scalar(select(BillingCatalogRecord).where(BillingCatalogRecord.id == 1).with_for_update())
        if expected_revision is not None and (row is None or row.revision != expected_revision):
            raise CatalogConflictError
        if row is not None and row.document == document:
            return row.revision
        revision = uuid4()
        if row is None:
            session.add(BillingCatalogRecord(id=1, revision=revision, document=document, updated_at=datetime.now(UTC)))
        else:
            row.revision = revision
            row.document = document
            row.updated_at = datetime.now(UTC)
        return revision


async def publish_file(path: Path, expected_revision: UUID | None) -> UUID:
    if path.stat().st_size > 65536:
        raise ValueError("Catalogue exceeds 64 KiB")
    catalog = Catalog.model_validate_json(path.read_bytes())
    postgres = Postgres(Settings())
    try:
        return await publish_catalog(postgres, catalog, expected_revision)
    finally:
        await postgres.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish the server monthly catalogue; no payments")
    parser.add_argument("file", type=Path)
    parser.add_argument("--expected-revision", type=UUID)
    args = parser.parse_args()
    try:
        revision = asyncio.run(publish_file(args.file, args.expected_revision))
    except (ValidationError, ValueError, OSError, CatalogConflictError, SQLAlchemyError):
        print("Invalid catalogue or conflicting revision; no update committed", file=sys.stderr)
        raise SystemExit(1) from None
    print(revision)


if __name__ == "__main__":
    main()
