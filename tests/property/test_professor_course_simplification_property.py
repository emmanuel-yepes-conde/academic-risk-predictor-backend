# Feature: professor-course-simplification, Property 1: Idempotencia de asignación
"""
Property-based test for idempotent professor assignment — last professor wins.

For any course C and any sequence of valid professors [P1, P2, ..., Pn] assigned
sequentially to C, after all assignments Course.professor_id must equal Pn (the
last professor assigned), and each intermediate assignment must return a response
with the correct professor_id and course_id.

**Validates: Requirements 4.1, 4.2**
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4, UUID

import pytest
from hypothesis import given, settings as h_settings, HealthCheck, assume
from hypothesis import strategies as st

from app.application.schemas.course import CourseRead
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
    """Create a Course ORM object with no professor assigned."""
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
async def test_idempotent_assignment_last_professor_wins(
    course_id: UUID,
    professor_ids: list[UUID],
):
    """
    Property 1: Idempotencia de asignación — el último profesor gana.

    For any course C, if we sequentially assign professors P1, P2, ..., Pn
    to C, the final state must be that Course.professor_id == Pn.
    Each intermediate assignment must return a ProfessorAssignmentRead with
    the correct professor_id and course_id.

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


# Feature: professor-course-simplification, Property 2: Round-trip de asignación
# ---------------------------------------------------------------------------
# Property-based test for professor-course assignment round-trip consistency.
#
# For any professor P assigned to a course C:
#   1. assign_professor(C, P) returns ProfessorAssignmentRead with
#      professor_id == P and course_id == C
#   2. get_course_professor(C) returns UserRead with id == P
#   3. list_professor_courses(P) returns a list containing C
#
# **Validates: Requirements 5.1, 5.3, 5.4, 7.6**
# ---------------------------------------------------------------------------

from datetime import datetime, timezone

from app.application.schemas.course import CourseRead
from app.application.schemas.user import UserRead

# Strategies for round-trip test
_rt_professor_id_strategy = st.uuids()
_rt_course_id_strategy = st.uuids()
_rt_program_id_strategy = st.uuids()
_rt_course_code_strategy = st.from_regex(r"[A-Z]{2,4}-[0-9]{3,6}", fullmatch=True)
_rt_course_name_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "Zs")),
    min_size=1,
    max_size=100,
).filter(lambda s: s.strip())


# ---------------------------------------------------------------------------
# Helpers for round-trip test
# ---------------------------------------------------------------------------


def _make_professor_user_rt(professor_id: UUID) -> User:
    """Create a User ORM object with PROFESSOR role for round-trip test."""
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


def _make_course_rt(
    course_id: UUID, program_id: UUID, code: str, name: str
) -> Course:
    """Create a Course ORM object for round-trip test."""
    return Course(
        id=course_id,
        subject_id=program_id,
        section=code[:8],
        academic_period="2026-1",
        professor_id=None,
        created_at=datetime.now(timezone.utc),
    )


def _build_service_for_roundtrip_rt(professor: User, course: Course):
    """
    Build a ProfessorCourseService with mocked dependencies that simulates:
      1. assign_professor: updates course.professor_id directly
      2. get_course_professor: returns the professor User via course.professor_id
      3. list_professor_courses: returns the course via CourseRepository

    Returns (service, phase) where phase tracks the current operation.
    """
    session = AsyncMock()

    class FakeScalarResult:
        def __init__(self, value):
            self._value = value

        def scalar_one_or_none(self):
            return self._value

    phase = {"current": "assign"}

    async def mock_execute(stmt):
        try:
            compiled_str = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        except Exception:
            compiled_str = str(stmt)
        if phase["current"] == "assign":
            if "courses" in compiled_str:
                return FakeScalarResult(course)
            return FakeScalarResult(professor)
        elif phase["current"] == "get_professor":
            if "courses" in compiled_str:
                return FakeScalarResult(course)
            # get_course_professor: select(User).where(User.id == course.professor_id)
            if course.professor_id is not None:
                return FakeScalarResult(professor)
            return FakeScalarResult(None)
        return FakeScalarResult(None)

    session.execute = AsyncMock(side_effect=mock_execute)
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()

    service = object.__new__(ProfessorCourseService)
    service._session = session
    service._audit = AsyncMock()
    service._audit.register = AsyncMock()
    service._course_repo = AsyncMock()
    service._course_repo.obtener_por_id = AsyncMock(return_value=course)

    async def mock_listar_por_docente(docente_id):
        if course.professor_id is not None and course.professor_id == docente_id:
            return [
                CourseRead(
                    id=course.id,
                    subject_id=course.subject_id,
                    section=course.section,
                    academic_period=course.academic_period,
                    professor_id=course.professor_id,
                    status=course.status,
                    created_at=course.created_at,
                    code="TST101",
                    name="Test Subject",
                    credits=3,
                    program_id=course.subject_id,
                )
            ]
        return []

    service._course_repo.listar_por_docente = AsyncMock(
        side_effect=mock_listar_por_docente
    )

    return service, phase


