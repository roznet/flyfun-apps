"""Alembic environment configuration.

Reads DATABASE_URL from environment (or falls back to SQLite for local dev).
Imports all models so autogenerate can detect schema changes.
"""

import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# -- Alembic Config object --
config = context.config

# Set up Python logging from the .ini file
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# -- Import ALL models so Base.metadata knows every table --
# Shared tables (users, api_tokens, user_preferences, cost_ledger)
from flyfun_common.db.models import Base  # noqa: E402

# App-specific tables (chat_usage, anon_chat_usage) — registered on the same Base
import db.models  # noqa: E402, F401

target_metadata = Base.metadata

# -- Resolve database URL from environment --
# Same logic as flyfun_common.db.engine.get_engine():
#   production → DATABASE_URL env var (MySQL)
#   development → sqlite:///data/flyfun.db
_db_url = os.environ.get("DATABASE_URL")
if not _db_url:
    # Resolve data dir relative to this file's parent (web/server/)
    _server_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.environ.get("DATA_DIR", os.path.join(_server_dir, "data"))
    os.makedirs(data_dir, exist_ok=True)
    _db_url = f"sqlite:///{data_dir}/flyfun.db"

config.set_main_option("sqlalchemy.url", _db_url)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL without a live connection)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table="alembic_version_maps",
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (with a live DB connection)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table="alembic_version_maps",
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
