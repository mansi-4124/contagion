import asyncio
import ssl
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine  # Changed to direct async engine

from alembic import context

from app.config.settings import settings
from app.models import Base  # Correctly imported models

# Alembic Config object, provides access to values in alembic.ini
config = context.config

# Inject the Neon URL from our typed Settings object at runtime.
config.set_main_option("sqlalchemy.url", settings.database.url)

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Correctly assigned metadata for --autogenerate to see your tables
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (generates SQL, no live DB connection)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations against Neon PostgreSQL."""

    ssl_context = ssl.create_default_context()
    print(settings.database.url)
    connectable = create_async_engine(
        settings.database.url,
        poolclass=pool.NullPool,
        pool_pre_ping=True,
        connect_args={
            "ssl": ssl_context,
            "command_timeout": 60,
        },
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (live DB connection, the normal case)."""
    import sys
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