# ---------------------------------------------------------------------------
# Property test — Round-trip de asignación profesor-curso
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@h_settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(
    professor_id=_rt_professor_id_strategy,
    course_id=_rt_course_id_strategy,
    program_id=_rt_program_id_strategy,
    course_code=_rt_course_code_strategy,
    course_name=_rt_course_name_strategy,
)
async def test_assignment_roundtrip_consistency(
    professor_id: UUID,
    course_id: UUID,
    program_id: UUID,
    course_code: str,
    course_name: str,
):
    """
    Property 2: Round-trip de asignación profesor-curso.

    For any professor P assigned to a course C:
      1. assign_professor(C, P) returns ProfessorAssignmentRead with
         professor_id == P and course_id == C
      2. get_course_professor(C) returns UserRead with id == P
      3. list_professor_courses(P) returns a list containing C

    The three views of the state must be consistent with each other.

    **Validates: Requirements 5.1, 5.3, 5.4, 7.6**
    """
    # Ensure IDs don't collide
    assume(professor_id != course_id)
    assume(professor_id != program_id)
    assume(course_id != program_id)

    professor = _make_professor_user_rt(professor_id)
    course = _make_course_rt(course_id, program_id, course_code, course_name)

    service, phase = _build_service_for_roundtrip_rt(professor, course)

    # --- Step 1: Assign professor to course ---
    phase["current"] = "assign"
    assignment_result = await service.assign_professor(course_id, professor_id)

    assert isinstance(assignment_result, ProfessorAssignmentRead), (
        f"Expected ProfessorAssignmentRead, got {type(assignment_result).__name__}"
    )
    assert assignment_result.professor_id == professor_id, (
        f"Assignment professor_id mismatch: expected {professor_id}, "
        f"got {assignment_result.professor_id}"
    )
    assert assignment_result.course_id == course_id, (
        f"Assignment course_id mismatch: expected {course_id}, "
        f"got {assignment_result.course_id}"
    )
    assert assignment_result.id is not None, "Assignment id must not be None"

    # --- Step 2: get_course_professor returns UserRead with id == P (Req 5.1) ---
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

    # --- Step 3: list_professor_courses(P) contains C (Req 5.3, 5.4) ---
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
    assert matched_course.professor_id == professor_id, (
        f"CourseRead.professor_id mismatch: expected {professor_id}, "
        f"got {matched_course.professor_id}"
    )


# Feature: professor-course-simplification, Property 3: Validación de rol
# ---------------------------------------------------------------------------
# Property-based test for role validation — non-professor users are rejected.
#
# For any user that does NOT have the PROFESSOR role (including nonexistent
# users), attempting to assign them to any course must result in HTTP 422,
# and the course's professor_id must remain unchanged.
#
# **Validates: Requirements 4.3**
# ---------------------------------------------------------------------------

from fastapi import HTTPException

# Strategies for role validation test
_rv_non_professor_roles = st.sampled_from([RoleEnum.STUDENT, RoleEnum.ADMIN])


# ---------------------------------------------------------------------------
# Helpers for role validation test
# ---------------------------------------------------------------------------


def _make_non_professor_user(user_id: UUID, role: RoleEnum) -> User:
    """Create a User ORM object with a non-PROFESSOR role."""
    return User(
        id=user_id,
        email=f"user-{user_id}@test.edu",
        full_name=f"User {user_id}",
        role=role,
        status=UserStatusEnum.ACTIVE,
    )


