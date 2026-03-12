import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

# Import all models so Alembic can discover them
from app.models import *  # noqa: F401, F403
from app.models.base import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata

# Get database URL from environment, converting asyncpg -> psycopg2 for sync
# and keeping asyncpg for async migrations
_db_url = os.environ.get("DATABASE_URL", config.get_main_option("sqlalchemy.url", ""))

# For async migrations, keep asyncpg; for sync, convert
_async_url = _db_url
if "postgresql://" in _db_url and "asyncpg" not in _db_url:
    _async_url = _db_url.replace("postgresql://", "postgresql+asyncpg://")
elif "postgresql+psycopg2://" in _db_url:
    _async_url = _db_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://")


def get_url() -> str:
    return _async_url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    # Use sync URL for offline mode
    sync_url = _async_url.replace("+asyncpg", "+psycopg2").replace("+aiosqlite", "")
    context.configure(
        url=sync_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations using an async engine."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_url()

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
