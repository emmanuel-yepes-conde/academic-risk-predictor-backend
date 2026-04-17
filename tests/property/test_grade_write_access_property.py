# Feature: multi-university-support, Property 13: Escritura de notas en curso no asignado retorna 403
"""
Property-based test for grade write access control.

Verifies that for any professor P and any course C to which P is NOT assigned,
any attempt by P to write grades on C must return 403 Forbidden.

Additionally verifies the positive path: when P IS assigned to C and the student
is enrolled, the grade write succeeds.

**Validates: Requirements 5.2**
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4, UUID

import pytest
from fastapi import HTTPException
from hypothesis import given, settings as h_settings, HealthCheck, assume
from hypothesis import strategies as st

from app.application.services.professor_course_service import ProfessorCourseService
from app.infrastructure.models.enrollment import Enrollment
from app.infrastructure.models.professor_course import ProfessorCourse


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

uuid_strategy = st.uuids()

grade_value_strategy = st.floats(
    min_value=0.0, max_value=5.0, allow_nan=False, allow_infinity=False,
)

grade_type_strategy = st.sampled_from(["asistencia", "seguimiento", "parcial_1"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_service(
    professor_id: UUID,
    assigned_course_ids: set[UUID],
    enrolled_students_by_course: dict[UUID, set[UUID]],
):
    """
    Build a ProfessorCourseService with mocked dependencies.

    The write_grade flow:
      1. verify_professor_assigned_to_course → session.execute(select(ProfessorCourse)...)
         → raises 403 if not assigned
      2. session.execute(select(Enrollment)...) → checks student enrollment
      3. audit.register(...) → logs the operation

    We mock session.execute to:
      - Return a ProfessorCourse when the course is in assigned_course_ids
        and the query is for ProfessorCourse
      - Return an Enrollment when the student is enrolled in the course
        and the query is for Enrollment
    """
    session = AsyncMock()

    class FakeScalarResult:
        def __init__(self, value):
            self._value = value

        def scalar_one_or_none(self):
            return self._value

    async def mock_execute(stmt):
        """
        Intercept session.execute calls.
        Distinguish between ProfessorCourse and Enrollment queries
        by inspecting the compiled statement's bind parameters.
        """
        try:
            compiled = stmt.compile()
            params = compiled.params
        except Exception:
            params = {}

        # Detect which table is being queried by checking parameter names
        has_professor_id_param = any("professor_id" in k for k in params)
        has_student_id_param = any("student_id" in k for k in params)

        bound_course_id = None
        for key, value in params.items():
            if "course_id" in key:
                bound_course_id = value
                break

        if has_student_id_param:
            # This is an Enrollment lookup
            bound_student_id = None
            for key, value in params.items():
                if "student_id" in key:
                    bound_student_id = value
                    break

            enrolled = enrolled_students_by_course.get(bound_course_id, set())
            if bound_student_id in enrolled:
                return FakeScalarResult(
                    Enrollment(
                        id=uuid4(),
                        student_id=bound_student_id,
                        course_id=bound_course_id,
                    )
                )
            return FakeScalarResult(None)

        elif has_professor_id_param and bound_course_id is not None:
            # This is a ProfessorCourse lookup
            if bound_course_id in assigned_course_ids:
                return FakeScalarResult(
                    ProfessorCourse(
                        id=uuid4(),
                        professor_id=professor_id,
                        course_id=bound_course_id,
                    )
                )
            return FakeScalarResult(None)

        return FakeScalarResult(None)

    session.execute = AsyncMock(side_effect=mock_execute)

    # Build the service with injected mocks
    service = object.__new__(ProfessorCourseService)
    service._session = session
    service._audit = AsyncMock()
    service._audit.register = AsyncMock()
    service._course_repo = AsyncMock()

    return service


# ---------------------------------------------------------------------------
# Property test — Negative path: unassigned professor gets 403
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@h_settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(
    professor_id=uuid_strategy,
    unassigned_course_ids=st.lists(
        st.uuids(), min_size=1, max_size=5, unique=True,
    ),
    student_id=uuid_strategy,
    grade_value=grade_value_strategy,
    grade_type=grade_type_strategy,
)
async def test_write_grade_unassigned_course_returns_403(
    professor_id: UUID,
    unassigned_course_ids: list[UUID],
    student_id: UUID,
    grade_value: float,
    grade_type: str,
):
    """
    Property 13: Escritura de notas en curso no asignado retorna 403.

    For any professor P and any course C to which P is NOT assigned,
    calling write_grade(P, C, student, grade_data) must raise
    HTTPException with status_code 403.

    The professor has NO assigned courses, so every course in
    unassigned_course_ids triggers the 403 path.

    **Validates: Requirements 5.2**
    """
    # Ensure no ID collisions
    all_ids = set(unassigned_course_ids + [professor_id, student_id])
    assume(len(all_ids) == len(unassigned_course_ids) + 2)

    # Professor has NO assigned courses
    assigned_course_ids: set[UUID] = set()

    # Even if students are enrolled, the professor check happens first
    enrolled_students: dict[UUID, set[UUID]] = {
        cid: {student_id} for cid in unassigned_course_ids
    }

    service = _build_service(professor_id, assigned_course_ids, enrolled_students)

    grade_data = {"type": grade_type, "value": grade_value}

    for cid in unassigned_course_ids:
        with pytest.raises(HTTPException) as exc_info:
            await service.write_grade(
                professor_id=professor_id,
                course_id=cid,
                student_id=student_id,
                grade_data=grade_data,
            )

        assert exc_info.value.status_code == 403, (
            f"Expected 403 for unassigned course {cid}, "
            f"got {exc_info.value.status_code}"
        )
        assert "No tiene permiso" in exc_info.value.detail, (
            f"Expected 'No tiene permiso' in detail, "
            f"got: {exc_info.value.detail}"
        )


# ---------------------------------------------------------------------------
# Property test — Positive path: assigned professor can write grades
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
    student_id=uuid_strategy,
    grade_value=grade_value_strategy,
    grade_type=grade_type_strategy,
)
async def test_write_grade_assigned_course_succeeds(
    professor_id: UUID,
    assigned_course_ids: list[UUID],
    student_id: UUID,
    grade_value: float,
    grade_type: str,
):
    """
    Positive counterpart to Property 13.

    For any professor P assigned to course C, with student S enrolled in C,
    calling write_grade(P, C, S, grade_data) must succeed and return a
    result dict with status "recorded".

    This confirms the access control boundary: assigned professors CAN write,
    unassigned professors CANNOT.

    **Validates: Requirements 5.2 (positive path)**
    """
    # Ensure no ID collisions
    all_ids = set(assigned_course_ids + [professor_id, student_id])
    assume(len(all_ids) == len(assigned_course_ids) + 2)

    assigned_set = set(assigned_course_ids)

    # Student is enrolled in all assigned courses
    enrolled_students: dict[UUID, set[UUID]] = {
        cid: {student_id} for cid in assigned_course_ids
    }

    service = _build_service(professor_id, assigned_set, enrolled_students)

    grade_data = {"type": grade_type, "value": grade_value}

    for cid in assigned_course_ids:
        result = await service.write_grade(
            professor_id=professor_id,
            course_id=cid,
            student_id=student_id,
            grade_data=grade_data,
        )

        assert isinstance(result, dict), (
            f"Expected dict result, got {type(result).__name__}"
        )
        assert result["status"] == "recorded", (
            f"Expected status 'recorded', got {result['status']}"
        )
        assert result["professor_id"] == str(professor_id), (
            f"Expected professor_id {professor_id}, got {result['professor_id']}"
        )
        assert result["course_id"] == str(cid), (
            f"Expected course_id {cid}, got {result['course_id']}"
        )
        assert result["student_id"] == str(student_id), (
            f"Expected student_id {student_id}, got {result['student_id']}"
        )