def _build_service_for_role_validation(
    course_id: UUID,
    user: User | None,
    initial_professor_id: UUID | None = None,
):
    """
    Build a ProfessorCourseService with mocked session that simulates:
      - A course that exists (with optional initial professor_id)
      - A user lookup that returns `user` (or None for nonexistent user)

    Returns (service, course).
    """
    session = AsyncMock()

    course = _make_course(course_id)
    course.professor_id = initial_professor_id

    class FakeScalarResult:
        def __init__(self, value):
            self._value = value

        def scalar_one_or_none(self):
            return self._value

    async def mock_execute(stmt):
        """Return the user for the User lookup query."""
        return FakeScalarResult(user)

    session.execute = AsyncMock(side_effect=mock_execute)
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()

    service = object.__new__(ProfessorCourseService)
    service._session = session
    service._audit = AsyncMock()
    service._audit.register = AsyncMock()
    service._course_repo = AsyncMock()
    service._course_repo.obtener_por_id = AsyncMock(return_value=course)

    return service, course


# ---------------------------------------------------------------------------
# Property test — Validación de rol: usuarios no-profesor son rechazados
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@h_settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(
    course_id=st.uuids(),
    user_id=st.uuids(),
    non_professor_role=_rv_non_professor_roles,
    initial_professor_id=st.one_of(st.none(), st.uuids()),
)
async def test_non_professor_role_rejected_with_422(
    course_id: UUID,
    user_id: UUID,
    non_professor_role: RoleEnum,
    initial_professor_id: UUID | None,
):
    """
    Property 3: Validación de rol — usuarios no-profesor son rechazados.

    For any user with role STUDENT or ADMIN, attempting to assign them to
    any course must raise HTTPException with status_code 422, and the
    course's professor_id must remain unchanged.

    **Validates: Requirements 4.3**
    """
    assume(course_id != user_id)

    user = _make_non_professor_user(user_id, non_professor_role)
    service, course = _build_service_for_role_validation(
        course_id, user, initial_professor_id
    )

    original_professor_id = course.professor_id

    with pytest.raises(HTTPException) as exc_info:
        await service.assign_professor(course_id, user_id)

    # --- Must raise HTTP 422 ---
    assert exc_info.value.status_code == 422, (
        f"Expected status_code 422, got {exc_info.value.status_code} "
        f"for user with role {non_professor_role}"
    )

    # --- Course.professor_id must remain unchanged ---
    assert course.professor_id == original_professor_id, (
        f"Course.professor_id changed from {original_professor_id} to "
        f"{course.professor_id} after rejected assignment of "
        f"{non_professor_role} user"
    )


@pytest.mark.anyio
@h_settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(
    course_id=st.uuids(),
    nonexistent_user_id=st.uuids(),
    initial_professor_id=st.one_of(st.none(), st.uuids()),
)
async def test_nonexistent_user_rejected_with_422(
    course_id: UUID,
    nonexistent_user_id: UUID,
    initial_professor_id: UUID | None,
):
    """
    Property 3: Validación de rol — usuarios inexistentes son rechazados.

    For any nonexistent user UUID, attempting to assign them to any course
    must raise HTTPException with status_code 422, and the course's
    professor_id must remain unchanged.

    **Validates: Requirements 4.3**
    """
    assume(course_id != nonexistent_user_id)

    # user=None simulates a nonexistent user (not found in DB)
    service, course = _build_service_for_role_validation(
        course_id, None, initial_professor_id
    )

    original_professor_id = course.professor_id

    with pytest.raises(HTTPException) as exc_info:
        await service.assign_professor(course_id, nonexistent_user_id)

    # --- Must raise HTTP 422 ---
    assert exc_info.value.status_code == 422, (
        f"Expected status_code 422, got {exc_info.value.status_code} "
        f"for nonexistent user {nonexistent_user_id}"
    )

    # --- Course.professor_id must remain unchanged ---
    assert course.professor_id == original_professor_id, (
        f"Course.professor_id changed from {original_professor_id} to "
        f"{course.professor_id} after rejected assignment of "
        f"nonexistent user"
    )


