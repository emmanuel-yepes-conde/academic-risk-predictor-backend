# Feature: multi-university-support, Property 12: RB-04 — Profesor solo ve estudiantes de sus cursos asignados
"""
Property-based test for RB-04 access control.

Verifies that for any professor P and any student S, P can access S's data
if and only if there exists at least one course C such that P is assigned to C
and S is enrolled in C. For any student S that does not satisfy this condition
with respect to P, any attempt by P to access S's data must return 403 Forbidden.

**Validates: Requirements 5.1, 5.3, 5.4**
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4, UUID

import pytest
from fastapi import HTTPException
from hypothesis import given, settings as h_settings, HealthCheck, assume
from hypothesis import strategies as st

from app.application.schemas.user import UserRead
from app.application.services.professor_course_service import ProfessorCourseService
from app.domain.enums import RoleEnum, UserStatusEnum
from app.infrastructure.models.professor_course import ProfessorCourse
from app.infrastructure.models.user import User


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

uuid_strategy = st.uuids()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_student(student_id: UUID) -> User:
    """Create a User ORM object with STUDENT role."""
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


def _build_service(
    professor_id: UUID,
    assigned_course_ids: set[UUID],
    students_by_course: dict[UUID, list[User]],
):
    """
    Build a ProfessorCourseService with mocked dependencies.

    The service's list_course_students flow:
      1. verify_professor_assigned_to_course → session.execute(select(ProfessorCourse)...)
      2. _course_repo.listar_estudiantes_inscritos(course_id)

    We mock session.execute to return a ProfessorCourse when the course is
    in assigned_course_ids, and None otherwise. The course_repo mock returns
    the students for the given course.
    """
    session = AsyncMock()

    class FakeScalarResult:
        def __init__(self, value):
            self._value = value

        def scalar_one_or_none(self):
            return self._value

    # The verify_professor_assigned_to_course method builds:
    #   select(ProfessorCourse).where(
    #       ProfessorCourse.course_id == course_id,
    #       ProfessorCourse.professor_id == professor_id,
    #   )
    # We inspect the statement's whereclause to extract the bound course_id.

    async def mock_execute(stmt):
        """
        Intercept session.execute calls for ProfessorCourse lookups.
        Extract the course_id from the WHERE clause bind parameters.
        """
        # Try to extract bind params from the compiled statement
        try:
            compiled = stmt.compile()
            params = compiled.params
        except Exception:
            params = {}

        # The WHERE clause binds course_id and professor_id as parameters.
        # SQLAlchemy names them like 'course_id_1', 'professor_id_1'.
        bound_course_id = None
        for key, value in params.items():
            if "course_id" in key:
                bound_course_id = value
                break

        if bound_course_id is not None and bound_course_id in assigned_course_ids:
            return FakeScalarResult(
                ProfessorCourse(
                    id=uuid4(),
                    professor_id=professor_id,
                    course_id=bound_course_id,
                )
            )
        return FakeScalarResult(None)

    session.execute = AsyncMock(side_effect=mock_execute)

    # Build the service with injected mocks
    service = object.__new__(ProfessorCourseService)
    service._session = session
    service._audit = AsyncMock()
    service._audit.register = AsyncMock()
    service._course_repo = AsyncMock()

    # Mock listar_estudiantes_inscritos on the course repo
    async def mock_listar_estudiantes(course_id):
        return students_by_course.get(course_id, [])

    service._course_repo.listar_estudiantes_inscritos = AsyncMock(
        side_effect=mock_listar_estudiantes
    )

    return service


# ---------------------------------------------------------------------------
# Property test
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@h_settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(
    professor_id=uuid_strategy,
    assigned_course_ids=st.lists(
        st.uuids(), min_size=1, max_size=3, unique=True,
    ),
    unassigned_course_ids=st.lists(
        st.uuids(), min_size=1, max_size=3, unique=True,
    ),
    students_per_course=st.integers(min_value=1, max_value=3),
)
async def test_rb04_professor_access_control(
    professor_id: UUID,
    assigned_course_ids: list[UUID],
    unassigned_course_ids: list[UUID],
    students_per_course: int,
):
    """
    Property 12: RB-04 — Profesor solo ve estudiantes de sus cursos asignados.

    For any professor P:
      - For each course C that P IS assigned to, list_course_students(C, P)
        must succeed and return the enrolled students as UserRead objects.
      - For each course C that P is NOT assigned to, list_course_students(C, P)
        must raise HTTPException with status_code 403.

    This verifies the bidirectional access control:
      - Positive path: assigned professor can see enrolled students (Req 5.1, 5.3)
      - Negative path: unassigned professor is denied access (Req 5.4)

    **Validates: Requirements 5.1, 5.3, 5.4**
    """
    # Ensure no overlap between assigned and unassigned course IDs, and professor_id
    all_ids = set(assigned_course_ids + unassigned_course_ids + [professor_id])
    assume(len(all_ids) == len(assigned_course_ids) + len(unassigned_course_ids) + 1)

    # Generate students for each course
    students_by_course: dict[UUID, list[User]] = {}
    for cid in assigned_course_ids + unassigned_course_ids:
        students_by_course[cid] = [
            _make_student(uuid4()) for _ in range(students_per_course)
        ]

    assigned_set = set(assigned_course_ids)

    service = _build_service(professor_id, assigned_set, students_by_course)

    # --- Positive path: professor IS assigned → can see students (Req 5.1, 5.3) ---
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

    # --- Negative path: professor is NOT assigned → 403 Forbidden (Req 5.4) ---
    for cid in unassigned_course_ids:
        with pytest.raises(HTTPException) as exc_info:
            await service.list_course_students(cid, professor_id)

        assert exc_info.value.status_code == 403, (
            f"Expected 403 for unassigned course {cid}, "
            f"got {exc_info.value.status_code}"
        )
