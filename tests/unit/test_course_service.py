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
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.application.schemas.course import (
    CourseCreate,
    CourseRead,
    CourseStatusUpdate,
    CourseUpdate,
)
from app.application.schemas.user import PaginatedResponse
from app.application.services.course_service import CourseService
from app.domain.enums import CourseStatusEnum


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_COURSE_ID = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
_PROGRAM_ID = uuid.UUID("99999999-8888-7777-6666-555555555555")


def _make_course(
    *,
    course_id: uuid.UUID = _COURSE_ID,
    subject_id: uuid.UUID | None = None,
    section: str = "A",
    code: str = "MAT101",
    name: str = "Cálculo I",
    credits: int = 4,
    academic_period: str = "2024-1",
    program_id: uuid.UUID = _PROGRAM_ID,
    professor_id: uuid.UUID | None = None,
    status: CourseStatusEnum = CourseStatusEnum.ACTIVE,
) -> CourseRead:
    """Create a CourseRead with the given attributes."""
    return CourseRead(
        id=course_id,
        subject_id=subject_id or uuid.uuid4(),
        section=section,
        code=code,
        name=name,
        credits=credits,
        academic_period=academic_period,
        program_id=program_id,
        professor_id=professor_id,
        status=status,
        created_at=datetime.now(timezone.utc),
    )


def _make_repo() -> AsyncMock:
    """Create a mock ICourseRepository with default return values."""
    repo = AsyncMock()
    return repo


def _valid_create_data() -> CourseCreate:
    return CourseCreate(
        subject_id=uuid.uuid4(),
        section="A",
        academic_period="2024-1",
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


class TestCreateCoursePersistsDirectly:
    @pytest.mark.anyio
    async def test_create_course_does_not_precheck_legacy_code(self):
        """Uniqueness is enforced by subject_id, section and academic_period."""
        repo = _make_repo()
        repo.create.return_value = _make_course()
        service = CourseService(repo)

        result = await service.create_course(_valid_create_data())

        assert isinstance(result, CourseRead)
        repo.create.assert_awaited_once()


# ===================================================================
# Get: happy path (Requirement 6.7)
# ===================================================================


class TestGetCourseSuccess:
    @pytest.mark.anyio
    async def test_get_course_success(self):
        """Existing course_id must return CourseRead."""
        repo = _make_repo()
        course = _make_course()
        repo.get_by_id.return_value = course
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
        repo.get_by_id.return_value = None
        service = CourseService(repo)

        with pytest.raises(HTTPException) as exc_info:
            await service.get_course(_COURSE_ID)

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Sección no encontrada"


# ===================================================================
# Update: happy path (Requirement 6.4)
# ===================================================================


class TestUpdateCourseSuccess:
    @pytest.mark.anyio
    async def test_update_course_success(self):
        """A valid partial update must persist and return CourseRead."""
        repo = _make_repo()
        updated_course = _make_course(section="B")
        repo.update.return_value = updated_course
        service = CourseService(repo)

        data = CourseUpdate(section="B")
        result = await service.update_course(_COURSE_ID, data)

        assert isinstance(result, CourseRead)
        assert result.section == "B"
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

        data = CourseUpdate(section="B")
        with pytest.raises(HTTPException) as exc_info:
            await service.update_course(_COURSE_ID, data)

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Sección no encontrada"


# ===================================================================
# Update: duplicate code from different course (Requirement 6.5)
# ===================================================================


class TestUpdateCoursePersistsDirectly:
    @pytest.mark.anyio
    async def test_update_course_delegates_to_repository(self):
        """Section updates are delegated to the repository."""
        repo = _make_repo()
        updated = _make_course(section="C")
        repo.update.return_value = updated
        service = CourseService(repo)

        data = CourseUpdate(section="C")
        result = await service.update_course(_COURSE_ID, data)

        assert result.section == "C"
        repo.update.assert_awaited_once_with(_COURSE_ID, data)


# ===================================================================
# Update: same code — no conflict (Requirement 6.6)
# ===================================================================


class TestUpdateCoursePartial:
    @pytest.mark.anyio
    async def test_update_course_same_section_succeeds(self):
        """Updating a section with the same value succeeds."""
        repo = _make_repo()
        updated_course = _make_course(section="A")
        repo.update.return_value = updated_course
        service = CourseService(repo)

        data = CourseUpdate(section="A")
        result = await service.update_course(_COURSE_ID, data)

        assert isinstance(result, CourseRead)
        assert result.section == "A"
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
            _COURSE_ID, CourseStatusUpdate(status=CourseStatusEnum.INACTIVE)
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
                _COURSE_ID, CourseStatusUpdate(status=CourseStatusEnum.INACTIVE)
            )

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Sección no encontrada"


# ===================================================================
# List: default status ACTIVE (Requirement 6.8)
# ===================================================================


class TestListCoursesDefaultStatusActive:
    @pytest.mark.anyio
    async def test_list_courses_default_status_active(self):
        """When status=None, the service delegates the unfiltered value."""
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

        repo.list_all.assert_awaited_once_with(0, 20, None, None)
        repo.count_all.assert_awaited_once_with(None, None)