# Feature: professor-course-simplification, Property 4: Control de acceso RB-04
# ---------------------------------------------------------------------------
# Property-based test for RB-04 access control — access conditioned on
# Course.professor_id.
#
# For any pair (professor, course), access to the course's student list is
# granted if and only if Course.professor_id matches the professor's ID.
# If it does not match, the service returns HTTP 403.
#
# **Validates: Requirements 6.1, 6.2, 6.3**
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Helpers for RB-04 access control test
# ---------------------------------------------------------------------------


def _make_student_rb04(student_id: UUID) -> User:
    """Create a User ORM object with STUDENT role for RB-04 test."""
    now = datetime.now(timezone.utc)
    return User(
        id=student_id,
        email=f"student-{student_id}@test.edu",
        full_name=f"Student {student_id}",
        role=RoleEnum.STUDENT,
        status=UserStatusEnum.ACTIVE,
        ml_consent=False,
        created_at=now,
        updated_at=now,
    )


def _build_service_for_rb04(
    professor_id: UUID,
    assigned_course_ids: set[UUID],
    students_by_course: dict[UUID, list[User]],
):
    """
    Build a ProfessorCourseService with mocked dependencies for RB-04 testing.

    The service's list_course_students flow:
      1. verify_professor_assigned_to_course → _course_repo.obtener_por_id(course_id)
         → checks course.professor_id == professor_id, raises 403 if not
      2. _course_repo.listar_estudiantes_inscritos(course_id)

    We mock _course_repo.obtener_por_id to return a Course with professor_id
    set when the course is in assigned_course_ids.
    """
    session = AsyncMock()

    async def mock_obtener_por_id(course_id):
        if course_id in assigned_course_ids:
            return Course(
                id=course_id,
                code=f"COURSE-{course_id}",
                name=f"Course {course_id}",
                credits=3,
                academic_period="2026-1",
                program_id=uuid4(),
                professor_id=professor_id,
            )
        else:
            # Course exists but professor is NOT assigned
            return Course(
                id=course_id,
                code=f"COURSE-{course_id}",
                name=f"Course {course_id}",
                credits=3,
                academic_period="2026-1",
                program_id=uuid4(),
                professor_id=None,
            )

    service = object.__new__(ProfessorCourseService)
    service._session = session
    service._audit = AsyncMock()
    service._audit.register = AsyncMock()
    service._course_repo = AsyncMock()
    service._course_repo.obtener_por_id = AsyncMock(side_effect=mock_obtener_por_id)

    async def mock_listar_estudiantes(course_id):
        return students_by_course.get(course_id, [])

    service._course_repo.listar_estudiantes_inscritos = AsyncMock(
        side_effect=mock_listar_estudiantes
    )

    return service


# ---------------------------------------------------------------------------
# Property test — Control de acceso RB-04
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@h_settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(
    professor_id=st.uuids(),
    assigned_course_ids=st.lists(
        st.uuids(), min_size=1, max_size=3, unique=True,
    ),
    unassigned_course_ids=st.lists(
        st.uuids(), min_size=1, max_size=3, unique=True,
    ),
    students_per_course=st.integers(min_value=1, max_value=3),
)
async def test_rb04_access_control_via_course_professor_id(
    professor_id: UUID,
    assigned_course_ids: list[UUID],
    unassigned_course_ids: list[UUID],
    students_per_course: int,
):
    """
    Property 4: Control de acceso RB-04 — acceso condicionado a Course.professor_id.

    For any professor P:
      - For each course C where Course.professor_id == P (assigned),
        list_course_students(C, P) must succeed and return UserRead objects.
      - For each course C where Course.professor_id != P (unassigned),
        list_course_students(C, P) must raise HTTPException with status_code 403.

    **Validates: Requirements 6.1, 6.2, 6.3**
    """
    # Ensure no overlap between assigned and unassigned course IDs, and professor_id
    all_ids = set(assigned_course_ids + unassigned_course_ids + [professor_id])
    assume(len(all_ids) == len(assigned_course_ids) + len(unassigned_course_ids) + 1)

    # Generate students for each course
    students_by_course: dict[UUID, list[User]] = {}
    for cid in assigned_course_ids + unassigned_course_ids:
        students_by_course[cid] = [
            _make_student_rb04(uuid4()) for _ in range(students_per_course)
        ]

    assigned_set = set(assigned_course_ids)

    service = _build_service_for_rb04(professor_id, assigned_set, students_by_course)

    # --- Positive path: professor IS assigned → access granted (Req 6.1) ---
    for cid in assigned_course_ids:
        result = await service.list_course_students(cid, professor_id)

        assert isinstance(result, list), (
            f"Expected list for assigned course {cid}, "
            f"got {type(result).__name__}"
        )
        assert len(result) == students_per_course, (
            f"Expected {students_per_course} students for course {cid}, "
            f"got {len(result)}"
        )
        for student_read in result:
            assert isinstance(student_read, UserRead), (
                f"Expected UserRead, got {type(student_read).__name__}"
            )
            assert student_read.role == RoleEnum.STUDENT, (
                f"Expected STUDENT role, got {student_read.role}"
            )

    # --- Negative path: professor NOT assigned → 403 Forbidden (Req 6.2, 6.3) ---
    for cid in unassigned_course_ids:
        with pytest.raises(HTTPException) as exc_info:
            await service.list_course_students(cid, professor_id)

        assert exc_info.value.status_code == 403, (
            f"Expected 403 for unassigned course {cid}, "
            f"got {exc_info.value.status_code}"
        )


