# Feature: postgresql-database-integration, Property 3: Relationship uniqueness
"""
Property-based tests for uniqueness constraints on Enrollment and Consent.

Verifies that attempting to INSERT a duplicate record (same composite key or
same unique FK) raises an IntegrityError and leaves exactly one record in the
table.

**Validates: Requirements 4.3, 4.4, 4.6**
"""

import uuid
from datetime import datetime, timezone

import pytest
import sqlalchemy as sa
from hypothesis import given, settings as h_settings
from hypothesis import strategies as st
from sqlalchemy import StaticPool, create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

# ---------------------------------------------------------------------------
# In-memory SQLite engine with the real SQLModel table definitions.
#
# We create a fresh engine + tables for each test invocation so that
# Hypothesis examples are fully isolated from one another.
# ---------------------------------------------------------------------------

# Import the ORM models — they carry the UniqueConstraint metadata.
from app.infrastructure.models.enrollment import Enrollment
from app.infrastructure.models.consent import Consent

# SQLModel uses SQLAlchemy metadata; we need the shared MetaData object.
from sqlmodel import SQLModel


def _make_engine():
    """
    Create a fresh in-memory SQLite engine with all relevant tables.

    SQLite does not support PostgreSQL-specific types (UUID, etc.) but
    SQLModel/SQLAlchemy will fall back to VARCHAR for UUID fields on SQLite,
    which is sufficient for constraint testing.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # Enable foreign key enforcement in SQLite (off by default)
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, _):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=OFF")  # FKs reference other tables we don't create
        cursor.close()

    # Create only the two tables we need (no FK dependencies to satisfy)
    SQLModel.metadata.create_all(engine, tables=[
        Enrollment.__table__,
        Consent.__table__,
    ])
    return engine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _count(session: Session, model, **filters) -> int:
    # SQLite stores UUID fields via the Uuid type's .hex processor (no dashes).
    # Use raw SQL with hex-encoded UUID strings to match what's actually stored.
    table = model.__tablename__
    where_clauses = " AND ".join(f"{col} = :{col}" for col in filters)
    sql = sa.text(f"SELECT COUNT(*) FROM {table} WHERE {where_clauses}")
    params = {col: val.hex if isinstance(val, uuid.UUID) else str(val) for col, val in filters.items()}
    return session.execute(sql, params).scalar_one()


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------

@pytest.mark.anyio
@h_settings(max_examples=25)
@given(student_id=st.uuids(), course_id=st.uuids())
async def test_enrollment_uniqueness(student_id: uuid.UUID, course_id: uuid.UUID):
    """
    **Validates: Requirements 4.3**

    Property 3 (Enrollment): For any (student_id, course_id) pair, a second
    INSERT with the same values must raise IntegrityError and leave exactly
    one record in the enrollments table.
    """
    engine = _make_engine()

    # First INSERT in its own session — must succeed
    with Session(engine) as session:
        first = Enrollment(
            id=uuid.uuid4(),
            student_id=student_id,
            course_id=course_id,
            enrollment_date=_now(),
        )
        session.add(first)
        session.commit()

    # Second INSERT in a new session — must fail with IntegrityError
    with Session(engine) as session:
        duplicate = Enrollment(
            id=uuid.uuid4(),
            student_id=student_id,
            course_id=course_id,
            enrollment_date=_now(),
        )
        session.add(duplicate)
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

    # Verify exactly one record remains in a clean session
    with Session(engine) as session:
        count = _count(session, Enrollment, student_id=student_id, course_id=course_id)
        assert count == 1, (
            f"Expected exactly 1 Enrollment for ({student_id}, {course_id}), got {count}"
        )

    engine.dispose()


@pytest.mark.anyio
@h_settings(max_examples=25)
@given(student_id=st.uuids(), course_id=st.uuids())
async def test_consent_student_id_uniqueness(student_id: uuid.UUID, course_id: uuid.UUID):
    """
    **Validates: Requirements 4.6 (updated after migration 0022)**

    Property 3 (Consent): Consent records are append-only — revocation and
    re-acceptance each create a new row for the same student_id.  The UNIQUE
    constraint on student_id was intentionally dropped in migration 0022 to
    support this pattern.  A second INSERT for the same student_id must
    succeed and leave exactly two Consent records.

    The course_id parameter is kept to match the @given signature convention
    but is unused — Consent rows are keyed only by student_id.
    """
    engine = _make_engine()

    # First INSERT — must succeed
    with Session(engine) as session:
        first = Consent(
            id=uuid.uuid4(),
            student_id=student_id,
            accepted=True,
            terms_version="v1.0",
            accepted_at=_now(),
        )
        session.add(first)
        session.commit()

    # Second INSERT — must also succeed (no unique constraint since 0022)
    with Session(engine) as session:
        second = Consent(
            id=uuid.uuid4(),
            student_id=student_id,
            accepted=False,
            terms_version="v1.1",
            accepted_at=_now(),
        )
        session.add(second)
        session.commit()  # must NOT raise

    # Verify both records exist
    with Session(engine) as session:
        count = _count(session, Consent, student_id=student_id)
        assert count == 2, (
            f"Expected 2 Consent rows for student_id={student_id}, got {count}"
        )

    engine.dispose()
