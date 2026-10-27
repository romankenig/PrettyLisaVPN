"""Alembic environment for the asynchronous PostgreSQL connection."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from prettylisavpn.account_messages import model as account_messages_model  # noqa: F401
from prettylisavpn.auth_sessions import model as auth_sessions_model  # noqa: F401
from prettylisavpn.billing import model as billing_model  # noqa: F401
from prettylisavpn.config import Settings
from prettylisavpn.database import Base
from prettylisavpn.devices import model as devices_model  # noqa: F401
from prettylisavpn.fleet import model as fleet_model  # noqa: F401
from prettylisavpn.legacy_vpn import nodes as vpn_nodes_model  # noqa: F401
from prettylisavpn.legacy_vpn import sessions as vpn_sessions_model  # noqa: F401
from prettylisavpn.product_events import model as product_events_model  # noqa: F401
from prettylisavpn.subscriptions import model as subscriptions_model  # noqa: F401
from prettylisavpn.support import model as support_model  # noqa: F401
from prettylisavpn.users import model as users_model  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def database_configuration() -> dict[str, str]:
    """Return an Alembic engine configuration without storing credentials in files."""
    return {"sqlalchemy.url": Settings().postgres_url.get_secret_value()}


def run_migrations_offline() -> None:
    """Render SQL without opening a database connection."""
    context.configure(
        url=database_configuration()["sqlalchemy.url"],
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def apply_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Apply migrations through SQLAlchemy's asynchronous engine."""
    connectable = async_engine_from_config(
        database_configuration(),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(apply_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    import asyncio

    asyncio.run(run_migrations_online())