# Feature: professor-course-simplification, Property 5: Guarda de inscripción
# ---------------------------------------------------------------------------
# Property-based test for enrollment guard — grades denied for unenrolled students.
#
# For any student that is NOT enrolled in a course (no Enrollment record),
# attempting to write a grade for that student in that course must result in
# HTTP 403, even when the professor IS correctly assigned to the course.
#
# **Validates: Requirements 6.4**
# ---------------------------------------------------------------------------

from app.infrastructure.models.enrollment import Enrollment


# ---------------------------------------------------------------------------
# Strategies for enrollment guard test
# ---------------------------------------------------------------------------

_eg_grade_value_strategy = st.floats(
    min_value=0.0, max_value=5.0, allow_nan=False, allow_infinity=False,
)

_eg_grade_type_strategy = st.sampled_from(["asistencia", "seguimiento", "parcial_1"])


# ---------------------------------------------------------------------------
# Helpers for enrollment guard test
# ---------------------------------------------------------------------------


def _build_service_for_enrollment_guard(
    professor_id: UUID,
    course_id: UUID,
    enrolled_student_ids: set[UUID],
):
    """
    Build a ProfessorCourseService with mocked dependencies for enrollment
    guard testing.

    The write_grade flow:
      1. verify_professor_assigned_to_course → _course_repo.obtener_por_id
         → checks course.professor_id == professor_id (PASSES here)
      2. session.execute(select(Enrollment)...) → checks student enrollment
         → returns None for unenrolled students → HTTPException(403)
      3. audit.register(...) → logs the operation (only if enrollment found)

    The professor IS assigned to the course, so step 1 always passes.
    Step 2 is the guard under test.
    """
    session = AsyncMock()

    # Course with professor correctly assigned
    course = Course(
        id=course_id,
        code=f"COURSE-{course_id}",
        name=f"Course {course_id}",
        credits=3,
        academic_period="2026-1",
        program_id=uuid4(),
        professor_id=professor_id,
    )

    class FakeScalarResult:
        def __init__(self, value):
            self._value = value

        def scalar_one_or_none(self):
            return self._value

    async def mock_execute(stmt):
        """
        Intercept session.execute calls for Enrollment lookups.
        Returns an Enrollment only if the student_id is in enrolled_student_ids.
        """
        try:
            compiled = stmt.compile()
            params = compiled.params
        except Exception:
            params = {}

        # Look for student_id in the query parameters
        bound_student_id = None
        for key, value in params.items():
            if "student_id" in key:
                bound_student_id = value
                break

        bound_course_id = None
        for key, value in params.items():
            if "course_id" in key:
                bound_course_id = value
                break

        if bound_student_id is not None:
            # This is an Enrollment lookup
            if bound_student_id in enrolled_student_ids:
                return FakeScalarResult(
                    Enrollment(
                        id=uuid4(),
                        student_id=bound_student_id,
                        course_id=bound_course_id or course_id,
                    )
                )
            return FakeScalarResult(None)

        return FakeScalarResult(None)

    session.execute = AsyncMock(side_effect=mock_execute)

    service = object.__new__(ProfessorCourseService)
    service._session = session
    service._audit = AsyncMock()
    service._audit.register = AsyncMock()
    service._course_repo = AsyncMock()
    service._course_repo.obtener_por_id = AsyncMock(return_value=course)

    return service


