"""Upgrade saved 0.8.0 receipts in an isolated disposable PostgreSQL database."""

import asyncio
import os
import sys
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from prettylisavpn.billing.model import (
    BillingOperationRecord,
    SandboxMandateRecord,
    SandboxPaymentRecord,
)
from prettylisavpn.config import Settings
from prettylisavpn.connections import Postgres

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.getenv("RUN_INTEGRATION_TESTS") != "1", reason="Requires PostgreSQL"),
]


async def test_upgrade_reconstructs_active_revoked_and_unsettled_authorities():
    source = make_url(Settings().postgres_url.get_secret_value())
    database = "sandbox_upgrade_" + uuid4().hex
    admin = create_async_engine(source, isolation_level="AUTOCOMMIT", hide_parameters=True)
    target = source.set(database=database).render_as_string(hide_password=False)
    config = Settings(_env_file=None, postgres_url=target)
    postgres = Postgres(config)

    async def migrate(*args):
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "alembic", *args,
            env={**os.environ, "POSTGRES_URL": target},
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        try:
            await asyncio.wait_for(process.communicate(), timeout=45)
            assert process.returncode == 0, "Isolated sandbox migration failed"
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()

    try:
        async with admin.connect() as connection:
            await connection.execute(text('CREATE DATABASE "' + database + '"'))
        await migrate("upgrade", "0025_billing_sandbox")
        users = [uuid4() for _ in range(3)]
        async with postgres.session() as session, session.begin():
            for user_id in users:
                await session.execute(
                    text("INSERT INTO users(id,email,status) VALUES (:id,:email,'ACTIVE')"),
                    {"id": user_id, "email": str(user_id) + "@example.com"},
                )
            for user, previous, replacement, local_status, provider in [
                (users[0], None, "old", "SUCCEEDED", "development-sandbox-v1"),
                (users[0], "old", "new", "SUCCEEDED", "development-sandbox-v1"),
                (users[0], "new", None, "PENDING", "development-sandbox-v1"),
                (users[1], None, "awaiting-local-settlement", "PENDING", "development-sandbox-v1"),
                (users[2], None, "foreign-provider", "SUCCEEDED", "other-provider"),
            ]:
                operation_id = uuid4()
                session.add(BillingOperationRecord(
                    id=operation_id, user_id=user, request_id=uuid4(), fingerprint="0" * 64,
                    command={}, quote={}, provider_name=provider, status=local_status,
                    next_attempt_at=datetime.now(UTC), attempts=1, created_at=datetime.now(UTC),
                ))
                await session.flush()
                session.add(SandboxPaymentRecord(
                    operation_id=operation_id,
                    request={"previous_mandate_reference": previous},
                    result={
                        "status": "SUCCEEDED",
                        "mandate": {"reference": replacement} if replacement else None,
                        "previous_mandate_revoked": previous is not None,
                    },
                ))
        await postgres.close()
        for _ in range(2):
            await migrate("upgrade", "head")
            await migrate("check")
            async with postgres.session() as session:
                rows = list(await session.scalars(select(SandboxMandateRecord)))
                assert {row.reference: row.status for row in rows} == {
                    "old": "REVOKED", "new": "REVOKED", "awaiting-local-settlement": "ACTIVE",
                }
                assert next(row.user_id for row in rows if row.status == "ACTIVE") == users[1]
            await postgres.close()
            await migrate("downgrade", "0025_billing_sandbox")
    finally:
        await postgres.close()
        async with admin.connect() as connection:
            await connection.execute(text('DROP DATABASE IF EXISTS "' + database + '" WITH (FORCE)'))
        await admin.dispose()
