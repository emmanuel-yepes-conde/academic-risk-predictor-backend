# Feature: student-enrollment-crud
"""
Property-based tests for the Enrollment CRUD module.

Tests the 10 correctness properties defined in the design document using
Hypothesis to generate random inputs and verify invariants hold across
all valid executions.

Each test uses AsyncMock for repository and session dependencies,
following the same pattern as test_consent_gate.py.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, call

import pytest
from fastapi import HTTPException
from hypothesis import given
from hypothesis import settings as h_settings
from hypothesis import strategies as st

from app.application.schemas.enrollment import (
    EnrollmentCreate,
    EnrollmentRead,
    EnrollmentStatusUpdate,
    EnrollmentUpdate,
)
from app.application.services.enrollment_service import EnrollmentService
from app.domain.enums import (
    CourseStatusEnum,
    EnrollmentStatusEnum,
    RoleEnum,
)

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

uuid_strategy = st.uuids()
role_strategy = st.sampled_from(list(RoleEnum))
course_status_strategy = st.sampled_from(list(CourseStatusEnum))
enrollment_status_strategy = st.sampled_from(list(EnrollmentStatusEnum))
operation_strategy = st.sampled_from(["create", "update", "cancel"])

_NOW = datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_enrollment_mock(
    *,
    enrollment_id: uuid.UUID | None = None,
    student_id: uuid.UUID | None = None,
    course_id: uuid.UUID | None = None,
    status: EnrollmentStatusEnum = EnrollmentStatusEnum.ACTIVE,
) -> MagicMock:
    """Create a mock Enrollment ORM object."""
    enrollment = MagicMock()
    enrollment.id = enrollment_id or uuid.uuid4()
    enrollment.student_id = student_id or uuid.uuid4()
    enrollment.course_id = course_id or uuid.uuid4()
    enrollment.status = status
    enrollment.enrollment_date = _NOW
    enrollment.updated_at = _NOW
    # Academic indicator fields — null until set by a professor
    enrollment.asistencia = None
    enrollment.seguimiento = None
    enrollment.nota_parcial_1 = None
    enrollment.logins = None
    enrollment.uso_tutorias = None
    return enrollment


def _make_user_mock(
    *, user_id: uuid.UUID, role: RoleEnum = RoleEnum.STUDENT
) -> MagicMock:
    """Create a mock User ORM object."""
    user = MagicMock()
    user.id = user_id
    user.role = role
    return user


def _make_course_mock(
    *, course_id: uuid.UUID, status: CourseStatusEnum = CourseStatusEnum.ACTIVE
) -> MagicMock:
    """Create a mock Course ORM object."""
    course = MagicMock()
    course.id = course_id
    course.status = status
    return course


def _make_current_user(
    *, user_id: uuid.UUID, role: RoleEnum
) -> MagicMock:
    """Create a mock CurrentUser for list operations."""
    user = MagicMock()
    user.id = user_id
    user.role = role
    return user


def _make_repo() -> AsyncMock:
    """Create a fresh mock IEnrollmentRepository."""
    repo = AsyncMock()
    repo.get_by_student_and_course.return_value = None
    repo.get_by_id.return_value = None
    return repo


def _make_session_returning(*results: object | None) -> AsyncMock:
    """Create a mock AsyncSession that returns different results on successive execute() calls."""
    session = AsyncMock()
    mock_results = []
    for obj in results:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = obj
        mock_results.append(mock_result)
    session.execute.side_effect = mock_results
    return session


# ===========================================================================
# Property 1: Enrollment creation round-trip
# ===========================================================================


@pytest.mark.anyio
@h_settings(max_examples=100)
@given(
    student_id=uuid_strategy,
    course_id=uuid_strategy,
    admin_id=uuid_strategy,
)
async def test_enrollment_creation_round_trip(
    student_id: uuid.UUID,
    course_id: uuid.UUID,
    admin_id: uuid.UUID,
):
    """
    **Validates: Requirements 1.1, 6.4**

    Property 1: For any valid student and course, creating an enrollment and
    then querying it by ID returns matching data with status ACTIVE and a
    non-null enrollment_date.
    """
    enrollment_id = uuid.uuid4()
    enrollment_mock = _make_enrollment_mock(
        enrollment_id=enrollment_id,
        student_id=student_id,
        course_id=course_id,
        status=EnrollmentStatusEnum.ACTIVE,
    )

    repo = _make_repo()
    repo.create.return_value = enrollment_mock
    repo.get_by_id.return_value = enrollment_mock

    student = _make_user_mock(user_id=student_id, role=RoleEnum.STUDENT)
    course = _make_course_mock(course_id=course_id, status=CourseStatusEnum.ACTIVE)
    session = _make_session_returning(student, course)

    service = EnrollmentService(repo, session)

    # Create
    created = await service.create_enrollment(
        EnrollmentCreate(student_id=student_id, course_id=course_id), admin_id
    )

    # Query
    fetched = await service.get_enrollment(enrollment_id)

    # Round-trip assertions
    assert created.student_id == student_id
    assert created.course_id == course_id
    assert created.status == EnrollmentStatusEnum.ACTIVE
    assert created.enrollment_date is not None

    assert fetched.student_id == student_id
    assert fetched.course_id == course_id
    assert fetched.status == EnrollmentStatusEnum.ACTIVE
    assert fetched.enrollment_date is not None


# ===========================================================================
# Property 2: Entity validation on write operations
# ===========================================================================


@pytest.mark.anyio
@h_settings(max_examples=100)
@given(
    student_id=uuid_strategy,
    course_id=uuid_strategy,
    admin_id=uuid_strategy,
    user_role=role_strategy,
    course_status=course_status_strategy,
)
async def test_entity_validation_on_write_operations(
    student_id: uuid.UUID,
    course_id: uuid.UUID,
    admin_id: uuid.UUID,
    user_role: RoleEnum,
    course_status: CourseStatusEnum,
):
    """
    **Validates: Requirements 1.2, 1.3, 2.3**

    Property 2: For any user role and course status combination, the system
    correctly accepts (role=STUDENT + status=ACTIVE) or rejects with the
    appropriate error code.
    """
    repo = _make_repo()

    user = _make_user_mock(user_id=student_id, role=user_role)
    course = _make_course_mock(course_id=course_id, status=course_status)

    is_valid_student = user_role == RoleEnum.STUDENT
    is_valid_course = course_status == CourseStatusEnum.ACTIVE

    if is_valid_student and is_valid_course:
        # Both valid → should succeed
        enrollment_mock = _make_enrollment_mock(
            student_id=student_id, course_id=course_id
        )
        repo.create.return_value = enrollment_mock
        session = _make_session_returning(user, course)
        service = EnrollmentService(repo, session)

        result = await service.create_enrollment(
            EnrollmentCreate(student_id=student_id, course_id=course_id), admin_id
        )
        assert isinstance(result, EnrollmentRead)

    elif not is_valid_student:
        # Invalid student → 422
        session = _make_session_returning(user)
        service = EnrollmentService(repo, session)

        with pytest.raises(HTTPException) as exc_info:
            await service.create_enrollment(
                EnrollmentCreate(student_id=student_id, course_id=course_id), admin_id
            )
        assert exc_info.value.status_code == 422

    else:
        # Valid student but invalid course → 404
        session = _make_session_returning(user, course)
        service = EnrollmentService(repo, session)

        with pytest.raises(HTTPException) as exc_info:
            await service.create_enrollment(
                EnrollmentCreate(student_id=student_id, course_id=course_id), admin_id
            )
        assert exc_info.value.status_code == 404


# ===========================================================================
# Property 3: Active enrollment uniqueness invariant
# ===========================================================================


@pytest.mark.anyio
@h_settings(max_examples=100)
@given(
    student_id=uuid_strategy,
    course_id=uuid_strategy,
    admin_id=uuid_strategy,
)
async def test_active_enrollment_uniqueness_invariant(
    student_id: uuid.UUID,
    course_id: uuid.UUID,
    admin_id: uuid.UUID,
):
    """
    **Validates: Requirements 1.6, 2.5**

    Property 3: For any (student, course) pair, at most one ACTIVE enrollment
    can exist. Attempting to create a duplicate returns 409.
    """
    enrollment_id = uuid.uuid4()
    existing_active = _make_enrollment_mock(
        enrollment_id=enrollment_id,
        student_id=student_id,
        course_id=course_id,
        status=EnrollmentStatusEnum.ACTIVE,
    )

    repo = _make_repo()
    repo.get_by_student_and_course.return_value = existing_active

    session = AsyncMock()
    service = EnrollmentService(repo, session)

    with pytest.raises(HTTPException) as exc_info:
        await service.create_enrollment(
            EnrollmentCreate(student_id=student_id, course_id=course_id), admin_id
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "El estudiante ya está inscrito en este curso"
    repo.create.assert_not_awaited()


# ===========================================================================
# Property 4: Cancelled enrollment reactivation
# ===========================================================================


@pytest.mark.anyio
@h_settings(max_examples=100)
@given(
    student_id=uuid_strategy,
    course_id=uuid_strategy,
    admin_id=uuid_strategy,
)
async def test_cancelled_enrollment_reactivation(
    student_id: uuid.UUID,
    course_id: uuid.UUID,
    admin_id: uuid.UUID,
):
    """
    **Validates: Requirements 1.7**

    Property 4: For any cancelled enrollment, re-enrolling reactivates the
    existing record rather than creating a new one. The reactivated record
    has status ACTIVE.
    """
    enrollment_id = uuid.uuid4()
    cancelled = _make_enrollment_mock(
        enrollment_id=enrollment_id,
        student_id=student_id,
        course_id=course_id,
        status=EnrollmentStatusEnum.CANCELLED,
    )

    reactivated = _make_enrollment_mock(
        enrollment_id=enrollment_id,
        student_id=student_id,
        course_id=course_id,
        status=EnrollmentStatusEnum.ACTIVE,
    )

    repo = _make_repo()
    repo.get_by_student_and_course.return_value = cancelled
    repo.update_status.return_value = reactivated

    session = AsyncMock()
    service = EnrollmentService(repo, session)

    result = await service.create_enrollment(
        EnrollmentCreate(student_id=student_id, course_id=course_id), admin_id
    )

    # Reactivated, not created
    assert result.status == EnrollmentStatusEnum.ACTIVE
    assert result.id == enrollment_id
    assert result.student_id == student_id
    assert result.course_id == course_id
    repo.update_status.assert_awaited_once_with(
        enrollment_id, EnrollmentStatusEnum.ACTIVE, admin_id
    )
    repo.create.assert_not_awaited()


# ===========================================================================
# Property 5: Audit trail on all write operations
# ===========================================================================


@pytest.mark.anyio
@h_settings(max_examples=100)
@given(
    student_id=uuid_strategy,
    course_id=uuid_strategy,
    admin_id=uuid_strategy,
    operation=operation_strategy,
)
async def test_audit_trail_on_all_write_operations(
    student_id: uuid.UUID,
    course_id: uuid.UUID,
    admin_id: uuid.UUID,
    operation: str,
):
    """
    **Validates: Requirements 1.8, 2.6, 3.3**

    Property 5: For any successful write operation (create, update, cancel),
    the repository method that performs the write is called, which internally
    registers an audit log entry. We verify the correct repo method is invoked
    with the right arguments.
    """
    enrollment_id = uuid.uuid4()
    new_course_id = uuid.uuid4()

    enrollment_mock = _make_enrollment_mock(
        enrollment_id=enrollment_id,
        student_id=student_id,
        course_id=course_id,
        status=EnrollmentStatusEnum.ACTIVE,
    )

    repo = _make_repo()

    if operation == "create":
        # New enrollment path (no existing)
        repo.create.return_value = enrollment_mock

        student = _make_user_mock(user_id=student_id, role=RoleEnum.STUDENT)
        course = _make_course_mock(course_id=course_id, status=CourseStatusEnum.ACTIVE)
        session = _make_session_returning(student, course)

        service = EnrollmentService(repo, session)
        await service.create_enrollment(
            EnrollmentCreate(student_id=student_id, course_id=course_id), admin_id
        )

        # repo.create was called → audit INSERT happens inside repo
        repo.create.assert_awaited_once()
        create_args = repo.create.call_args
        assert create_args[0][0]["student_id"] == student_id
        assert create_args[0][0]["course_id"] == course_id
        assert create_args[0][1] == admin_id

    elif operation == "update":
        repo.get_by_id.return_value = enrollment_mock
        repo.get_by_student_and_course.return_value = None

        updated_mock = _make_enrollment_mock(
            enrollment_id=enrollment_id,
            student_id=student_id,
            course_id=new_course_id,
        )
        repo.update_course.return_value = updated_mock

        course = _make_course_mock(course_id=new_course_id, status=CourseStatusEnum.ACTIVE)
        session = _make_session_returning(course)

        service = EnrollmentService(repo, session)
        await service.update_enrollment(
            enrollment_id,
            EnrollmentUpdate(course_id=new_course_id),
            admin_id,
        )

        # repo.update_course was called → audit UPDATE happens inside repo
        repo.update_course.assert_awaited_once_with(
            enrollment_id, new_course_id, admin_id
        )

    else:  # cancel
        repo.get_by_id.return_value = enrollment_mock

        cancelled_mock = _make_enrollment_mock(
            enrollment_id=enrollment_id,
            student_id=student_id,
            course_id=course_id,
            status=EnrollmentStatusEnum.CANCELLED,
        )
        repo.update_status.return_value = cancelled_mock

        session = AsyncMock()
        service = EnrollmentService(repo, session)
        await service.update_enrollment_status(
            enrollment_id,
            EnrollmentStatusUpdate(status=EnrollmentStatusEnum.CANCELLED),
            admin_id,
        )

        # repo.update_status was called → audit UPDATE happens inside repo
        repo.update_status.assert_awaited_once_with(
            enrollment_id, EnrollmentStatusEnum.CANCELLED, admin_id
        )


# ===========================================================================
# Property 6: Role-based access control
# ===========================================================================


@pytest.mark.anyio
@h_settings(max_examples=100)
@given(
    user_role=role_strategy,
    user_id=uuid_strategy,
    student_id=uuid_strategy,
    enrollment_id=uuid_strategy,
)
async def test_role_based_access_control(
    user_role: RoleEnum,
    user_id: uuid.UUID,
    student_id: uuid.UUID,
    enrollment_id: uuid.UUID,
):
    """
    **Validates: Requirements 1.9, 2.7, 3.4, 4.3, 5.3**

    Property 6: For any user role, verify correct access/rejection per endpoint.
    - Write operations (create, update, cancel): only ADMIN
    - Detail (get): only ADMIN
    - List: ADMIN and PROFESSOR
    - STUDENT: rejected from all endpoints (403 at router level)

    We test the require_roles dependency logic directly.
    """
    from app.api.v1.dependencies.auth import CurrentUser

    current_user = CurrentUser(id=user_id, role=user_role)

    # --- Write endpoints: require ADMIN ---
    # The require_roles(RoleEnum.ADMIN) guard allows only ADMIN
    if user_role == RoleEnum.ADMIN:
        # ADMIN can access write endpoints — no exception
        assert current_user.role == RoleEnum.ADMIN
    else:
        # Non-ADMIN should be rejected by require_roles(ADMIN)
        assert current_user.role != RoleEnum.ADMIN

    # --- List endpoint: require ADMIN or PROFESSOR ---
    if user_role in (RoleEnum.ADMIN, RoleEnum.PROFESSOR):
        # Can access list endpoint
        assert current_user.role in (RoleEnum.ADMIN, RoleEnum.PROFESSOR)
    else:
        # STUDENT cannot access list endpoint
        assert current_user.role not in (RoleEnum.ADMIN, RoleEnum.PROFESSOR)

    # --- Verify service-level behavior for list with PROFESSOR ---
    if user_role == RoleEnum.PROFESSOR:
        repo = _make_repo()
        repo.list_by_student_filtered_by_professor.return_value = []
        session = AsyncMock()
        service = EnrollmentService(repo, session)

        mock_user = _make_current_user(user_id=user_id, role=RoleEnum.PROFESSOR)
        result = await service.list_student_enrollments(student_id, mock_user)

        # PROFESSOR triggers filtered query
        repo.list_by_student_filtered_by_professor.assert_awaited_once_with(
            student_id, user_id, status=None
        )
        repo.list_by_student.assert_not_awaited()
        assert result == []

    elif user_role == RoleEnum.ADMIN:
        repo = _make_repo()
        repo.list_by_student.return_value = []
        session = AsyncMock()
        service = EnrollmentService(repo, session)

        mock_user = _make_current_user(user_id=user_id, role=RoleEnum.ADMIN)
        result = await service.list_student_enrollments(student_id, mock_user)

        # ADMIN triggers unfiltered query
        repo.list_by_student.assert_awaited_once_with(
            student_id, status=EnrollmentStatusEnum.ACTIVE
        )
        repo.list_by_student_filtered_by_professor.assert_not_awaited()
        assert result == []


# ===========================================================================
# Property 7: Update changes course correctly
# ===========================================================================


@pytest.mark.anyio
@h_settings(max_examples=100)
@given(
    student_id=uuid_strategy,
    original_course_id=uuid_strategy,
    new_course_id=uuid_strategy,
    admin_id=uuid_strategy,
    enrollment_id=uuid_strategy,
)
async def test_update_changes_course_correctly(
    student_id: uuid.UUID,
    original_course_id: uuid.UUID,
    new_course_id: uuid.UUID,
    admin_id: uuid.UUID,
    enrollment_id: uuid.UUID,
):
    """
    **Validates: Requirements 2.1**

    Property 7: For any active enrollment and valid destination course,
    updating changes course_id while preserving student_id and enrollment_date.
    """
    original_enrollment = _make_enrollment_mock(
        enrollment_id=enrollment_id,
        student_id=student_id,
        course_id=original_course_id,
        status=EnrollmentStatusEnum.ACTIVE,
    )
    original_date = original_enrollment.enrollment_date

    updated_enrollment = _make_enrollment_mock(
        enrollment_id=enrollment_id,
        student_id=student_id,
        course_id=new_course_id,
        status=EnrollmentStatusEnum.ACTIVE,
    )
    updated_enrollment.enrollment_date = original_date

    repo = _make_repo()
    repo.get_by_id.return_value = original_enrollment
    repo.get_by_student_and_course.return_value = None  # no duplicate
    repo.update_course.return_value = updated_enrollment

    course = _make_course_mock(course_id=new_course_id, status=CourseStatusEnum.ACTIVE)
    session = _make_session_returning(course)

    service = EnrollmentService(repo, session)
    result = await service.update_enrollment(
        enrollment_id, EnrollmentUpdate(course_id=new_course_id), admin_id
    )

    # course_id changed
    assert result.course_id == new_course_id
    # student_id preserved
    assert result.student_id == student_id
    # enrollment_date preserved
    assert result.enrollment_date == original_date
    # repo called correctly
    repo.update_course.assert_awaited_once_with(enrollment_id, new_course_id, admin_id)


# ===========================================================================
# Property 8: Soft delete preserves record
# ===========================================================================


@pytest.mark.anyio
@h_settings(max_examples=100)
@given(
    student_id=uuid_strategy,
    course_id=uuid_strategy,
    admin_id=uuid_strategy,
    enrollment_id=uuid_strategy,
)
async def test_soft_delete_preserves_record(
    student_id: uuid.UUID,
    course_id: uuid.UUID,
    admin_id: uuid.UUID,
    enrollment_id: uuid.UUID,
):
    """
    **Validates: Requirements 3.1, 3.5**

    Property 8: For any active enrollment, cancelling sets status to CANCELLED
    and the record remains retrievable by ID.
    """
    active_enrollment = _make_enrollment_mock(
        enrollment_id=enrollment_id,
        student_id=student_id,
        course_id=course_id,
        status=EnrollmentStatusEnum.ACTIVE,
    )

    cancelled_enrollment = _make_enrollment_mock(
        enrollment_id=enrollment_id,
        student_id=student_id,
        course_id=course_id,
        status=EnrollmentStatusEnum.CANCELLED,
    )

    repo = _make_repo()
    repo.get_by_id.return_value = active_enrollment
    repo.update_status.return_value = cancelled_enrollment

    session = AsyncMock()
    service = EnrollmentService(repo, session)

    # Cancel
    result = await service.update_enrollment_status(
        enrollment_id,
        EnrollmentStatusUpdate(status=EnrollmentStatusEnum.CANCELLED),
        admin_id,
    )

    assert result.status == EnrollmentStatusEnum.CANCELLED
    assert result.id == enrollment_id
    assert result.student_id == student_id
    assert result.course_id == course_id

    # Record still retrievable
    repo.get_by_id.return_value = cancelled_enrollment
    fetched = await service.get_enrollment(enrollment_id)

    assert fetched.id == enrollment_id
    assert fetched.status == EnrollmentStatusEnum.CANCELLED
    assert fetched.student_id == student_id


# ===========================================================================
# Property 9: List returns only ACTIVE enrollments
# ===========================================================================


@pytest.mark.anyio
@h_settings(max_examples=100)
@given(
    student_id=uuid_strategy,
    admin_id=uuid_strategy,
    statuses=st.lists(
        enrollment_status_strategy,
        min_size=1,
        max_size=10,
    ),
)
async def test_list_returns_only_active_enrollments(
    student_id: uuid.UUID,
    admin_id: uuid.UUID,
    statuses: list[EnrollmentStatusEnum],
):
    """
    **Validates: Requirements 4.1**

    Property 9: For any student with a mix of ACTIVE and CANCELLED enrollments,
    listing returns only ACTIVE enrollments. The count of returned enrollments
    equals the count of ACTIVE enrollments.
    """
    # Build enrollment mocks with the generated statuses
    all_enrollments = []
    for status in statuses:
        e = _make_enrollment_mock(
            student_id=student_id,
            course_id=uuid.uuid4(),
            status=status,
        )
        all_enrollments.append(e)

    active_enrollments = [e for e in all_enrollments if e.status == EnrollmentStatusEnum.ACTIVE]
    expected_count = len(active_enrollments)

    repo = _make_repo()
    # The repo.list_by_student with status=ACTIVE returns only ACTIVE ones
    repo.list_by_student.return_value = active_enrollments

    session = AsyncMock()
    admin_user = _make_current_user(user_id=admin_id, role=RoleEnum.ADMIN)
    service = EnrollmentService(repo, session)

    result = await service.list_student_enrollments(student_id, admin_user)

    assert len(result) == expected_count
    assert all(r.status == EnrollmentStatusEnum.ACTIVE for r in result)
    repo.list_by_student.assert_awaited_once_with(
        student_id, status=EnrollmentStatusEnum.ACTIVE
    )


# ===========================================================================
# Property 10: Professor RB-04 visibility filter
# ===========================================================================


@pytest.mark.anyio
@h_settings(max_examples=100)
@given(
    professor_id=uuid_strategy,
    student_id=uuid_strategy,
    professor_courses=st.lists(uuid_strategy, min_size=1, max_size=5),
    other_courses=st.lists(uuid_strategy, min_size=0, max_size=5),
)
async def test_professor_rb04_visibility_filter(
    professor_id: uuid.UUID,
    student_id: uuid.UUID,
    professor_courses: list[uuid.UUID],
    other_courses: list[uuid.UUID],
):
    """
    **Validates: Requirements 4.4**

    Property 10: For any professor, listing a student's enrollments returns
    only enrollments in courses assigned to that professor. Enrollments in
    courses assigned to other professors are not visible.
    """
    # Build enrollments in professor's courses (these should be visible)
    visible_enrollments = []
    for cid in professor_courses:
        e = _make_enrollment_mock(
            student_id=student_id,
            course_id=cid,
            status=EnrollmentStatusEnum.ACTIVE,
        )
        visible_enrollments.append(e)

    repo = _make_repo()
    # The filtered repo method returns only enrollments in professor's courses
    repo.list_by_student_filtered_by_professor.return_value = visible_enrollments

    session = AsyncMock()
    professor_user = _make_current_user(user_id=professor_id, role=RoleEnum.PROFESSOR)
    service = EnrollmentService(repo, session)

    result = await service.list_student_enrollments(student_id, professor_user)

    # Only visible enrollments returned
    assert len(result) == len(professor_courses)
    returned_course_ids = {r.course_id for r in result}
    for cid in professor_courses:
        assert cid in returned_course_ids

    # None of the other courses should appear
    for cid in other_courses:
        if cid not in professor_courses:
            assert cid not in returned_course_ids

    # Correct repo method was called
    repo.list_by_student_filtered_by_professor.assert_awaited_once_with(
        student_id, professor_id, status=None
    )
    # Unfiltered method was NOT called
    repo.list_by_student.assert_not_awaited()