# ---------------------------------------------------------------------------
# Property test — Enrollment guard: grades denied for unenrolled students
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@h_settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(
    professor_id=st.uuids(),
    course_id=st.uuids(),
    unenrolled_student_id=st.uuids(),
    grade_value=_eg_grade_value_strategy,
    grade_type=_eg_grade_type_strategy,
)
async def test_enrollment_guard_denies_grade_for_unenrolled_student(
    professor_id: UUID,
    course_id: UUID,
    unenrolled_student_id: UUID,
    grade_value: float,
    grade_type: str,
):
    """
    Property 5: Guarda de inscripción — notas denegadas para estudiantes no inscritos.

    For any (professor, course, student) triple where:
      - The professor IS assigned to the course (Course.professor_id == professor_id)
      - The student is NOT enrolled in the course (no Enrollment record)

    Calling write_grade(professor_id, course_id, student_id, grade_data) must
    raise HTTPException with status_code 403 and a message containing
    "no está inscrito".

    This verifies that the enrollment guard is enforced independently of the
    professor assignment check — even a correctly assigned professor cannot
    write grades for students who are not enrolled.

    **Validates: Requirements 6.4**
    """
    # Ensure no ID collisions
    assume(len({professor_id, course_id, unenrolled_student_id}) == 3)

    # No students are enrolled — the unenrolled_student_id has no Enrollment
    enrolled_student_ids: set[UUID] = set()

    service = _build_service_for_enrollment_guard(
        professor_id, course_id, enrolled_student_ids
    )

    grade_data = {"type": grade_type, "value": grade_value}

    with pytest.raises(HTTPException) as exc_info:
        await service.write_grade(
            professor_id=professor_id,
            course_id=course_id,
            student_id=unenrolled_student_id,
            grade_data=grade_data,
        )

    # --- Must raise HTTP 403 ---
    assert exc_info.value.status_code == 403, (
        f"Expected 403 for unenrolled student {unenrolled_student_id}, "
        f"got {exc_info.value.status_code}"
    )

    # --- Detail must mention "no está inscrito" ---
    assert "no está inscrito" in exc_info.value.detail, (
        f"Expected 'no está inscrito' in detail, "
        f"got: {exc_info.value.detail}"
    )


# Feature: professor-course-simplification, Property 6: Correctitud del audit trail
# ---------------------------------------------------------------------------
# Property-based test for audit trail correctness — operations reference
# table "courses".
#
# For any professor assignment operation:
#   - If the course had NO previous professor (professor_id was None):
#     audit.register is called with table_name="courses", operation=INSERT,
#     new_data containing professor_id and course_id.
#   - If the course already HAD a professor (professor_id was not None):
#     audit.register is called with table_name="courses", operation=UPDATE,
#     previous_data containing the old professor_id,
#     new_data containing the new professor_id and course_id.
#
# **Validates: Requirements 4.5, 8.1, 8.2, 8.3**
# ---------------------------------------------------------------------------

from app.application.schemas.audit_log import AuditLogCreate
from app.domain.enums import OperationEnum


def _build_service_for_audit(
    course_id: UUID,
    professor_ids: list[UUID],
    initial_professor_id: UUID | None = None,
):
    """
    Build a ProfessorCourseService with mocked dependencies for audit trail
    testing.

    The service assigns professors sequentially. The audit mock captures
    every call to audit.register so we can inspect the AuditLogCreate
    payloads afterwards.

    Returns (service, course, audit_mock) where audit_mock.register is an
    AsyncMock whose call_args_list contains the AuditLogCreate objects.
    """
    session = AsyncMock()

    course = _make_course(course_id)
    course.professor_id = initial_professor_id

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

        for _key, value in params.items():
            if value in professors:
                return FakeScalarResult(professors[value])

        return FakeScalarResult(None)

    session.execute = AsyncMock(side_effect=mock_execute)
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()

    audit_mock = AsyncMock()
    audit_mock.register = AsyncMock()

    service = object.__new__(ProfessorCourseService)
    service._session = session
    service._audit = audit_mock
    service._course_repo = AsyncMock()
    service._course_repo.obtener_por_id = AsyncMock(return_value=course)

    return service, course, audit_mock


