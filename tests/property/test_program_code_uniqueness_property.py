# Feature: campus-hierarchy, Property 7: Unicidad de program_code dentro de un campus
"""
Property-based test for program_code uniqueness scoped by campus.

Verifies that:
  - Two programs with the SAME program_code in the SAME campus raise
    IntegrityError on the second INSERT (scoped uniqueness enforced).
  - Two programs with the SAME program_code in DIFFERENT campuses both
    succeed (cross-campus duplication is allowed).

Uses an in-memory SQLite engine with the real SQLModel table definitions
to test the UniqueConstraint("program_code", "campus_id") on the
programs table.

**Validates: Requirements 3.4**
"""

import uuid
from datetime import datetime, timezone

import pytest
import sqlalchemy as sa
from hypothesis import given, settings as h_settings, assume
from hypothesis import strategies as st
from sqlalchemy import StaticPool, create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlmodel import SQLModel

from app.infrastructure.models.campus import Campus
from app.infrastructure.models.program import Program
from app.infrastructure.models.university import University

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

program_code_strategy = st.from_regex(r"[A-Z0-9]{3,20}", fullmatch=True)
snies_code_strategy = st.integers(min_value=1, max_value=999_999)

# ---------------------------------------------------------------------------
# Engine helper
# ---------------------------------------------------------------------------


def _make_engine():
    """
    Create a fresh in-memory SQLite engine with the universities, campuses,
    and programs tables.  FK enforcement is disabled because we insert rows
    directly and only need the UniqueConstraint to be checked.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, _):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=OFF")
        cursor.close()

    SQLModel.metadata.create_all(engine, tables=[
        University.__table__,
        Campus.__table__,
        Program.__table__,
    ])
    return engine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _make_program(
    university_id: uuid.UUID,
    campus_id: uuid.UUID,
    program_code: str,
    snies_code: int,
) -> Program:
    """Build a Program ORM instance with the given campus and code."""
    return Program(
        id=uuid.uuid4(),
        campus_id=campus_id,
        university_id=university_id,
        institution="INST",
        degree_type="PREG",
        program_code=program_code,
        program_name=f"Program {program_code}",
        pensum=f"PEN-{program_code}",
        academic_group="GRP",
        location="LOC",
        snies_code=snies_code,
        created_at=_now(),
    )


def _count_programs(session: Session, campus_id: uuid.UUID, program_code: str) -> int:
    """Count programs matching the given campus_id and program_code."""
    sql = sa.text(
        "SELECT COUNT(*) FROM programs "
        "WHERE campus_id = :cid AND program_code = :code"
    )
    params = {
        "cid": campus_id.hex,
        "code": program_code,
    }
    return session.execute(sql, params).scalar_one()


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@h_settings(max_examples=100)
@given(
    program_code=program_code_strategy,
    snies_a=snies_code_strategy,
    snies_b=snies_code_strategy,
)
async def test_same_program_code_same_campus_raises_integrity_error(
    program_code: str,
    snies_a: int,
    snies_b: int,
):
    """
    Property 7 (same campus): For any program_code, inserting two programs
    with that code into the SAME campus must raise IntegrityError on the
    second INSERT, leaving exactly one record.

    **Validates: Requirements 3.4**
    """
    # snies_code has a global unique constraint — ensure they differ
    assume(snies_a != snies_b)

    engine = _make_engine()
    university_id = uuid.uuid4()
    campus_id = uuid.uuid4()

    # First INSERT — must succeed
    with Session(engine) as session:
        first = _make_program(university_id, campus_id, program_code, snies_a)
        session.add(first)
        session.commit()

    # Second INSERT with same program_code + same campus — must fail
    with Session(engine) as session:
        duplicate = _make_program(university_id, campus_id, program_code, snies_b)
        session.add(duplicate)
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

    # Verify exactly one record exists for this (campus, program_code)
    with Session(engine) as session:
        count = _count_programs(session, campus_id, program_code)
        assert count == 1, (
            f"Expected exactly 1 program with code {program_code!r} in campus "
            f"{campus_id}, got {count}"
        )

    engine.dispose()


@pytest.mark.anyio
@h_settings(max_examples=100)
@given(
    program_code=program_code_strategy,
    snies_a=snies_code_strategy,
    snies_b=snies_code_strategy,
)
async def test_same_program_code_different_campuses_both_succeed(
    program_code: str,
    snies_a: int,
    snies_b: int,
):
    """
    Property 7 (different campuses): For any program_code, inserting two
    programs with that code into DIFFERENT campuses must both succeed.
    The scoped uniqueness constraint allows the same program_code across
    distinct campuses (including within the same university).

    **Validates: Requirements 3.4**
    """
    # snies_code has a global unique constraint — ensure they differ
    assume(snies_a != snies_b)

    engine = _make_engine()
    university_id = uuid.uuid4()
    campus_a = uuid.uuid4()
    campus_b = uuid.uuid4()

    # INSERT into campus A — must succeed
    with Session(engine) as session:
        prog_a = _make_program(university_id, campus_a, program_code, snies_a)
        session.add(prog_a)
        session.commit()

    # INSERT into campus B with same program_code — must also succeed
    with Session(engine) as session:
        prog_b = _make_program(university_id, campus_b, program_code, snies_b)
        session.add(prog_b)
        session.commit()

    # Verify one record per campus
    with Session(engine) as session:
        count_a = _count_programs(session, campus_a, program_code)
        count_b = _count_programs(session, campus_b, program_code)
        assert count_a == 1, (
            f"Expected 1 program in campus A ({campus_a}), got {count_a}"
        )
        assert count_b == 1, (
            f"Expected 1 program in campus B ({campus_b}), got {count_b}"
        )

    engine.dispose()
