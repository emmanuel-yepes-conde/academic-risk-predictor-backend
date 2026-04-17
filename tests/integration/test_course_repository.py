"""
Integration tests for CourseRepository (Req 6.2).

Covers: crear, obtener_por_id, listar_por_docente,
        listar_estudiantes_inscritos, and not-found cases.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.application.schemas.course import CourseCreate
from app.domain.enums import RoleEnum
from app.infrastructure.models.course import Course
from app.infrastructure.models.enrollment import Enrollment
from app.infrastructure.models.professor_course import ProfessorCourse
from app.infrastructure.models.user import User
from app.infrastructure.repositories.course_repository import CourseRepository

from tests.integration.conftest import make_mock_session, now


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _course_create(**kwargs) -> CourseCreate:
    defaults = dict(
        code=f"CS{uuid.uuid4().hex[:4].upper()}",
        name="Integration Course",
        credits=3,
        academic_period="2024-1",
        program_id=uuid.uuid4(),
    )
    defaults.update(kwargs)
    return CourseCreate(**defaults)


def _make_student(**kwargs) -> User:
    defaults = dict(
        id=uuid.uuid4(),
        email=f"s_{uuid.uuid4().hex[:8]}@test.com",
        full_name="Student",
        role=RoleEnum.STUDENT,
        ml_consent=False,
        created_at=now(),
        updated_at=now(),
    )
    defaults.update(kwargs)
    return User(**defaults)


def _make_professor(**kwargs) -> User:
    defaults = dict(
        id=uuid.uuid4(),
        email=f"p_{uuid.uuid4().hex[:8]}@test.com",
        full_name="Professor",
        role=RoleEnum.PROFESSOR,
        ml_consent=False,
        created_at=now(),
        updated_at=now(),
    )
    defaults.update(kwargs)
    return User(**defaults)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_crear_and_obtener_por_id():
    """crear() persists course; obtener_por_id() returns it with matching fields."""
    session = make_mock_session()
    repo = CourseRepository(session=session)

    data = _course_create(name="Algorithms", credits=4)
    created = await repo.crear(data)

    assert created.code == data.code
    assert created.name == data.name
    assert created.credits == data.credits
    assert created.academic_period == data.academic_period

    fetched = await repo.obtener_por_id(created.id)
    assert fetched is not None
    assert fetched.id == created.id


@pytest.mark.anyio
async def test_obtener_por_id_not_found():
    """obtener_por_id() returns None for an unknown UUID."""
    async def _empty_execute(stmt, *args, **kwargs):
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        result.scalars.return_value.all.return_value = []
        return result

    session = make_mock_session()
    session.execute = AsyncMock(side_effect=_empty_execute)
    repo = CourseRepository(session=session)

    result = await repo.obtener_por_id(uuid.uuid4())
    assert result is None


@pytest.mark.anyio
async def test_listar_por_docente():
    """listar_por_docente() returns courses assigned to the given professor."""
    professor = _make_professor()
    course = Course(
        id=uuid.uuid4(),
        code="MAT101",
        name="Calculus",
        credits=4,
        academic_period="2024-1",
        created_at=now(),
    )

    async def _execute(stmt, *args, **kwargs):
        result = MagicMock()
        result.scalar_one_or_none.return_value = course
        result.scalars.return_value.all.return_value = [course]
        return result

    session = make_mock_session()
    session.execute = AsyncMock(side_effect=_execute)
    repo = CourseRepository(session=session)

    courses = await repo.listar_por_docente(professor.id)
    assert len(courses) == 1
    assert courses[0].id == course.id


@pytest.mark.anyio
async def test_listar_por_docente_empty():
    """listar_por_docente() returns empty list when professor has no courses."""
    async def _empty_execute(stmt, *args, **kwargs):
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        result.scalars.return_value.all.return_value = []
        return result

    session = make_mock_session()
    session.execute = AsyncMock(side_effect=_empty_execute)
    repo = CourseRepository(session=session)

    courses = await repo.listar_por_docente(uuid.uuid4())
    assert courses == []


@pytest.mark.anyio
async def test_listar_estudiantes_inscritos():
    """listar_estudiantes_inscritos() returns students enrolled in the course."""
    student = _make_student(full_name="Enrolled Student")
    course_id = uuid.uuid4()

    async def _execute(stmt, *args, **kwargs):
        result = MagicMock()
        result.scalar_one_or_none.return_value = student
        result.scalars.return_value.all.return_value = [student]
        return result

    session = make_mock_session()
    session.execute = AsyncMock(side_effect=_execute)
    repo = CourseRepository(session=session)

    students = await repo.listar_estudiantes_inscritos(course_id)
    assert len(students) == 1
    assert students[0].full_name == "Enrolled Student"


@pytest.mark.anyio
async def test_listar_estudiantes_inscritos_empty():
    """listar_estudiantes_inscritos() returns empty list when no enrollments."""
    async def _empty_execute(stmt, *args, **kwargs):
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        result.scalars.return_value.all.return_value = []
        return result

    session = make_mock_session()
    session.execute = AsyncMock(side_effect=_empty_execute)
    repo = CourseRepository(session=session)

    students = await repo.listar_estudiantes_inscritos(uuid.uuid4())
    assert students == []