# ---------------------------------------------------------------------------
# Property test — Audit trail correctness
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@h_settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(
    course_id=st.uuids(),
    professor_ids=st.lists(
        st.uuids(), min_size=1, max_size=3, unique=True,
    ),
)
async def test_audit_trail_correctness_for_professor_assignment(
    course_id: UUID,
    professor_ids: list[UUID],
):
    """
    Property 6: Correctitud del audit trail — operaciones referencian tabla "courses".

    For any sequence of professor assignments to a course:
      - The FIRST assignment (course had no professor, professor_id was None)
        must produce an audit log entry with:
          table_name="courses", operation=INSERT,
          new_data={"professor_id": str(P), "course_id": str(C)}
      - Each SUBSEQUENT assignment (replacing an existing professor) must
        produce an audit log entry with:
          table_name="courses", operation=UPDATE,
          previous_data={"professor_id": str(old_P)},
          new_data={"professor_id": str(new_P), "course_id": str(C)}

    **Validates: Requirements 4.5, 8.1, 8.2, 8.3**
    """
    assume(course_id not in professor_ids)

    service, course, audit_mock = _build_service_for_audit(
        course_id, professor_ids, initial_professor_id=None,
    )

    for i, professor_id in enumerate(professor_ids):
        await service.assign_professor(course_id, professor_id)

    # --- Verify audit.register was called once per assignment ---
    assert audit_mock.register.call_count == len(professor_ids), (
        f"Expected {len(professor_ids)} audit calls, "
        f"got {audit_mock.register.call_count}"
    )

    for i, call in enumerate(audit_mock.register.call_args_list):
        # Extract the AuditLogCreate from the positional arg
        audit_entry: AuditLogCreate = call.args[0]
        assigned_pid = professor_ids[i]

        # --- table_name must always be "courses" (Req 8.1, 8.2) ---
        assert audit_entry.table_name == "courses", (
            f"Call {i}: expected table_name='courses', "
            f"got '{audit_entry.table_name}'"
        )

        if i == 0:
            # First assignment: INSERT (course had no professor)
            assert audit_entry.operation == OperationEnum.INSERT, (
                f"Call {i}: first assignment should be INSERT, "
                f"got {audit_entry.operation}"
            )
            # previous_data should be None for INSERT
            assert audit_entry.previous_data is None, (
                f"Call {i}: INSERT should have previous_data=None, "
                f"got {audit_entry.previous_data}"
            )
        else:
            # Subsequent assignments: UPDATE (replacing existing professor)
            assert audit_entry.operation == OperationEnum.UPDATE, (
                f"Call {i}: replacement should be UPDATE, "
                f"got {audit_entry.operation}"
            )
            # previous_data must contain the old professor_id
            previous_pid = professor_ids[i - 1]
            assert audit_entry.previous_data is not None, (
                f"Call {i}: UPDATE should have previous_data, got None"
            )
            assert audit_entry.previous_data.get("professor_id") == str(previous_pid), (
                f"Call {i}: previous_data professor_id mismatch: "
                f"expected {str(previous_pid)}, "
                f"got {audit_entry.previous_data.get('professor_id')}"
            )

        # --- new_data must contain professor_id and course_id (Req 8.3) ---
        assert audit_entry.new_data is not None, (
            f"Call {i}: new_data must not be None"
        )
        assert audit_entry.new_data.get("professor_id") == str(assigned_pid), (
            f"Call {i}: new_data professor_id mismatch: "
            f"expected {str(assigned_pid)}, "
            f"got {audit_entry.new_data.get('professor_id')}"
        )
        assert audit_entry.new_data.get("course_id") == str(course_id), (
            f"Call {i}: new_data course_id mismatch: "
            f"expected {str(course_id)}, "
            f"got {audit_entry.new_data.get('course_id')}"
        )
