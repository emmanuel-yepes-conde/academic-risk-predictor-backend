"""
Unit tests for Course model and related schemas after professor-course simplification.

Validates: Requirements 1.4, 10.1, 10.2, 3.3

These are structural tests — they verify the fields exist with the correct types
after the simplification that moved professor_id directly into the Course model
and removed the ProfessorCourse intermediate table.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from app.infrastructure.models.course import Course
from app.application.schemas.course import CourseCreate, CourseRead
from app.application.schemas.professor_course import ProfessorAssignmentRead


class TestCourseModelProfessorId:
    """Verify Course ORM model has professor_id field (Req 1.4)."""

    def test_course_model_has_professor_id_field(self):
        """Course model must declare a professor_id field."""
        assert "professor_id" in Course.model_fields

    def test_professor_id_is_nullable(self):
        """professor_id must accept None (nullable FK)."""
        course = Course(
            id=uuid.uuid4(),
            code="CS101",
            name="Intro to CS",
            credits=3,
            academic_period="2025-1",
            program_id=uuid.uuid4(),
            professor_id=None,
            created_at=datetime.now(timezone.utc),
        )
        assert course.professor_id is None

    def test_professor_id_accepts_uuid(self):
        """professor_id must accept a valid UUID value."""
        prof_id = uuid.uuid4()
        course = Course(
            id=uuid.uuid4(),
            code="CS102",
            name="Data Structures",
            credits=4,
            academic_period="2025-1",
            program_id=uuid.uuid4(),
            professor_id=prof_id,
            created_at=datetime.now(timezone.utc),
        )
        assert course.professor_id == prof_id

    def test_professor_id_default_is_none(self):
        """professor_id should default to None when not provided."""
        course = Course(
            id=uuid.uuid4(),
            code="CS103",
            name="Algorithms",
            credits=3,
            academic_period="2025-1",
            program_id=uuid.uuid4(),
            created_at=datetime.now(timezone.utc),
        )
        assert course.professor_id is None


class TestCourseReadSchema:
    """Verify CourseRead schema includes professor_id (Req 10.1)."""

    def test_course_read_has_professor_id_field(self):
        """CourseRead must declare a professor_id field."""
        assert "professor_id" in CourseRead.model_fields

    def test_course_read_professor_id_accepts_none(self):
        """CourseRead.professor_id must accept None."""
        from app.domain.enums import CourseStatusEnum

        data = CourseRead(
            id=uuid.uuid4(),
            code="CS101",
            name="Intro to CS",
            credits=3,
            academic_period="2025-1",
            program_id=uuid.uuid4(),
            professor_id=None,
            status=CourseStatusEnum.ACTIVE,
            created_at=datetime.now(timezone.utc),
        )
        assert data.professor_id is None

    def test_course_read_professor_id_accepts_uuid(self):
        """CourseRead.professor_id must accept a UUID."""
        from app.domain.enums import CourseStatusEnum

        prof_id = uuid.uuid4()
        data = CourseRead(
            id=uuid.uuid4(),
            code="CS101",
            name="Intro to CS",
            credits=3,
            academic_period="2025-1",
            program_id=uuid.uuid4(),
            professor_id=prof_id,
            status=CourseStatusEnum.ACTIVE,
            created_at=datetime.now(timezone.utc),
        )
        assert data.professor_id == prof_id

    def test_course_read_serializes_professor_id(self):
        """CourseRead must include professor_id in serialized output."""
        from app.domain.enums import CourseStatusEnum

        prof_id = uuid.uuid4()
        data = CourseRead(
            id=uuid.uuid4(),
            code="CS101",
            name="Intro to CS",
            credits=3,
            academic_period="2025-1",
            program_id=uuid.uuid4(),
            professor_id=prof_id,
            status=CourseStatusEnum.ACTIVE,
            created_at=datetime.now(timezone.utc),
        )
        dumped = data.model_dump()
        assert "professor_id" in dumped
        assert dumped["professor_id"] == prof_id


class TestCourseCreateSchema:
    """Verify CourseCreate does NOT include professor_id (Req 10.2)."""

    def test_course_create_does_not_have_professor_id(self):
        """CourseCreate must not declare a professor_id field."""
        assert "professor_id" not in CourseCreate.model_fields

    def test_course_create_ignores_professor_id_in_input(self):
        """CourseCreate must ignore professor_id even if provided in input data."""
        data = CourseCreate(
            code="CS101",
            name="Intro to CS",
            credits=3,
            academic_period="2025-1",
            program_id=uuid.uuid4(),
            professor_id=uuid.uuid4(),  # type: ignore[call-arg]
        )
        dumped = data.model_dump()
        assert "professor_id" not in dumped


class TestProfessorAssignmentReadSchema:
    """Verify ProfessorAssignmentRead has fields id, professor_id, course_id (Req 3.3)."""

    def test_has_id_field(self):
        """ProfessorAssignmentRead must have an 'id' field."""
        assert "id" in ProfessorAssignmentRead.model_fields

    def test_has_professor_id_field(self):
        """ProfessorAssignmentRead must have a 'professor_id' field."""
        assert "professor_id" in ProfessorAssignmentRead.model_fields

    def test_has_course_id_field(self):
        """ProfessorAssignmentRead must have a 'course_id' field."""
        assert "course_id" in ProfessorAssignmentRead.model_fields

    def test_all_fields_are_uuid(self):
        """All three fields must accept UUID values."""
        assignment = ProfessorAssignmentRead(
            id=uuid.uuid4(),
            professor_id=uuid.uuid4(),
            course_id=uuid.uuid4(),
        )
        assert isinstance(assignment.id, uuid.UUID)
        assert isinstance(assignment.professor_id, uuid.UUID)
        assert isinstance(assignment.course_id, uuid.UUID)

    def test_serialization_includes_all_fields(self):
        """Serialized output must include id, professor_id, and course_id."""
        assignment = ProfessorAssignmentRead(
            id=uuid.uuid4(),
            professor_id=uuid.uuid4(),
            course_id=uuid.uuid4(),
        )
        dumped = assignment.model_dump()
        assert set(dumped.keys()) == {"id", "professor_id", "course_id"}


class TestProfessorCourseReadRemoved:
    """Verify ProfessorCourseRead no longer exists in professor_course module (Req 3.3)."""

    def test_professor_course_read_not_in_module(self):
        """ProfessorCourseRead must not be importable from professor_course schemas."""
        import app.application.schemas.professor_course as pc_module

        assert not hasattr(pc_module, "ProfessorCourseRead")

    def test_professor_course_read_not_importable(self):
        """Attempting to import ProfessorCourseRead should raise ImportError."""
        with pytest.raises(ImportError):
            from app.application.schemas.professor_course import ProfessorCourseRead  # noqa: F401
