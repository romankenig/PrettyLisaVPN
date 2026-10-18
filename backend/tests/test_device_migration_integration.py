"""Check populated legacy upgrade/downgrade in a separate disposable database."""

import asyncio
import os
import sys
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from prettylisavpn.config import Settings

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.getenv("RUN_INTEGRATION_TESTS") != "1", reason="Needs CI PostgreSQL"),
]


async def test_legacy_devices_remain_null_and_timestamp_column_round_trips():
    source = make_url(Settings().postgres_url.get_secret_value())
    database = "device_migration_" + uuid4().hex
    admin = create_async_engine(source, isolation_level="AUTOCOMMIT", hide_parameters=True)
    async with admin.connect() as connection:
        await connection.execute(text('CREATE DATABASE "' + database + '"'))
    target = source.set(database=database)
    engine = create_async_engine(target, hide_parameters=True)
    environment = {**os.environ, "POSTGRES_URL": target.render_as_string(hide_password=False)}

    async def alembic(*args):
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "alembic",
            *args,
            env=environment,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, errors = await process.communicate()
        assert process.returncode == 0, (
            "Alembic subprocess failed: " + errors.decode().splitlines()[-1]
        )

    try:
        await alembic("upgrade", "0017_profile_evidence")
        user_id, device_id, installation_id = uuid4(), uuid4(), uuid4()
        async with engine.begin() as connection:
            await connection.execute(
                text("INSERT INTO users(id,email,status) VALUES (:id,:email,'ACTIVE')"),
                {"id": user_id, "email": "legacy@example.com"},
            )
            await connection.execute(
                text(
                    "INSERT INTO devices(id,user_id,installation_id,platform,device_name,status) "
                    "VALUES (:id,:user,:installation,'WINDOWS','Legacy','ACTIVE')"
                ),
                {"id": device_id, "user": user_id, "installation": installation_id},
            )
        await alembic("upgrade", "head")
        async with engine.begin() as connection:
            row = (await connection.execute(text("SELECT last_login_at FROM devices"))).one()
            assert row.last_login_at is None
            kind = await connection.scalar(
                text(
                    "SELECT data_type FROM information_schema.columns "
                    "WHERE table_name='devices' AND column_name='last_login_at'"
                )
            )
            assert kind == "timestamp with time zone"
            await connection.execute(text("UPDATE devices SET last_login_at=now()"))
        await alembic("downgrade", "0017_profile_evidence")
        async with engine.connect() as connection:
            assert await connection.scalar(text("SELECT count(*) FROM devices")) == 1
        await alembic("upgrade", "head")
        await alembic("check")
    finally:
        await engine.dispose()
        async with admin.connect() as connection:
            await connection.execute(text('DROP DATABASE "' + database + '" WITH (FORCE)'))
        await admin.dispose()
