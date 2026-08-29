"""Alembic environment configuration."""
import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# Load the alembic.ini config
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

from dotenv import load_dotenv
load_dotenv()

# Override with DATABASE_URL env var if set (for Railway / production)
database_url = os.getenv("DATABASE_URL", "")
if database_url:
    # Alembic requires psycopg2 sync driver for migrations
    sync_url = database_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
    config.set_main_option("sqlalchemy.url", sync_url)

# Import all models so Alembic can detect them
from app.models.user import User       # noqa: F401
from app.models.memory import Memory   # noqa: F401
from app.models.session import SessionTurn  # noqa: F401
from app.database import Base

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
