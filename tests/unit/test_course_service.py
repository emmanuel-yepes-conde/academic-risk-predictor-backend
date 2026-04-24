"""
Unit tests for CourseService.

Tests cover specific examples and edge cases for all CRUD flows:
- test_create_course_success — happy path with valid data
- test_create_course_duplicate_code_returns_409 — exact error message verification
- test_get_course_success — retrieval by existing ID
- test_get_course_not_found_returns_404 — non-existent ID
- test_update_course_success — happy path partial update
- test_update_course_not_found_returns_404 — non-existent ID
- test_update_course_duplicate_code_different_course_returns_409 — code from another course
- test_update_course_same_code_no_conflict — self-update with own code
- test_update_course_status_success — status change
- test_update_course_status_not_found_returns_404 — non-existent ID
- test_list_courses_default_status_active — status=None becomes ACTIVE

Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.application.schemas.course import CourseCreate, CourseRead, CourseUpdate
from app.application.schemas.user import PaginatedResponse
from app.application.services.course_service import CourseService
from app.domain.enums import CourseStatusEnum


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_COURSE_ID = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
_OTHER_COURSE_ID = uuid.UUID("11111111-2222-3333-4444-555555555555")
_PROGRAM_ID = uuid.UUID("99999999-8888-7777-6666-555555555555")


def _make_course(
    *,
    course_id: uuid.UUID = _COURSE_ID,
    code: str = "MAT101",
    name: str = "Cálculo I",
    credits: int = 4,
    academic_period: str = "2024-1",
    program_id: uuid.UUID = _PROGRAM_ID,
    professor_id: uuid.UUID | None = None,
    status: CourseStatusEnum = CourseStatusEnum.ACTIVE,
) -> MagicMock:
    """Create a mock Course with the given attributes."""
    course = MagicMock()
    course.id = course_id
    course.code = code
    course.name = name
    course.credits = credits
    course.academic_period = academic_period
    course.program_id = program_id
    course.professor_id = professor_id
    course.status = status
    course.created_at = datetime.now(timezone.utc)
    return course


def _make_repo() -> AsyncMock:
    """Create a mock ICourseRepository with default return values."""
    repo = AsyncMock()
    repo.get_by_code.return_value = None
    return repo


def _valid_create_data() -> CourseCreate:
    return CourseCreate(
        code="MAT101",
        name="Cálculo I",
        credits=4,
        academic_period="2024-1",
        program_id=_PROGRAM_ID,
    )


# ===================================================================
# Create: happy path (Requirement 6.2)
# ===================================================================


class TestCreateCourseSuccess:
    @pytest.mark.anyio
    async def test_create_course_success(self):
        """A valid CourseCreate must persist and return CourseRead."""
        repo = _make_repo()
        course = _make_course()
        repo.create.return_value = course
        service = CourseService(repo)

        result = await service.create_course(_valid_create_data())

        assert isinstance(result, CourseRead)
        assert result.id == _COURSE_ID
        assert result.code == "MAT101"
        assert result.name == "Cálculo I"
        assert result.credits == 4
        repo.create.assert_awaited_once()


# ===================================================================
# Create: duplicate code (Requirement 6.3)
# ===================================================================


class TestCreateCourseDuplicateCode:
    @pytest.mark.anyio
    async def test_create_course_duplicate_code_returns_409(self):
        """Duplicate code must raise HTTPException 409 with exact message."""
        repo = _make_repo()
        repo.get_by_code.return_value = _make_course()
        service = CourseService(repo)

        with pytest.raises(HTTPException) as exc_info:
            await service.create_course(_valid_create_data())

        assert exc_info.value.status_code == 409
        assert exc_info.value.detail == "El code ya está registrado"
        repo.create.assert_not_awaited()


# ===================================================================
# Get: happy path (Requirement 6.7)
# ===================================================================


class TestGetCourseSuccess:
    @pytest.mark.anyio
    async def test_get_course_success(self):
        """Existing course_id must return CourseRead."""
        repo = _make_repo()
        course = _make_course()
        repo.obtener_por_id.return_value = course
        service = CourseService(repo)

        result = await service.get_course(_COURSE_ID)

        assert isinstance(result, CourseRead)
        assert result.id == _COURSE_ID
        assert result.code == "MAT101"


# ===================================================================
# Get: not found (Requirement 6.7)
# ===================================================================


class TestGetCourseNotFound:
    @pytest.mark.anyio
    async def test_get_course_not_found_returns_404(self):
        """Non-existent course_id must raise HTTPException 404."""
        repo = _make_repo()
        repo.obtener_por_id.return_value = None
        service = CourseService(repo)

        with pytest.raises(HTTPException) as exc_info:
            await service.get_course(_COURSE_ID)

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Curso no encontrado"


# ===================================================================
# Update: happy path (Requirement 6.4)
# ===================================================================


class TestUpdateCourseSuccess:
    @pytest.mark.anyio
    async def test_update_course_success(self):
        """A valid partial update must persist and return CourseRead."""
        repo = _make_repo()
        updated_course = _make_course(name="Cálculo Diferencial")
        repo.update.return_value = updated_course
        service = CourseService(repo)

        data = CourseUpdate(name="Cálculo Diferencial")
        result = await service.update_course(_COURSE_ID, data)

        assert isinstance(result, CourseRead)
        assert result.name == "Cálculo Diferencial"
        repo.update.assert_awaited_once_with(_COURSE_ID, data)


# ===================================================================
# Update: not found (Requirement 6.4)
# ===================================================================


class TestUpdateCourseNotFound:
    @pytest.mark.anyio
    async def test_update_course_not_found_returns_404(self):
        """Non-existent course_id must raise HTTPException 404."""
        repo = _make_repo()
        repo.update.return_value = None
        service = CourseService(repo)

        data = CourseUpdate(name="Nuevo Nombre")
        with pytest.raises(HTTPException) as exc_info:
            await service.update_course(_COURSE_ID, data)

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Curso no encontrado"


# ===================================================================
# Update: duplicate code from different course (Requirement 6.5)
# ===================================================================


class TestUpdateCourseDuplicateCode:
    @pytest.mark.anyio
    async def test_update_course_duplicate_code_different_course_returns_409(self):
        """Code belonging to another course must raise 409."""
        repo = _make_repo()
        other_course = _make_course(course_id=_OTHER_COURSE_ID, code="FIS201")
        repo.get_by_code.return_value = other_course
        service = CourseService(repo)

        data = CourseUpdate(code="FIS201")
        with pytest.raises(HTTPException) as exc_info:
            await service.update_course(_COURSE_ID, data)

        assert exc_info.value.status_code == 409
        assert exc_info.value.detail == "El code ya está registrado"
        repo.update.assert_not_awaited()


# ===================================================================
# Update: same code — no conflict (Requirement 6.6)
# ===================================================================


class TestUpdateCourseSameCodeNoConflict:
    @pytest.mark.anyio
    async def test_update_course_same_code_no_conflict(self):
        """Updating a course with its own code must succeed."""
        repo = _make_repo()
        existing_course = _make_course()
        repo.get_by_code.return_value = existing_course
        updated_course = _make_course(name="Cálculo Actualizado")
        repo.update.return_value = updated_course
        service = CourseService(repo)

        data = CourseUpdate(code="MAT101", name="Cálculo Actualizado")
        result = await service.update_course(_COURSE_ID, data)

        assert isinstance(result, CourseRead)
        assert result.name == "Cálculo Actualizado"
        repo.update.assert_awaited_once()


# ===================================================================
# Update status: happy path (Requirement 6.9)
# ===================================================================


class TestUpdateCourseStatusSuccess:
    @pytest.mark.anyio
    async def test_update_course_status_success(self):
        """Status change must persist and return CourseRead."""
        repo = _make_repo()
        updated_course = _make_course(status=CourseStatusEnum.INACTIVE)
        repo.update_status.return_value = updated_course
        service = CourseService(repo)

        result = await service.update_course_status(
            _COURSE_ID, CourseStatusEnum.INACTIVE
        )

        assert isinstance(result, CourseRead)
        assert result.status == CourseStatusEnum.INACTIVE
        repo.update_status.assert_awaited_once_with(
            _COURSE_ID, CourseStatusEnum.INACTIVE
        )


# ===================================================================
# Update status: not found (Requirement 6.9)
# ===================================================================


class TestUpdateCourseStatusNotFound:
    @pytest.mark.anyio
    async def test_update_course_status_not_found_returns_404(self):
        """Non-existent course_id must raise HTTPException 404."""
        repo = _make_repo()
        repo.update_status.return_value = None
        service = CourseService(repo)

        with pytest.raises(HTTPException) as exc_info:
            await service.update_course_status(
                _COURSE_ID, CourseStatusEnum.INACTIVE
            )

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Curso no encontrado"


# ===================================================================
# List: default status ACTIVE (Requirement 6.8)
# ===================================================================


class TestListCoursesDefaultStatusActive:
    @pytest.mark.anyio
    async def test_list_courses_default_status_active(self):
        """When status=None, service must default to ACTIVE."""
        repo = _make_repo()
        course = _make_course()
        repo.list_all.return_value = [course]
        repo.count_all.return_value = 1
        service = CourseService(repo)

        result = await service.list_courses(status=None, skip=0, limit=20)

        assert isinstance(result, PaginatedResponse)
        assert result.total == 1
        assert result.skip == 0
        assert result.limit == 20
        assert len(result.data) == 1

        # Verify that the repo was called with ACTIVE status
        repo.list_all.assert_awaited_once_with(
            skip=0, limit=20, status=CourseStatusEnum.ACTIVE
        )
        repo.count_all.assert_awaited_once_with(
            status=CourseStatusEnum.ACTIVE
        )
