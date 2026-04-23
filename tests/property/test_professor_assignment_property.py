# Feature: multi-university-support, Property 10: Un curso tiene exactamente un profesor asignado
"""
Property-based test for professor-course assignment idempotency.

Verifies that for any course, assigning professor A and then professor B
results in exactly one active assignment (professor B). The assignment
operation is idempotent: it always results in exactly one professor per course.

**Validates: Requirements 4.1, 4.2**
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4, UUID

import pytest
from hypothesis import given, settings as h_settings, HealthCheck, assume
from hypothesis import strategies as st

from app.application.schemas.professor_course import ProfessorAssignmentRead
from app.application.services.professor_course_service import ProfessorCourseService
from app.domain.enums import RoleEnum, UserStatusEnum
from app.infrastructure.models.course import Course
from app.infrastructure.models.user import User

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

professor_id_strategy = st.uuids()
course_id_strategy = st.uuids()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_professor_user(professor_id: UUID) -> User:
    """Create a User ORM object with PROFESSOR role."""
    return User(
        id=professor_id,
        email=f"prof-{professor_id}@test.edu",
        full_name=f"Professor {professor_id}",
        role=RoleEnum.PROFESSOR,
        status=UserStatusEnum.ACTIVE,
    )


def _make_course(course_id: UUID) -> Course:
    """Create a Course ORM object."""
    return Course(
        id=course_id,
        code=f"COURSE-{course_id}",
        name=f"Course {course_id}",
        credits=3,
        academic_period="2026-1",
        program_id=uuid4(),
        professor_id=None,
    )


def _build_service(course_id: UUID, professor_ids: list[UUID]):
    """
    Build a ProfessorCourseService with a fully mocked session that
    simulates the DB state for sequential professor assignments.

    The service updates Course.professor_id directly (no intermediate table).

    Returns (service, course) where course tracks the current professor_id.
    """
    session = AsyncMock()

    course = _make_course(course_id)
    professors = {pid: _make_professor_user(pid) for pid in professor_ids}

    class FakeScalarResult:
        def __init__(self, value):
            self._value = value

        def scalar_one_or_none(self):
            return self._value

    async def mock_execute(stmt):
        """Return the professor User for the User lookup query."""
        try:
            compiled = stmt.compile()
            params = compiled.params
        except Exception:
            params = {}

        # Extract the bound user id from the WHERE clause parameters
        for key, value in params.items():
            if value in professors:
                return FakeScalarResult(professors[value])

        return FakeScalarResult(None)

    session.execute = AsyncMock(side_effect=mock_execute)
    session.add = MagicMock()
    session.flush = AsyncMock()

    async def mock_refresh(obj):
        pass  # Course already has an id

    session.refresh = AsyncMock(side_effect=mock_refresh)

    # Build the service manually to inject mocks
    service = object.__new__(ProfessorCourseService)
    service._session = session
    service._audit = AsyncMock()
    service._audit.register = AsyncMock()
    service._course_repo = AsyncMock()
    service._course_repo.obtener_por_id = AsyncMock(return_value=course)

    return service, course


# ---------------------------------------------------------------------------
# Property test
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@h_settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(
    course_id=course_id_strategy,
    professor_ids=st.lists(
        st.uuids(), min_size=2, max_size=5, unique=True,
    ),
)
async def test_course_has_exactly_one_professor_after_sequential_assignments(
    course_id: UUID,
    professor_ids: list[UUID],
):
    """
    Property 10: Un curso tiene exactamente un profesor asignado
    (idempotencia de asignación).

    For any course C, if we sequentially assign professors P1, P2, ..., Pn
    to C, the final state must be that only Pn is assigned to C.
    Each intermediate assignment must also result in exactly one professor.

    Specifically:
      - After each assign_professor(C, Pi), the returned ProfessorAssignmentRead
        must reference course_id == C and professor_id == Pi
      - After all assignments, Course.professor_id must equal the last professor

    **Validates: Requirements 4.1, 4.2**
    """
    assume(course_id not in professor_ids)

    service, course = _build_service(course_id, professor_ids)

    last_result = None
    for i, professor_id in enumerate(professor_ids):
        result = await service.assign_professor(course_id, professor_id)

        # --- Each assignment must return a valid ProfessorAssignmentRead ---
        assert isinstance(result, ProfessorAssignmentRead), (
            f"Assignment {i+1}: expected ProfessorAssignmentRead, "
            f"got {type(result).__name__}"
        )

        # --- The returned record must reference the correct course ---
        assert result.course_id == course_id, (
            f"Assignment {i+1}: course_id mismatch: "
            f"expected {course_id}, got {result.course_id}"
        )

        # --- The returned record must reference the assigned professor ---
        assert result.professor_id == professor_id, (
            f"Assignment {i+1}: professor_id mismatch: "
            f"expected {professor_id}, got {result.professor_id}"
        )

        # --- The id must be non-None ---
        assert result.id is not None, (
            f"Assignment {i+1}: id must not be None"
        )

        last_result = result

    # --- After all assignments, Course.professor_id must be the last professor ---
    last_professor_id = professor_ids[-1]
    assert course.professor_id == last_professor_id, (
        f"Final Course.professor_id mismatch: "
        f"expected {last_professor_id}, got {course.professor_id}"
    )

    # --- The last returned result must match the final state ---
    assert last_result.professor_id == last_professor_id, (
        f"Last result professor_id mismatch: "
        f"expected {last_professor_id}, got {last_result.professor_id}"
    )
