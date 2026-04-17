# Feature: postgresql-database-integration, Property 8: Privacy filter RB-04
"""
Property-based tests for the RB-04 privacy filter in UserRepository.list.

Verifies that UserRepository.list(professor_id=...) returns exactly the
students enrolled in courses assigned to the given professor, and that
no non-enrolled students appear in the results.

**Validates: Requirements 7.1, 7.2, 7.3**
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from hypothesis import assume, given, settings as h_settings
from hypothesis import strategies as st
from sqlalchemy import StaticPool, create_engine, event, select
from sqlalchemy.orm import Session
from sqlmodel import SQLModel

from app.domain.enums import RoleEnum
from app.infrastructure.models.course import Course
from app.infrastructure.models.enrollment import Enrollment
from app.infrastructure.models.professor_course import ProfessorCourse
from app.infrastructure.models.program import Program
from app.infrastructure.models.university import University
from app.infrastructure.models.user import User
from app.infrastructure.repositories.user_repository import UserRepository

# ---------------------------------------------------------------------------
# In-memory SQLite engine factory
#
# A fresh engine is created per Hypothesis example to guarantee full
# isolation between test runs.
# ---------------------------------------------------------------------------

_TABLES = [
    University.__table__,
    Program.__table__,
    User.__table__,
    Course.__table__,
    Enrollment.__table__,
    ProfessorCourse.__table__,
]


def _make_engine():
    """Create a fresh in-memory SQLite engine with the required tables."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _set_pragma(dbapi_conn, _):
        cursor = dbapi_conn.cursor()
        # Disable FK enforcement — referenced tables (audit_logs) are not
        # created here; we only need the tables relevant to the filter.
        cursor.execute("PRAGMA foreign_keys=OFF")
        cursor.close()

    SQLModel.metadata.create_all(engine, tables=_TABLES)
    return engine


# ---------------------------------------------------------------------------
# Async session bridge
#
# UserRepository uses AsyncSession.execute(stmt).  We bridge async calls to
# a real synchronous SQLite Session so the actual JOIN query is executed
# against real data — no mocking of query logic.
# ---------------------------------------------------------------------------

def _make_async_session_bridge(sync_session: Session) -> AsyncMock:
    """
    Return an AsyncMock that delegates execute() to a real sync Session.

    This allows UserRepository (which expects AsyncSession) to run its
    actual SQL statements against an in-memory SQLite database.
    """
    mock_session = AsyncMock()

    async def _execute(stmt, *args, **kwargs):
        # Run the SQLAlchemy Core/ORM statement synchronously
        result = sync_session.execute(stmt)
        return result

    mock_session.execute = AsyncMock(side_effect=_execute)
    # add/flush/refresh are not used by list(); provide no-ops for safety
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()
    mock_session.refresh = AsyncMock()

    return mock_session


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _make_user(role: RoleEnum, index: int) -> User:
    """Create a User ORM instance with a unique email."""
    uid = uuid.uuid4()
    return User(
        id=uid,
        email=f"{role.value.lower()}_{index}_{uid.hex[:8]}@test.example",
        full_name=f"Test {role.value} {index}",
        role=role,
        ml_consent=False,
        created_at=_now(),
        updated_at=_now(),
    )


def _make_university() -> University:
    """Create a University ORM instance."""
    uid = uuid.uuid4()
    return University(
        id=uid,
        name="Test University",
        code=f"TU{uid.hex[:6].upper()}",
        country="Colombia",
        city="Bogotá",
        active=True,
        created_at=_now(),
    )


def _make_program(university_id: uuid.UUID) -> Program:
    """Create a Program ORM instance linked to a university."""
    uid = uuid.uuid4()
    return Program(
        id=uid,
        campus_id=uuid.uuid4(),
        university_id=university_id,
        institution="USBCO",
        degree_type="PREG",
        program_code=f"P{uid.hex[:6].upper()}",
        program_name="Test Program",
        pensum=f"PEN{uid.hex[:8]}",
        academic_group="MFPSI",
        location="SAN BENITO",
        snies_code=int(uid.int % 100000),
        created_at=_now(),
    )


def _make_course(program_id: uuid.UUID) -> Course:
    """Create a Course ORM instance linked to a program."""
    uid = uuid.uuid4()
    return Course(
        id=uid,
        code=f"CS{uid.hex[:6].upper()}",
        name="Test Course",
        credits=3,
        academic_period="2025-I",
        program_id=program_id,
        created_at=_now(),
    )


# ---------------------------------------------------------------------------
# Property test
# ---------------------------------------------------------------------------

@pytest.mark.anyio
@h_settings(max_examples=100)
@given(
    n_students=st.integers(min_value=1, max_value=10),
    n_enrolled=st.integers(min_value=0, max_value=5),
)
async def test_professor_only_sees_enrolled_students(
    n_students: int, n_enrolled: int
) -> None:
    """
    **Validates: Requirements 7.1, 7.2, 7.3**

    Property 8 (Privacy filter RB-04): For any combination of n_students
    total students and n_enrolled students enrolled in the professor's course,
    UserRepository.list(professor_id=...) must return exactly n_enrolled
    students, and none of the non-enrolled students must appear in the result.
    """
    assume(n_enrolled <= n_students)

    engine = _make_engine()

    with Session(engine) as session:
        # 1. Create a professor
        professor = _make_user(RoleEnum.PROFESSOR, 0)
        session.add(professor)

        # 2. Create a university, program, course and assign it to the professor
        university = _make_university()
        session.add(university)
        session.flush()

        program = _make_program(university.id)
        session.add(program)
        session.flush()

        course = _make_course(program.id)
        session.add(course)

        professor_course = ProfessorCourse(
            id=uuid.uuid4(),
            professor_id=professor.id,
            course_id=course.id,
        )
        session.add(professor_course)

        # 3. Create n_students student users
        students = [_make_user(RoleEnum.STUDENT, i) for i in range(n_students)]
        for student in students:
            session.add(student)

        session.flush()

        # 4. Enroll exactly n_enrolled students in the professor's course
        enrolled_students = students[:n_enrolled]
        non_enrolled_students = students[n_enrolled:]

        for student in enrolled_students:
            enrollment = Enrollment(
                id=uuid.uuid4(),
                student_id=student.id,
                course_id=course.id,
                enrollment_date=_now(),
            )
            session.add(enrollment)

        session.flush()

        # 5. Build the async bridge and call UserRepository.list
        async_session = _make_async_session_bridge(session)
        repo = UserRepository(session=async_session)

        result = await repo.list(
            professor_id=professor.id,
            role=RoleEnum.STUDENT,
            skip=0,
            limit=100,
        )

        # 6. Assert exactly n_enrolled students are returned
        assert len(result) == n_enrolled, (
            f"Expected {n_enrolled} enrolled students, got {len(result)}. "
            f"n_students={n_students}, n_enrolled={n_enrolled}"
        )

        # 7. Assert all returned users are the enrolled ones
        result_ids = {u.id for u in result}
        enrolled_ids = {s.id for s in enrolled_students}
        non_enrolled_ids = {s.id for s in non_enrolled_students}

        assert result_ids == enrolled_ids, (
            f"Returned student IDs do not match enrolled IDs. "
            f"Extra: {result_ids - enrolled_ids}, Missing: {enrolled_ids - result_ids}"
        )

        # 8. Assert none of the non-enrolled students appear in the result
        assert result_ids.isdisjoint(non_enrolled_ids), (
            f"Non-enrolled students appeared in result: "
            f"{result_ids & non_enrolled_ids}"
        )

    engine.dispose()
