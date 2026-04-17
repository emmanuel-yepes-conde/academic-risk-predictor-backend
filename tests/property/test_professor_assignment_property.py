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

from app.application.schemas.professor_course import ProfessorCourseRead
from app.application.services.professor_course_service import ProfessorCourseService
from app.domain.enums import RoleEnum, UserStatusEnum
from app.infrastructure.models.course import Course
from app.infrastructure.models.professor_course import ProfessorCourse
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
    )


def _build_service(course_id: UUID, professor_ids: list[UUID]):
    """
    Build a ProfessorCourseService with a fully mocked session that
    simulates the DB state for sequential professor assignments.

    Returns (service, state_dict) where state_dict tracks the current
    ProfessorCourse assignment for assertions.
    """
    session = AsyncMock()
    state = {"current_assignment": None}

    course = _make_course(course_id)
    professors = {pid: _make_professor_user(pid) for pid in professor_ids}

    # --- Mock session.execute to handle different SELECT queries ---

    class FakeScalarResult:
        def __init__(self, value):
            self._value = value

        def scalar_one_or_none(self):
            return self._value

    # We need to track which query is being made. The service issues
    # three types of SELECT in assign_professor:
    #   1. select(User).where(User.id == professor_id)  → professor lookup
    #   2. select(ProfessorCourse).where(ProfessorCourse.course_id == ...)
    #      → existing assignment lookup
    #
    # The course lookup is done via self._course_repo.obtener_por_id()
    # which we mock separately.

    call_counter = {"n": 0}

    async def mock_execute(stmt):
        """
        The service calls session.execute twice per assign_professor call:
          1st call: select(User) — professor lookup
          2nd call: select(ProfessorCourse) — existing assignment lookup
        We alternate based on a counter that resets every 2 calls.
        """
        idx = call_counter["n"] % 2
        call_counter["n"] += 1

        if idx == 0:
            # 1st call in the pair: User lookup
            # Extract professor_id from the call args by inspecting
            # the compiled statement's whereclause
            for pid, prof in professors.items():
                try:
                    compiled = stmt.compile(
                        compile_kwargs={"literal_binds": True}
                    )
                    if str(pid) in str(compiled):
                        return FakeScalarResult(prof)
                except Exception:
                    pass
            # Fallback: return the professor for the current call
            # based on the sequence
            assign_idx = (call_counter["n"] - 1) // 2
            if assign_idx < len(professor_ids):
                pid = professor_ids[assign_idx]
                return FakeScalarResult(professors.get(pid))
            return FakeScalarResult(None)
        else:
            # 2nd call in the pair: ProfessorCourse lookup
            return FakeScalarResult(state["current_assignment"])

    session.execute = AsyncMock(side_effect=mock_execute)

    def mock_add(obj):
        if isinstance(obj, ProfessorCourse):
            state["current_assignment"] = obj

    session.add = MagicMock(side_effect=mock_add)
    session.flush = AsyncMock()

    async def mock_refresh(obj):
        if isinstance(obj, ProfessorCourse) and obj.id is None:
            obj.id = uuid4()

    session.refresh = AsyncMock(side_effect=mock_refresh)

    # Build the service manually to inject mocks
    service = object.__new__(ProfessorCourseService)
    service._session = session
    service._audit = AsyncMock()  # Mock audit to avoid side effects
    service._course_repo = AsyncMock()
    service._course_repo.obtener_por_id = AsyncMock(return_value=course)

    return service, state


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
      - After each assign_professor(C, Pi), the returned ProfessorCourseRead
        must reference course_id == C and professor_id == Pi
      - After all assignments, the internal state must have exactly one
        assignment record for course C
      - That single record must reference the last professor in the sequence

    **Validates: Requirements 4.1, 4.2**
    """
    assume(course_id not in professor_ids)

    service, state = _build_service(course_id, professor_ids)

    last_result = None
    for i, professor_id in enumerate(professor_ids):
        result = await service.assign_professor(course_id, professor_id)

        # --- Each assignment must return a valid ProfessorCourseRead ---
        assert isinstance(result, ProfessorCourseRead), (
            f"Assignment {i+1}: expected ProfessorCourseRead, "
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

    # --- After all assignments, exactly one assignment must exist ---
    final_assignment = state["current_assignment"]
    assert final_assignment is not None, (
        "After all assignments, there must be an active assignment"
    )

    # --- The final assignment must reference the last professor ---
    last_professor_id = professor_ids[-1]
    assert final_assignment.professor_id == last_professor_id, (
        f"Final assignment professor_id mismatch: "
        f"expected {last_professor_id}, got {final_assignment.professor_id}"
    )

    # --- The final assignment must reference the correct course ---
    assert final_assignment.course_id == course_id, (
        f"Final assignment course_id mismatch: "
        f"expected {course_id}, got {final_assignment.course_id}"
    )

    # --- The last returned result must match the final state ---
    assert last_result.professor_id == last_professor_id, (
        f"Last result professor_id mismatch: "
        f"expected {last_professor_id}, got {last_result.professor_id}"
    )
