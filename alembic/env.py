"""
alembic/env.py

Alembic migration environment — connects to the database and applies migrations.

Role: Database Administrator (DBA)

Supports both:
  - Sync mode (for `alembic upgrade head` CLI)
  - Offline mode (generate SQL scripts without DB connection)

Usage:
  alembic upgrade head                           # apply all pending migrations
  alembic downgrade -1                           # rollback last migration
  alembic revision --autogenerate -m "message"   # auto-generate new migration
  alembic current                                # show current revision
  alembic history                                # show all migrations
  alembic upgrade head --sql                     # preview SQL without running
"""
from __future__ import annotations

import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context
from dotenv import load_dotenv

# Load .env so DATABASE_URL is available when running from CLI
load_dotenv()

# Alembic Config object — access to alembic.ini values
config = context.config

# Set up logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ── Import all SQLModel table models ─────────────────────────
# This populates SQLModel.metadata so autogenerate works correctly.
# Add any new models here when you create them.
from sqlmodel import SQLModel
import backend.models  # noqa: F401 — registers all table classes

target_metadata = SQLModel.metadata


# ── Database URL ─────────────────────────────────────────────

def _sync_url(url: str) -> str:
    """
    Convert async driver URLs to sync equivalents for Alembic.
    Alembic's engine_from_config requires a sync DBAPI driver.
    """
    replacements = {
        "sqlite+aiosqlite:///": "sqlite:///",
        "postgresql+asyncpg://": "postgresql+psycopg2://",
        "mysql+aiomysql://": "mysql+pymysql://",
    }
    for async_prefix, sync_prefix in replacements.items():
        if url.startswith(async_prefix):
            return url.replace(async_prefix, sync_prefix, 1)
    return url


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite+aiosqlite:///./safety_monitor.db",
)
SYNC_URL = _sync_url(DATABASE_URL)

# Override the URL in alembic.ini with our env-var version
config.set_main_option("sqlalchemy.url", SYNC_URL)


# ── Migration functions ───────────────────────────────────────

def run_migrations_offline() -> None:
    """
    Offline mode: generate SQL script without connecting to DB.
    Useful for reviewing changes before applying to production.

    Run with: alembic upgrade head --sql > migration.sql
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        render_as_batch=True,  # Required for SQLite ALTER TABLE
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Online mode: connect to DB and apply migrations directly.
    Used by: alembic upgrade head
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            render_as_batch=True,  # Required for SQLite ALTER TABLE
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
