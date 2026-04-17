"""
Shared fixtures for integration tests.

Uses SQLite in-memory (sync) to validate constraint behaviour, and
mock AsyncSession for repository-level tests that exercise business logic.
"""

import pytest


@pytest.fixture
def anyio_backend():
    """Pin all async integration tests to asyncio (trio is not installed)."""
    return "asyncio"

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
import sqlalchemy as sa
from sqlalchemy import StaticPool, create_engine, event
from sqlalchemy.orm import Session
from sqlmodel import SQLModel

from app.infrastructure.models.audit_log import AuditLog
from app.infrastructure.models.consent import Consent
from app.infrastructure.models.course import Course
from app.infrastructure.models.enrollment import Enrollment
from app.infrastructure.models.professor_course import ProfessorCourse
from app.infrastructure.models.program import Program
from app.infrastructure.models.university import University
from app.infrastructure.models.user import User


# ---------------------------------------------------------------------------
# SQLite in-memory engine (for constraint / integrity tests)
# ---------------------------------------------------------------------------

ALL_TABLES = [
    University.__table__,
    Program.__table__,
    User.__table__,
    Course.__table__,
    Enrollment.__table__,
    ProfessorCourse.__table__,
    Consent.__table__,
    AuditLog.__table__,
]


def make_sqlite_engine():
    """Return a fresh SQLite in-memory engine with all tables created."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _set_pragma(dbapi_conn, _):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=OFF")
        cursor.close()

    SQLModel.metadata.create_all(engine, tables=ALL_TABLES)
    return engine


@pytest.fixture
def sqlite_session():
    """Yield a synchronous SQLite Session with all tables, rolled back after each test."""
    engine = make_sqlite_engine()
    with Session(engine) as session:
        yield session
    engine.dispose()


# ---------------------------------------------------------------------------
# Mock AsyncSession factory for repository tests
# ---------------------------------------------------------------------------

def make_mock_session(stored_objects: dict | None = None):
    """
    Build a mock AsyncSession that stores added objects by type and
    returns them on execute().

    stored_objects: optional dict mapping type -> list of pre-seeded objects
    """
    if stored_objects is None:
        stored_objects = {}

    added: list = []

    def _add(obj):
        added.append(obj)
        t = type(obj)
        stored_objects.setdefault(t, []).append(obj)

    async def _execute(stmt, *args, **kwargs):
        result = MagicMock()
        # Return the last added object of any non-AuditLog type
        non_audit = [o for o in added if not isinstance(o, AuditLog)]
        result.scalar_one_or_none.return_value = non_audit[-1] if non_audit else None
        result.scalars.return_value.all.return_value = non_audit
        return result

    mock_session = AsyncMock()
    mock_session.add = MagicMock(side_effect=_add)
    mock_session.flush = AsyncMock()
    mock_session.refresh = AsyncMock()
    mock_session.execute = AsyncMock(side_effect=_execute)
    mock_session._added = added
    return mock_session


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def now() -> datetime:
    return datetime.now(timezone.utc)


def make_user(**kwargs) -> User:
    defaults = dict(
        id=uuid.uuid4(),
        email=f"user_{uuid.uuid4().hex[:8]}@test.com",
        full_name="Test User",
        role="STUDENT",
        ml_consent=False,
        created_at=now(),
        updated_at=now(),
    )
    defaults.update(kwargs)
    return User(**defaults)


def make_university(**kwargs) -> University:
    defaults = dict(
        id=uuid.uuid4(),
        name="Test University",
        code=f"TU{uuid.uuid4().hex[:6].upper()}",
        country="Colombia",
        city="Bogotá",
        active=True,
        created_at=now(),
    )
    defaults.update(kwargs)
    return University(**defaults)


def make_program(**kwargs) -> Program:
    defaults = dict(
        id=uuid.uuid4(),
        campus_id=uuid.uuid4(),
        university_id=uuid.uuid4(),
        institution="USBCO",
        degree_type="PREG",
        program_code=f"P{uuid.uuid4().hex[:6].upper()}",
        program_name="Test Program",
        pensum=f"PEN{uuid.uuid4().hex[:8]}",
        academic_group="MFPSI",
        location="SAN BENITO",
        snies_code=int(uuid.uuid4().int % 100000),
        created_at=now(),
    )
    defaults.update(kwargs)
    return Program(**defaults)


def make_course(**kwargs) -> Course:
    defaults = dict(
        id=uuid.uuid4(),
        code=f"CS{uuid.uuid4().hex[:4].upper()}",
        name="Test Course",
        credits=3,
        academic_period="2024-1",
        program_id=uuid.uuid4(),
        created_at=now(),
    )
    defaults.update(kwargs)
    return Course(**defaults)
