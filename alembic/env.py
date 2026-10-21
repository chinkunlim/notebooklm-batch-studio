"""Alembic environment: connects with the app's config and compares against the ORM models."""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context

from notebooklm_batch_studio.adapters.db import models  # noqa: F401 - registers every table on Base.metadata
from notebooklm_batch_studio.adapters.db.base import Base
from notebooklm_batch_studio.adapters.db.session import create_db_engine
from notebooklm_batch_studio.config.settings import load_config

alembic_config = context.config
if alembic_config.config_file_name:
    fileConfig(alembic_config.config_file_name)
DATABASE_URL = load_config().database_url
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of connecting (`alembic upgrade head --sql`)."""
    context.configure(
        url=DATABASE_URL, target_metadata=target_metadata, literal_binds=True, render_as_batch=True
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Connect to the database and apply migrations (batch mode so SQLite can ALTER tables)."""
    with create_db_engine(DATABASE_URL).connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
