"""
Unit tests for EnrollmentService.

Tests cover specific examples and edge cases for all CRUD flows:
- test_create_enrollment_success — happy path with valid data (new enrollment)
- test_create_enrollment_reactivates_cancelled — reactivates CANCELLED enrollment
- test_create_enrollment_duplicate_active_returns_409 — duplicate ACTIVE enrollment
- test_create_enrollment_invalid_student_returns_422 — student not found or wrong role
- test_create_enrollment_invalid_course_returns_404 — course not found or inactive
- test_update_enrollment_success — happy path course change
- test_update_enrollment_duplicate_destination_returns_409 — duplicate in destination
- test_update_enrollment_not_found_returns_404 — non-existent enrollment
- test_cancel_enrollment_success — happy path soft delete
- test_cancel_enrollment_not_found_returns_404 — non-existent enrollment
- test_get_enrollment_success — retrieval by existing ID
- test_get_enrollment_not_found_returns_404 — non-existent ID
- test_list_student_enrollments_admin — ADMIN sees all ACTIVE
- test_list_student_enrollments_professor_filters — PROFESSOR filtered by RB-04

Requirements: 1.1–1.9, 2.1–2.7, 3.1–3.5, 4.1–4.4, 5.1–5.3
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

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
# Helpers
# ---------------------------------------------------------------------------

_ENROLLMENT_ID = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
_STUDENT_ID = uuid.UUID("11111111-2222-3333-4444-555555555555")
_COURSE_ID = uuid.UUID("22222222-3333-4444-5555-666666666666")
_NEW_COURSE_ID = uuid.UUID("33333333-4444-5555-6666-777777777777")
_ADMIN_USER_ID = uuid.UUID("99999999-8888-7777-6666-555555555555")
_PROFESSOR_ID = uuid.UUID("44444444-5555-6666-7777-888888888888")
_NOW = datetime.now(timezone.utc)


def _make_enrollment(
    *,
    enrollment_id: uuid.UUID = _ENROLLMENT_ID,
    student_id: uuid.UUID = _STUDENT_ID,
    course_id: uuid.UUID = _COURSE_ID,
    status: EnrollmentStatusEnum = EnrollmentStatusEnum.ACTIVE,
) -> MagicMock:
    """Create a mock Enrollment with the given attributes."""
    enrollment = MagicMock()
    enrollment.id = enrollment_id
    enrollment.student_id = student_id
    enrollment.course_id = course_id
    enrollment.status = status
    enrollment.enrollment_date = _NOW
    enrollment.updated_at = _NOW
    return enrollment


def _make_student(
    *,
    user_id: uuid.UUID = _STUDENT_ID,
    role: RoleEnum = RoleEnum.STUDENT,
) -> MagicMock:
    """Create a mock User with the given attributes."""
    user = MagicMock()
    user.id = user_id
    user.role = role
    return user


def _make_course(
    *,
    course_id: uuid.UUID = _COURSE_ID,
    status: CourseStatusEnum = CourseStatusEnum.ACTIVE,
) -> MagicMock:
    """Create a mock Course with the given attributes."""
    course = MagicMock()
    course.id = course_id
    course.status = status
    return course


def _make_current_user(
    *,
    user_id: uuid.UUID = _ADMIN_USER_ID,
    role: RoleEnum = RoleEnum.ADMIN,
) -> MagicMock:
    """Create a mock current_user for list operations."""
    user = MagicMock()
    user.id = user_id
    user.role = role
    return user


def _make_repo() -> AsyncMock:
    """Create a mock IEnrollmentRepository with default return values."""
    repo = AsyncMock()
    repo.get_by_student_and_course.return_value = None
    repo.get_by_id.return_value = None
    return repo


def _make_session_with_result(return_obj: object | None) -> AsyncMock:
    """Create a mock AsyncSession whose execute().scalar_one_or_none() returns return_obj."""
    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = return_obj
    session.execute.return_value = mock_result
    return session


def _make_session_with_sequence(*results: object | None) -> AsyncMock:
    """Create a mock AsyncSession that returns different results on successive execute() calls."""
    session = AsyncMock()
    mock_results = []
    for obj in results:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = obj
        mock_results.append(mock_result)
    session.execute.side_effect = mock_results
    return session


def _valid_create_data() -> EnrollmentCreate:
    return EnrollmentCreate(student_id=_STUDENT_ID, course_id=_COURSE_ID)


def _valid_update_data() -> EnrollmentUpdate:
    return EnrollmentUpdate(course_id=_NEW_COURSE_ID)


# ===================================================================
# Create: happy path — new enrollment (Requirement 1.1)
# ===================================================================


class TestCreateEnrollmentSuccess:
    @pytest.mark.anyio
    async def test_create_enrollment_success(self):
        """A valid EnrollmentCreate with no existing enrollment must create and return EnrollmentRead."""
        repo = _make_repo()
        enrollment = _make_enrollment()
        repo.create.return_value = enrollment

        student = _make_student()
        course = _make_course()
        session = _make_session_with_sequence(student, course)

        service = EnrollmentService(repo, session)
        result = await service.create_enrollment(_valid_create_data(), _ADMIN_USER_ID)

        assert isinstance(result, EnrollmentRead)
        assert result.id == _ENROLLMENT_ID
        assert result.student_id == _STUDENT_ID
        assert result.course_id == _COURSE_ID
        assert result.status == EnrollmentStatusEnum.ACTIVE
        repo.get_by_student_and_course.assert_awaited_once_with(_STUDENT_ID, _COURSE_ID)
        repo.create.assert_awaited_once()


# ===================================================================
# Create: reactivates CANCELLED enrollment (Requirement 1.7)
# ===================================================================


class TestCreateEnrollmentReactivatesCancelled:
    @pytest.mark.anyio
    async def test_create_enrollment_reactivates_cancelled(self):
        """If a CANCELLED enrollment exists for (student, course), it must be reactivated."""
        repo = _make_repo()
        cancelled = _make_enrollment(status=EnrollmentStatusEnum.CANCELLED)
        repo.get_by_student_and_course.return_value = cancelled

        reactivated = _make_enrollment(status=EnrollmentStatusEnum.ACTIVE)
        repo.update_status.return_value = reactivated

        session = AsyncMock()  # session not used for reactivation path
        service = EnrollmentService(repo, session)
        result = await service.create_enrollment(_valid_create_data(), _ADMIN_USER_ID)

        assert isinstance(result, EnrollmentRead)
        assert result.status == EnrollmentStatusEnum.ACTIVE
        repo.update_status.assert_awaited_once_with(
            _ENROLLMENT_ID, EnrollmentStatusEnum.ACTIVE, _ADMIN_USER_ID
        )
        repo.create.assert_not_awaited()


# ===================================================================
# Create: duplicate ACTIVE enrollment (Requirement 1.6)
# ===================================================================


class TestCreateEnrollmentDuplicateActive:
    @pytest.mark.anyio
    async def test_create_enrollment_duplicate_active_returns_409(self):
        """Duplicate ACTIVE enrollment must raise HTTPException 409."""
        repo = _make_repo()
        existing = _make_enrollment(status=EnrollmentStatusEnum.ACTIVE)
        repo.get_by_student_and_course.return_value = existing

        session = AsyncMock()
        service = EnrollmentService(repo, session)

        with pytest.raises(HTTPException) as exc_info:
            await service.create_enrollment(_valid_create_data(), _ADMIN_USER_ID)

        assert exc_info.value.status_code == 409
        assert exc_info.value.detail == "El estudiante ya está inscrito en este curso"
        repo.create.assert_not_awaited()


# ===================================================================
# Create: invalid student (Requirement 1.4)
# ===================================================================


class TestCreateEnrollmentInvalidStudent:
    @pytest.mark.anyio
    async def test_create_enrollment_invalid_student_returns_422(self):
        """Non-existent or non-STUDENT user must raise HTTPException 422."""
        repo = _make_repo()
        # No existing enrollment
        repo.get_by_student_and_course.return_value = None

        # Session returns None for student lookup
        session = _make_session_with_result(None)

        service = EnrollmentService(repo, session)

        with pytest.raises(HTTPException) as exc_info:
            await service.create_enrollment(_valid_create_data(), _ADMIN_USER_ID)

        assert exc_info.value.status_code == 422
        assert exc_info.value.detail == "El usuario indicado no existe o no tiene rol de estudiante"
        repo.create.assert_not_awaited()

    @pytest.mark.anyio
    async def test_create_enrollment_wrong_role_returns_422(self):
        """User with non-STUDENT role must raise HTTPException 422."""
        repo = _make_repo()
        repo.get_by_student_and_course.return_value = None

        professor = _make_student(role=RoleEnum.PROFESSOR)
        session = _make_session_with_result(professor)

        service = EnrollmentService(repo, session)

        with pytest.raises(HTTPException) as exc_info:
            await service.create_enrollment(_valid_create_data(), _ADMIN_USER_ID)

        assert exc_info.value.status_code == 422
        assert exc_info.value.detail == "El usuario indicado no existe o no tiene rol de estudiante"


# ===================================================================
# Create: invalid course (Requirement 1.5)
# ===================================================================


class TestCreateEnrollmentInvalidCourse:
    @pytest.mark.anyio
    async def test_create_enrollment_invalid_course_returns_404(self):
        """Non-existent course must raise HTTPException 404."""
        repo = _make_repo()
        repo.get_by_student_and_course.return_value = None

        student = _make_student()
        # First execute → student found, second execute → course not found
        session = _make_session_with_sequence(student, None)

        service = EnrollmentService(repo, session)

        with pytest.raises(HTTPException) as exc_info:
            await service.create_enrollment(_valid_create_data(), _ADMIN_USER_ID)

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Curso no encontrado"
        repo.create.assert_not_awaited()

    @pytest.mark.anyio
    async def test_create_enrollment_inactive_course_returns_404(self):
        """Inactive course must raise HTTPException 404."""
        repo = _make_repo()
        repo.get_by_student_and_course.return_value = None

        student = _make_student()
        inactive_course = _make_course(status=CourseStatusEnum.INACTIVE)
        session = _make_session_with_sequence(student, inactive_course)

        service = EnrollmentService(repo, session)

        with pytest.raises(HTTPException) as exc_info:
            await service.create_enrollment(_valid_create_data(), _ADMIN_USER_ID)

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Curso no encontrado"


# ===================================================================
# Update: happy path (Requirement 2.1)
# ===================================================================


class TestUpdateEnrollmentSuccess:
    @pytest.mark.anyio
    async def test_update_enrollment_success(self):
        """A valid update must change course and return EnrollmentRead."""
        repo = _make_repo()
        existing = _make_enrollment()
        repo.get_by_id.return_value = existing
        repo.get_by_student_and_course.return_value = None  # no duplicate

        updated = _make_enrollment(course_id=_NEW_COURSE_ID)
        repo.update_course.return_value = updated

        # Session for _validate_course (destination course)
        new_course = _make_course(course_id=_NEW_COURSE_ID)
        session = _make_session_with_result(new_course)

        service = EnrollmentService(repo, session)
        result = await service.update_enrollment(
            _ENROLLMENT_ID, _valid_update_data(), _ADMIN_USER_ID
        )

        assert isinstance(result, EnrollmentRead)
        assert result.course_id == _NEW_COURSE_ID
        repo.update_course.assert_awaited_once_with(
            _ENROLLMENT_ID, _NEW_COURSE_ID, _ADMIN_USER_ID
        )


# ===================================================================
# Update: not found (Requirement 2.2)
# ===================================================================


class TestUpdateEnrollmentNotFound:
    @pytest.mark.anyio
    async def test_update_enrollment_not_found_returns_404(self):
        """Non-existent enrollment_id must raise HTTPException 404."""
        repo = _make_repo()
        repo.get_by_id.return_value = None

        session = AsyncMock()
        service = EnrollmentService(repo, session)

        with pytest.raises(HTTPException) as exc_info:
            await service.update_enrollment(
                _ENROLLMENT_ID, _valid_update_data(), _ADMIN_USER_ID
            )

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Inscripción no encontrada"
        repo.update_course.assert_not_awaited()


# ===================================================================
# Update: duplicate in destination (Requirement 2.5)
# ===================================================================


class TestUpdateEnrollmentDuplicateDestination:
    @pytest.mark.anyio
    async def test_update_enrollment_duplicate_destination_returns_409(self):
        """Duplicate ACTIVE enrollment in destination course must raise 409."""
        repo = _make_repo()
        existing = _make_enrollment()
        repo.get_by_id.return_value = existing

        # Duplicate ACTIVE enrollment in destination
        duplicate = _make_enrollment(course_id=_NEW_COURSE_ID, status=EnrollmentStatusEnum.ACTIVE)
        repo.get_by_student_and_course.return_value = duplicate

        # Session for _validate_course
        new_course = _make_course(course_id=_NEW_COURSE_ID)
        session = _make_session_with_result(new_course)

        service = EnrollmentService(repo, session)

        with pytest.raises(HTTPException) as exc_info:
            await service.update_enrollment(
                _ENROLLMENT_ID, _valid_update_data(), _ADMIN_USER_ID
            )

        assert exc_info.value.status_code == 409
        assert exc_info.value.detail == "El estudiante ya está inscrito en el curso destino"
        repo.update_course.assert_not_awaited()


# ===================================================================
# Cancel: happy path (Requirement 3.1)
# ===================================================================


class TestCancelEnrollmentSuccess:
    @pytest.mark.anyio
    async def test_cancel_enrollment_success(self):
        """Cancelling an existing enrollment must set status to CANCELLED."""
        repo = _make_repo()
        existing = _make_enrollment()
        repo.get_by_id.return_value = existing

        cancelled = _make_enrollment(status=EnrollmentStatusEnum.CANCELLED)
        repo.update_status.return_value = cancelled

        session = AsyncMock()
        service = EnrollmentService(repo, session)
        body = EnrollmentStatusUpdate(status=EnrollmentStatusEnum.CANCELLED)
        result = await service.update_enrollment_status(_ENROLLMENT_ID, body, _ADMIN_USER_ID)

        assert isinstance(result, EnrollmentRead)
        assert result.status == EnrollmentStatusEnum.CANCELLED
        repo.update_status.assert_awaited_once_with(
            _ENROLLMENT_ID, EnrollmentStatusEnum.CANCELLED, _ADMIN_USER_ID
        )


# ===================================================================
# Cancel: not found (Requirement 3.2)
# ===================================================================


class TestCancelEnrollmentNotFound:
    @pytest.mark.anyio
    async def test_cancel_enrollment_not_found_returns_404(self):
        """Non-existent enrollment_id must raise HTTPException 404."""
        repo = _make_repo()
        repo.get_by_id.return_value = None

        session = AsyncMock()
        service = EnrollmentService(repo, session)
        body = EnrollmentStatusUpdate(status=EnrollmentStatusEnum.CANCELLED)

        with pytest.raises(HTTPException) as exc_info:
            await service.update_enrollment_status(_ENROLLMENT_ID, body, _ADMIN_USER_ID)

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Inscripción no encontrada"


# ===================================================================
# Get: happy path (Requirement 5.1)
# ===================================================================


class TestGetEnrollmentSuccess:
    @pytest.mark.anyio
    async def test_get_enrollment_success(self):
        """Existing enrollment_id must return EnrollmentRead."""
        repo = _make_repo()
        enrollment = _make_enrollment()
        repo.get_by_id.return_value = enrollment

        session = AsyncMock()
        service = EnrollmentService(repo, session)
        result = await service.get_enrollment(_ENROLLMENT_ID)

        assert isinstance(result, EnrollmentRead)
        assert result.id == _ENROLLMENT_ID
        assert result.student_id == _STUDENT_ID
        assert result.course_id == _COURSE_ID


# ===================================================================
# Get: not found (Requirement 5.2)
# ===================================================================


class TestGetEnrollmentNotFound:
    @pytest.mark.anyio
    async def test_get_enrollment_not_found_returns_404(self):
        """Non-existent enrollment_id must raise HTTPException 404."""
        repo = _make_repo()
        repo.get_by_id.return_value = None

        session = AsyncMock()
        service = EnrollmentService(repo, session)

        with pytest.raises(HTTPException) as exc_info:
            await service.get_enrollment(_ENROLLMENT_ID)

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Inscripción no encontrada"


# ===================================================================
# List: ADMIN sees all ACTIVE (Requirement 4.1)
# ===================================================================


class TestListStudentEnrollmentsAdmin:
    @pytest.mark.anyio
    async def test_list_student_enrollments_admin(self):
        """ADMIN user must receive all ACTIVE enrollments for the student."""
        repo = _make_repo()
        enrollments = [_make_enrollment(), _make_enrollment(
            enrollment_id=uuid.uuid4(), course_id=uuid.uuid4()
        )]
        repo.list_by_student.return_value = enrollments

        session = AsyncMock()
        admin_user = _make_current_user(role=RoleEnum.ADMIN)
        service = EnrollmentService(repo, session)
        result = await service.list_student_enrollments(_STUDENT_ID, admin_user)

        assert len(result) == 2
        assert all(isinstance(r, EnrollmentRead) for r in result)
        repo.list_by_student.assert_awaited_once_with(
            _STUDENT_ID, status=EnrollmentStatusEnum.ACTIVE
        )
        repo.list_by_student_filtered_by_professor.assert_not_awaited()


# ===================================================================
# List: PROFESSOR filters by own courses — RB-04 (Requirement 4.4)
# ===================================================================


class TestListStudentEnrollmentsProfessor:
    @pytest.mark.anyio
    async def test_list_student_enrollments_professor_filters(self):
        """PROFESSOR user must only see enrollments in their assigned courses (RB-04)."""
        repo = _make_repo()
        enrollment = _make_enrollment()
        repo.list_by_student_filtered_by_professor.return_value = [enrollment]

        session = AsyncMock()
        professor_user = _make_current_user(
            user_id=_PROFESSOR_ID, role=RoleEnum.PROFESSOR
        )
        service = EnrollmentService(repo, session)
        result = await service.list_student_enrollments(_STUDENT_ID, professor_user)

        assert len(result) == 1
        assert isinstance(result[0], EnrollmentRead)
        repo.list_by_student_filtered_by_professor.assert_awaited_once_with(
            _STUDENT_ID, _PROFESSOR_ID, status=None
        )
        repo.list_by_student.assert_not_awaited()

    @pytest.mark.anyio
    async def test_list_student_enrollments_professor_empty(self):
        """PROFESSOR with no matching courses must receive empty list."""
        repo = _make_repo()
        repo.list_by_student_filtered_by_professor.return_value = []

        session = AsyncMock()
        professor_user = _make_current_user(
            user_id=_PROFESSOR_ID, role=RoleEnum.PROFESSOR
        )
        service = EnrollmentService(repo, session)
        result = await service.list_student_enrollments(_STUDENT_ID, professor_user)

        assert result == []
        repo.list_by_student_filtered_by_professor.assert_awaited_once_with(
            _STUDENT_ID, _PROFESSOR_ID, status=None
        )


# ===================================================================
# List: STUDENT role returns all statuses when no filter (Req 1.5)
# ===================================================================


class TestListStudentEnrollmentsStudent:
    @pytest.mark.anyio
    async def test_list_student_enrollments_student_no_filter(self):
        """STUDENT role with no status filter must return all enrollments (all statuses)."""
        repo = _make_repo()
        enrollments = [
            _make_enrollment(status=EnrollmentStatusEnum.ACTIVE),
            _make_enrollment(
                enrollment_id=uuid.uuid4(),
                course_id=uuid.uuid4(),
                status=EnrollmentStatusEnum.COMPLETED,
            ),
            _make_enrollment(
                enrollment_id=uuid.uuid4(),
                course_id=uuid.uuid4(),
                status=EnrollmentStatusEnum.PENDING,
            ),
        ]
        repo.list_by_student.return_value = enrollments

        session = AsyncMock()
        student_user = _make_current_user(
            user_id=_STUDENT_ID, role=RoleEnum.STUDENT
        )
        service = EnrollmentService(repo, session)
        result = await service.list_student_enrollments(_STUDENT_ID, student_user)

        assert len(result) == 3
        assert all(isinstance(r, EnrollmentRead) for r in result)
        # status=None means no filter — return all statuses
        repo.list_by_student.assert_awaited_once_with(
            _STUDENT_ID, status=None
        )
        repo.list_by_student_filtered_by_professor.assert_not_awaited()

    @pytest.mark.anyio
    async def test_list_student_enrollments_student_with_status_filter(self):
        """STUDENT role with status filter must pass the filter to the repository."""
        repo = _make_repo()
        completed = _make_enrollment(status=EnrollmentStatusEnum.COMPLETED)
        repo.list_by_student.return_value = [completed]

        session = AsyncMock()
        student_user = _make_current_user(
            user_id=_STUDENT_ID, role=RoleEnum.STUDENT
        )
        service = EnrollmentService(repo, session)
        result = await service.list_student_enrollments(
            _STUDENT_ID, student_user, status=EnrollmentStatusEnum.COMPLETED
        )

        assert len(result) == 1
        assert result[0].status == EnrollmentStatusEnum.COMPLETED
        repo.list_by_student.assert_awaited_once_with(
            _STUDENT_ID, status=EnrollmentStatusEnum.COMPLETED
        )


# ===================================================================
# List: ADMIN defaults to ACTIVE when no filter (Req 3.2)
# ===================================================================


class TestListStudentEnrollmentsAdminDefaultActive:
    @pytest.mark.anyio
    async def test_list_student_enrollments_admin_defaults_to_active(self):
        """ADMIN with no status filter must default to ACTIVE enrollments."""
        repo = _make_repo()
        enrollments = [_make_enrollment(status=EnrollmentStatusEnum.ACTIVE)]
        repo.list_by_student.return_value = enrollments

        session = AsyncMock()
        admin_user = _make_current_user(role=RoleEnum.ADMIN)
        service = EnrollmentService(repo, session)
        result = await service.list_student_enrollments(_STUDENT_ID, admin_user)

        assert len(result) == 1
        repo.list_by_student.assert_awaited_once_with(
            _STUDENT_ID, status=EnrollmentStatusEnum.ACTIVE
        )

    @pytest.mark.anyio
    async def test_list_student_enrollments_admin_with_status_filter(self):
        """ADMIN with explicit status filter must use that filter instead of ACTIVE default."""
        repo = _make_repo()
        completed = _make_enrollment(status=EnrollmentStatusEnum.COMPLETED)
        repo.list_by_student.return_value = [completed]

        session = AsyncMock()
        admin_user = _make_current_user(role=RoleEnum.ADMIN)
        service = EnrollmentService(repo, session)
        result = await service.list_student_enrollments(
            _STUDENT_ID, admin_user, status=EnrollmentStatusEnum.COMPLETED
        )

        assert len(result) == 1
        assert result[0].status == EnrollmentStatusEnum.COMPLETED
        repo.list_by_student.assert_awaited_once_with(
            _STUDENT_ID, status=EnrollmentStatusEnum.COMPLETED
        )


# ===================================================================
# List: PROFESSOR applies RB-04 + status filter (Req 3.4)
# ===================================================================


class TestListStudentEnrollmentsProfessorWithStatus:
    @pytest.mark.anyio
    async def test_list_student_enrollments_professor_with_status_filter(self):
        """PROFESSOR with status filter must apply both RB-04 and status filter."""
        repo = _make_repo()
        completed = _make_enrollment(status=EnrollmentStatusEnum.COMPLETED)
        repo.list_by_student_filtered_by_professor.return_value = [completed]

        session = AsyncMock()
        professor_user = _make_current_user(
            user_id=_PROFESSOR_ID, role=RoleEnum.PROFESSOR
        )
        service = EnrollmentService(repo, session)
        result = await service.list_student_enrollments(
            _STUDENT_ID, professor_user, status=EnrollmentStatusEnum.COMPLETED
        )

        assert len(result) == 1
        assert result[0].status == EnrollmentStatusEnum.COMPLETED
        repo.list_by_student_filtered_by_professor.assert_awaited_once_with(
            _STUDENT_ID, _PROFESSOR_ID, status=EnrollmentStatusEnum.COMPLETED
        )
        repo.list_by_student.assert_not_awaited()


# ===================================================================
# update_enrollment_status: sets status to COMPLETED (Req 2.2)
# ===================================================================


class TestUpdateEnrollmentStatusCompleted:
    @pytest.mark.anyio
    async def test_update_enrollment_status_completed(self):
        """update_enrollment_status with COMPLETED must set status to COMPLETED."""
        repo = _make_repo()
        existing = _make_enrollment(status=EnrollmentStatusEnum.ACTIVE)
        repo.get_by_id.return_value = existing

        completed = _make_enrollment(status=EnrollmentStatusEnum.COMPLETED)
        repo.update_status.return_value = completed

        session = AsyncMock()
        service = EnrollmentService(repo, session)
        body = EnrollmentStatusUpdate(status=EnrollmentStatusEnum.COMPLETED)
        result = await service.update_enrollment_status(_ENROLLMENT_ID, body, _ADMIN_USER_ID)

        assert isinstance(result, EnrollmentRead)
        assert result.status == EnrollmentStatusEnum.COMPLETED
        repo.update_status.assert_awaited_once_with(
            _ENROLLMENT_ID, EnrollmentStatusEnum.COMPLETED, _ADMIN_USER_ID
        )


# ===================================================================
# update_enrollment_status: sets status to PENDING (Req 2.3)
# ===================================================================


class TestUpdateEnrollmentStatusPending:
    @pytest.mark.anyio
    async def test_update_enrollment_status_pending(self):
        """update_enrollment_status with PENDING must set status to PENDING."""
        repo = _make_repo()
        existing = _make_enrollment(status=EnrollmentStatusEnum.ACTIVE)
        repo.get_by_id.return_value = existing

        pending = _make_enrollment(status=EnrollmentStatusEnum.PENDING)
        repo.update_status.return_value = pending

        session = AsyncMock()
        service = EnrollmentService(repo, session)
        body = EnrollmentStatusUpdate(status=EnrollmentStatusEnum.PENDING)
        result = await service.update_enrollment_status(_ENROLLMENT_ID, body, _ADMIN_USER_ID)

        assert isinstance(result, EnrollmentRead)
        assert result.status == EnrollmentStatusEnum.PENDING
        repo.update_status.assert_awaited_once_with(
            _ENROLLMENT_ID, EnrollmentStatusEnum.PENDING, _ADMIN_USER_ID
        )
