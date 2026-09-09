"""
Alembic environment configuration.

Reads the database URL from app.config.settings (the same source of truth
the FastAPI app uses) so credentials are never duplicated or hardcoded.

Alembic runs synchronously, so we use DATABASE_URL_SYNC (psycopg2 driver).
"""

import sys
from pathlib import Path
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

# ── Ensure the backend/ directory is on sys.path ─────────────────
# Alembic runs from the directory containing alembic.ini, but Python
# needs backend/ on the path to resolve `from app.config import ...`.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# ── Import the app's settings and model metadata ─────────────────
# This import also triggers all model module imports (via models/__init__.py),
# ensuring Base.metadata contains every table for autogenerate.
from app.config import settings
from app.models import Base

# ── Alembic Config object ───────────────────────────────────────
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# NOTE: We intentionally do NOT call config.set_main_option("sqlalchemy.url", ...)
# because configparser's % interpolation chokes on URL-encoded characters
# (e.g. %40 for @). Instead we pass the URL directly to create_engine below.

# Model metadata for autogenerate support.
target_metadata = Base.metadata


# ── Offline migrations (generate SQL without a live DB) ──────────
def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    context.configure(
        url=settings.DATABASE_URL_SYNC,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


# ── Online migrations (requires a live DB connection) ────────────
def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = create_engine(
        settings.DATABASE_URL_SYNC,
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

