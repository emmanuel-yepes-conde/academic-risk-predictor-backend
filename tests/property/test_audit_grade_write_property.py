# Feature: multi-university-support, Property 14: Toda escritura de notas genera entrada en audit_log
"""
Property-based test for audit logging on grade writes.

Verifies that for any successful grade write operation performed by a professor,
exactly one audit log entry is registered with the correct fields:
professor_id, course_id, student_id, timestamp, and operation type.

**Validates: Requirements 5.5**
"""

from unittest.mock import AsyncMock, call
from uuid import uuid4, UUID

import pytest
from hypothesis import given, settings as h_settings, HealthCheck, assume
from hypothesis import strategies as st

from app.application.schemas.audit_log import AuditLogCreate
from app.application.services.professor_course_service import ProfessorCourseService
from app.domain.enums import OperationEnum
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


def _build_service_with_audit_capture(
    professor_id: UUID,
    assigned_course_ids: set[UUID],
    enrolled_students_by_course: dict[UUID, set[UUID]],
) -> tuple[ProfessorCourseService, AsyncMock]:
    """
    Build a ProfessorCourseService with mocked dependencies.

    Returns (service, audit_register_mock) so the caller can inspect
    exactly which AuditLogCreate payloads were passed to audit.register().
    """
    session = AsyncMock()

    class FakeScalarResult:
        def __init__(self, value):
            self._value = value

        def scalar_one_or_none(self):
            return self._value

    async def mock_execute(stmt):
        try:
            compiled = stmt.compile()
            params = compiled.params
        except Exception:
            params = {}

        has_professor_id_param = any("professor_id" in k for k in params)
        has_student_id_param = any("student_id" in k for k in params)

        bound_course_id = None
        for key, value in params.items():
            if "course_id" in key:
                bound_course_id = value
                break

        if has_student_id_param:
            # Enrollment lookup
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
            # ProfessorCourse lookup
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

    return service, service._audit.register


# ---------------------------------------------------------------------------
# Property test — Every successful grade write produces exactly one audit entry
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@h_settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(
    professor_id=uuid_strategy,
    course_id=uuid_strategy,
    student_id=uuid_strategy,
    grade_value=grade_value_strategy,
    grade_type=grade_type_strategy,
)
async def test_grade_write_generates_exactly_one_audit_entry(
    professor_id: UUID,
    course_id: UUID,
    student_id: UUID,
    grade_value: float,
    grade_type: str,
):
    """
    Property 14: Toda escritura de notas genera entrada en audit_log.

    For any successful grade write by an assigned professor on an enrolled
    student, exactly one call to audit.register() must be made.

    **Validates: Requirements 5.5**
    """
    # Ensure no ID collisions
    assume(len({professor_id, course_id, student_id}) == 3)

    assigned_set = {course_id}
    enrolled_students = {course_id: {student_id}}

    service, audit_register = _build_service_with_audit_capture(
        professor_id, assigned_set, enrolled_students,
    )

    grade_data = {"type": grade_type, "value": grade_value}

    await service.write_grade(
        professor_id=professor_id,
        course_id=course_id,
        student_id=student_id,
        grade_data=grade_data,
    )

    assert audit_register.call_count == 1, (
        f"Expected exactly 1 audit.register() call after grade write, "
        f"got {audit_register.call_count}"
    )


