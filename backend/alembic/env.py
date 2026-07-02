import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

from app.config.settings import settings

# Alembic Config object, provides access to values in alembic.ini
config = context.config

# Inject the Neon URL from our typed Settings object at runtime.
# settings.database.url comes from DB_URL env var (see app/config/settings.py, D0-05).
config.set_main_option("sqlalchemy.url", settings.database.url)

# Interpret the config file for Python logging (unchanged from template)
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import Base.metadata here once models exist (Day 1, D1-01).
# Left as None for D0 — alembic still runs fine with no autogenerate target.
# On D1, change this to:
#     from app.models.base import Base
#     target_metadata = Base.metadata
target_metadata = None


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
    """Create an async Engine and run migrations against Neon."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,  # don't pool connections for one-off migration runs
        connect_args={"ssl": "require"},  # Neon requires SSL
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (live DB connection, the normal case)."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()