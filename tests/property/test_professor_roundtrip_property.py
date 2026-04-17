# Feature: multi-university-support, Property 11: Round-trip de asignación profesor-curso
"""
Property-based test for professor-course assignment round-trip.

Verifies that for any professor P assigned to a course C:
  - GET /courses/{C.id}/professor returns P's data (UserRead)
  - GET /professors/{P.id}/courses includes C in the list (CourseRead)

**Validates: Requirements 4.5, 4.6**
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4, UUID

import pytest
from hypothesis import given, settings as h_settings, HealthCheck, assume
from hypothesis import strategies as st

from app.application.schemas.course import CourseRead
from app.application.schemas.professor_course import ProfessorCourseRead
from app.application.schemas.user import UserRead
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
program_id_strategy = st.uuids()

course_name_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "Zs")),
    min_size=1,
    max_size=100,
).filter(lambda s: s.strip())

course_code_strategy = st.from_regex(r"[A-Z]{2,4}-[0-9]{3,6}", fullmatch=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_professor_user(professor_id: UUID) -> User:
    """Create a User ORM object with PROFESSOR role."""
    now = datetime.now(timezone.utc)
    return User(
        id=professor_id,
        email=f"prof-{professor_id}@test.edu",
        full_name=f"Professor {professor_id}",
        role=RoleEnum.PROFESSOR,
        status=UserStatusEnum.ACTIVE,
        ml_consent=False,
        created_at=now,
        updated_at=now,
    )


def _make_course(course_id: UUID, program_id: UUID, code: str, name: str) -> Course:
    """Create a Course ORM object."""
    return Course(
        id=course_id,
        code=code,
        name=name,
        credits=3,
        academic_period="2026-1",
        program_id=program_id,
        created_at=datetime.now(timezone.utc),
    )


def _build_service_for_roundtrip(
    professor: User,
    course: Course,
):
    """
    Build a ProfessorCourseService with a mocked session that simulates:
      1. assign_professor: creates a ProfessorCourse record
      2. get_course_professor: returns the professor User via JOIN
      3. list_professor_courses: returns the course via CourseRepository

    Returns (service, state_dict) where state_dict tracks the assignment.
    """
    session = AsyncMock()
    state = {"assignment": None}

    # --- Mock session.execute for different query patterns ---

    class FakeScalarResult:
        def __init__(self, value):
            self._value = value

        def scalar_one_or_none(self):
            return self._value

    class FakeScalarsResult:
        def __init__(self, values):
            self._values = values

        def all(self):
            return self._values

    class FakeScalarsWrapper:
        def __init__(self, values):
            self._values = values

        def scalars(self):
            return FakeScalarsResult(self._values)

    # Phase tracking: which operation is being performed
    phase = {"current": "assign", "assign_call": 0}

    async def mock_execute(stmt):
        compiled_str = ""
        try:
            compiled = stmt.compile(compile_kwargs={"literal_binds": True})
            compiled_str = str(compiled)
        except Exception:
            compiled_str = str(stmt)

        if phase["current"] == "assign":
            # assign_professor issues 2 queries:
            #   1st: select(User) — professor lookup
            #   2nd: select(ProfessorCourse) — existing assignment lookup
            idx = phase["assign_call"] % 2
            phase["assign_call"] += 1

            if idx == 0:
                # User lookup
                return FakeScalarResult(professor)
            else:
                # ProfessorCourse lookup — no existing assignment
                return FakeScalarResult(state["assignment"])

        elif phase["current"] == "get_professor":
            # get_course_professor: JOIN User + ProfessorCourse
            if state["assignment"] is not None:
                return FakeScalarResult(professor)
            return FakeScalarResult(None)

        elif phase["current"] == "list_courses":
            # list_professor_courses delegates to CourseRepository.listar_por_docente
            # which does a JOIN Course + ProfessorCourse
            if state["assignment"] is not None:
                return FakeScalarsWrapper([course])
            return FakeScalarsWrapper([])

        return FakeScalarResult(None)

    session.execute = AsyncMock(side_effect=mock_execute)

    def mock_add(obj):
        if isinstance(obj, ProfessorCourse):
            state["assignment"] = obj

    session.add = MagicMock(side_effect=mock_add)
    session.flush = AsyncMock()

    async def mock_refresh(obj):
        if isinstance(obj, ProfessorCourse) and obj.id is None:
            obj.id = uuid4()

    session.refresh = AsyncMock(side_effect=mock_refresh)

    # Build the service with injected mocks
    service = object.__new__(ProfessorCourseService)
    service._session = session
    service._audit = AsyncMock()
    service._audit.register = AsyncMock()
    service._course_repo = AsyncMock()
    service._course_repo.obtener_por_id = AsyncMock(return_value=course)

    # For list_professor_courses, the service delegates to _course_repo.listar_por_docente
    async def mock_listar_por_docente(docente_id):
        if state["assignment"] is not None and state["assignment"].professor_id == docente_id:
            return [course]
        return []

    service._course_repo.listar_por_docente = AsyncMock(side_effect=mock_listar_por_docente)

    return service, state, phase


# ---------------------------------------------------------------------------
# Property test
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@h_settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(
    professor_id=professor_id_strategy,
    course_id=course_id_strategy,
    program_id=program_id_strategy,
    course_code=course_code_strategy,
    course_name=course_name_strategy,
)
async def test_professor_course_assignment_roundtrip(
    professor_id: UUID,
    course_id: UUID,
    program_id: UUID,
    course_code: str,
    course_name: str,
):
    """
    Property 11: Round-trip de asignación profesor-curso.

    For any professor P assigned to a course C:
      1. assign_professor(C, P) succeeds and returns a ProfessorCourseRead
         referencing both C and P
      2. get_course_professor(C) returns a UserRead matching P's data
      3. list_professor_courses(P) returns a list containing C

    This verifies the bidirectional consistency of the assignment:
    the write path (assign) and both read paths (get professor for course,
    list courses for professor) agree on the state.

    **Validates: Requirements 4.5, 4.6**
    """
    # Ensure IDs don't collide
    assume(professor_id != course_id)
    assume(professor_id != program_id)
    assume(course_id != program_id)

    professor = _make_professor_user(professor_id)
    course = _make_course(course_id, program_id, course_code, course_name)

    service, state, phase = _build_service_for_roundtrip(professor, course)

    # --- Step 1: Assign professor to course ---
    phase["current"] = "assign"
    assignment_result = await service.assign_professor(course_id, professor_id)

    assert isinstance(assignment_result, ProfessorCourseRead), (
        f"Expected ProfessorCourseRead, got {type(assignment_result).__name__}"
    )
    assert assignment_result.course_id == course_id, (
        f"Assignment course_id mismatch: expected {course_id}, "
        f"got {assignment_result.course_id}"
    )
    assert assignment_result.professor_id == professor_id, (
        f"Assignment professor_id mismatch: expected {professor_id}, "
        f"got {assignment_result.professor_id}"
    )
    assert assignment_result.id is not None, "Assignment id must not be None"

    # --- Step 2: GET professor for course (Req 4.5) ---
    phase["current"] = "get_professor"
    professor_result = await service.get_course_professor(course_id)

    assert isinstance(professor_result, UserRead), (
        f"Expected UserRead, got {type(professor_result).__name__}"
    )
    assert professor_result.id == professor_id, (
        f"get_course_professor returned wrong professor: "
        f"expected {professor_id}, got {professor_result.id}"
    )
    assert professor_result.role == RoleEnum.PROFESSOR, (
        f"Returned user must have PROFESSOR role, got {professor_result.role}"
    )
    assert professor_result.email == professor.email, (
        f"Professor email mismatch: expected {professor.email}, "
        f"got {professor_result.email}"
    )
    assert professor_result.full_name == professor.full_name, (
        f"Professor full_name mismatch: expected {professor.full_name}, "
        f"got {professor_result.full_name}"
    )

    # --- Step 3: GET courses for professor (Req 4.6) ---
    phase["current"] = "list_courses"
    courses_result = await service.list_professor_courses(professor_id)

    assert isinstance(courses_result, list), (
        f"Expected list, got {type(courses_result).__name__}"
    )
    assert len(courses_result) >= 1, (
        f"Professor must have at least 1 course assigned, got {len(courses_result)}"
    )

    # Find the assigned course in the list
    matching_courses = [c for c in courses_result if c.id == course_id]
    assert len(matching_courses) == 1, (
        f"Expected exactly 1 course with id {course_id} in professor's courses, "
        f"found {len(matching_courses)}"
    )

    matched_course = matching_courses[0]
    assert isinstance(matched_course, CourseRead), (
        f"Expected CourseRead, got {type(matched_course).__name__}"
    )
    assert matched_course.code == course_code, (
        f"Course code mismatch: expected {course_code}, got {matched_course.code}"
    )
    assert matched_course.name == course_name, (
        f"Course name mismatch: expected {course_name}, got {matched_course.name}"
    )
