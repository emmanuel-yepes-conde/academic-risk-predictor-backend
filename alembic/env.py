"""
Alembic environment configuration with async support.
Imports all ORM models so SQLModel metadata picks them up for autogenerate.
"""

import asyncio
from logging.config import fileConfig

from sqlalchemy.ext.asyncio import create_async_engine
from alembic import context
from sqlmodel import SQLModel

# Import settings to get DATABASE_URL
from app.core.config import settings

# Import all ORM models so their tables are registered in SQLModel.metadata
from app.infrastructure.models.user import User  # noqa: F401
from app.infrastructure.models.course import Course  # noqa: F401
from app.infrastructure.models.enrollment import Enrollment  # noqa: F401
from app.infrastructure.models.professor_course import ProfessorCourse  # noqa: F401
from app.infrastructure.models.audit_log import AuditLog  # noqa: F401
from app.infrastructure.models.consent import Consent  # noqa: F401
from app.infrastructure.models.program import Program  # noqa: F401
from app.infrastructure.models.student_profile import StudentProfile  # noqa: F401
from app.infrastructure.models.university import University  # noqa: F401

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Use SQLModel.metadata as the target for autogenerate
target_metadata = SQLModel.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL and not an Engine.
    Calls to context.execute() here emit the given string to the
    script output.
    """
    url = settings.DATABASE_URL
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations using an async engine."""
    connectable = create_async_engine(settings.DATABASE_URL)

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode using asyncio."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