# ---------------------------------------------------------------------------
# Property test — Audit entry contains correct fields
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@h_settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(
    professor_id=uuid_strategy,
    course_id=uuid_strategy,
    student_id=uuid_strategy,
    grade_value=grade_value_strategy,
    grade_type=grade_type_strategy,
)
async def test_grade_write_audit_entry_has_correct_fields(
    professor_id: UUID,
    course_id: UUID,
    student_id: UUID,
    grade_value: float,
    grade_type: str,
):
    """
    Property 14: Toda escritura de notas genera entrada en audit_log.

    The audit log entry must contain:
    - table_name = "grades"
    - operation = INSERT
    - user_id = professor_id (the professor who wrote the grade)
    - new_data containing professor_id, course_id, student_id, and grade info

    **Validates: Requirements 5.5**
    """
    assume(len({professor_id, course_id, student_id}) == 3)

    assigned_set = {course_id}
    enrolled_students = {course_id: {student_id}}

    service, audit_register = _build_service_with_audit_capture(
        professor_id, assigned_set, enrolled_students,
    )

    grade_data = {"type": grade_type, "value": grade_value}

    await service.write_grade(
        professor_id=professor_id,
        course_id=course_id,
        student_id=student_id,
        grade_data=grade_data,
    )

    # Extract the AuditLogCreate passed to register()
    audit_call_args = audit_register.call_args
    audit_log_create: AuditLogCreate = audit_call_args[0][0]

    # Verify table_name
    assert audit_log_create.table_name == "grades", (
        f"Expected table_name='grades', got '{audit_log_create.table_name}'"
    )

    # Verify operation type
    assert audit_log_create.operation == OperationEnum.INSERT, (
        f"Expected operation=INSERT, got {audit_log_create.operation}"
    )

    # Verify user_id is the professor who performed the write
    assert audit_log_create.user_id == professor_id, (
        f"Expected user_id={professor_id}, got {audit_log_create.user_id}"
    )

    # Verify new_data contains professor_id, course_id, student_id
    new_data = audit_log_create.new_data
    assert new_data is not None, "new_data must not be None"

    assert new_data.get("professor_id") == str(professor_id), (
        f"Expected professor_id={professor_id} in new_data, "
        f"got {new_data.get('professor_id')}"
    )
    assert new_data.get("course_id") == str(course_id), (
        f"Expected course_id={course_id} in new_data, "
        f"got {new_data.get('course_id')}"
    )
    assert new_data.get("student_id") == str(student_id), (
        f"Expected student_id={student_id} in new_data, "
        f"got {new_data.get('student_id')}"
    )


# ---------------------------------------------------------------------------
# Property test — Multiple grade writes each produce their own audit entry
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@h_settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(
    professor_id=uuid_strategy,
    course_ids=st.lists(st.uuids(), min_size=1, max_size=5, unique=True),
    student_id=uuid_strategy,
    grade_value=grade_value_strategy,
    grade_type=grade_type_strategy,
)
async def test_multiple_grade_writes_each_produce_audit_entry(
    professor_id: UUID,
    course_ids: list[UUID],
    student_id: UUID,
    grade_value: float,
    grade_type: str,
):
    """
    Property 14 (extended): For N successful grade writes across N courses,
    exactly N audit.register() calls must be made, one per write.

    **Validates: Requirements 5.5**
    """
    all_ids = set(course_ids + [professor_id, student_id])
    assume(len(all_ids) == len(course_ids) + 2)

    assigned_set = set(course_ids)
    enrolled_students = {cid: {student_id} for cid in course_ids}

    service, audit_register = _build_service_with_audit_capture(
        professor_id, assigned_set, enrolled_students,
    )

    grade_data = {"type": grade_type, "value": grade_value}

    for cid in course_ids:
        await service.write_grade(
            professor_id=professor_id,
            course_id=cid,
            student_id=student_id,
            grade_data=grade_data,
        )

    assert audit_register.call_count == len(course_ids), (
        f"Expected {len(course_ids)} audit.register() calls for "
        f"{len(course_ids)} grade writes, got {audit_register.call_count}"
    )

    # Verify each call targeted the correct course
    for i, cid in enumerate(course_ids):
        call_args = audit_register.call_args_list[i]
        audit_log_create: AuditLogCreate = call_args[0][0]
        assert audit_log_create.new_data["course_id"] == str(cid), (
            f"Audit entry {i} expected course_id={cid}, "
            f"got {audit_log_create.new_data['course_id']}"
        )
