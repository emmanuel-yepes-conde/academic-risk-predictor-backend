"""
Integration tests for CourseRepository (Req 6.2) and
ProfessorCourseService (Req 7.1–7.6).

Covers: crear, obtener_por_id, listar_por_docente,
        listar_estudiantes_inscritos, and not-found cases.
Service-level: assign_professor, get_course_professor,
        list_professor_courses, list_course_students (RB-04).
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.application.schemas.course import CourseCreate, CourseRead
from app.application.schemas.professor_course import ProfessorAssignmentRead
from app.application.schemas.user import UserRead
from app.application.services.professor_course_service import ProfessorCourseService
from app.domain.enums import RoleEnum, UserStatusEnum
from app.infrastructure.models.course import Course
from app.infrastructure.models.enrollment import Enrollment
from app.infrastructure.models.subject import Subject
from app.infrastructure.models.user import User
from app.infrastructure.repositories.course_repository import CourseRepository

from tests.integration.conftest import make_mock_session, now


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _course_create(**kwargs) -> CourseCreate:
    subject_id = kwargs.pop("subject_id", uuid.uuid4())
    defaults = dict(
        subject_id=subject_id,
        section="A",
        academic_period="2024-1",
    )
    defaults.update(kwargs)
    return CourseCreate(**defaults)


def _make_subject(**kwargs) -> Subject:
    defaults = dict(
        id=uuid.uuid4(),
        code=f"CS{uuid.uuid4().hex[:4].upper()}",
        name="Integration Course",
        credits=3,
        program_id=uuid.uuid4(),
        created_at=now(),
    )
    defaults.update(kwargs)
    return Subject(**defaults)


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

    subject = _make_subject(name="Algorithms", credits=4)
    data = _course_create(subject_id=subject.id)

    async def _execute(stmt, *args, **kwargs):
        result = MagicMock()
        course = next(o for o in session._added if isinstance(o, Course))
        result.first.return_value = (course, subject)
        return result

    session.execute = AsyncMock(side_effect=_execute)
    created = await repo.crear(data)

    assert created.subject_id == data.subject_id
    assert created.code == subject.code
    assert created.name == subject.name
    assert created.credits == subject.credits
    assert created.academic_period == data.academic_period

    fetched = await repo.obtener_por_id(created.id)
    assert fetched is not None
    assert fetched.id == created.id


@pytest.mark.anyio
async def test_obtener_por_id_not_found():
    """obtener_por_id() returns None for an unknown UUID."""
    async def _empty_execute(stmt, *args, **kwargs):
        result = MagicMock()
        result.first.return_value = None
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
        subject_id=uuid.uuid4(),
        section="A",
        academic_period="2024-1",
        professor_id=professor.id,
        created_at=now(),
    )
    subject = _make_subject(id=course.subject_id, code="MAT101", name="Calculus", credits=4)

    async def _execute(stmt, *args, **kwargs):
        result = MagicMock()
        result.all.return_value = [(course, subject)]
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


# ---------------------------------------------------------------------------
# ProfessorCourseService integration tests (Req 7.1–7.6)
# ---------------------------------------------------------------------------

def _make_course_with_professor(professor_id: uuid.UUID | None = None, **kwargs) -> Course:
    """Create a Course instance with optional professor_id."""
    defaults = dict(
        id=uuid.uuid4(),
        subject_id=uuid.uuid4(),
        section="A",
        academic_period="2024-1",
        professor_id=professor_id,
        created_at=now(),
    )
    defaults.update(kwargs)
    return Course(**defaults)


def _make_professor_user(**kwargs) -> User:
    """Create a User with PROFESSOR role and all required fields."""
    defaults = dict(
        id=uuid.uuid4(),
        email=f"prof_{uuid.uuid4().hex[:8]}@test.com",
        full_name="Test Professor",
        role=RoleEnum.PROFESSOR,
        status=UserStatusEnum.ACTIVE,
        ml_consent=False,
        created_at=now(),
        updated_at=now(),
    )
    defaults.update(kwargs)
    return User(**defaults)


def _make_student_user(**kwargs) -> User:
    """Create a User with STUDENT role and all required fields."""
    defaults = dict(
        id=uuid.uuid4(),
        email=f"stu_{uuid.uuid4().hex[:8]}@test.com",
        full_name="Test Student",
        role=RoleEnum.STUDENT,
        status=UserStatusEnum.ACTIVE,
        ml_consent=False,
        created_at=now(),
        updated_at=now(),
    )
    defaults.update(kwargs)
    return User(**defaults)


@pytest.mark.anyio
async def test_assign_professor_returns_professor_assignment_read():
    """
    assign_professor returns ProfessorAssignmentRead with {id, professor_id, course_id}.
    Validates: Requirements 7.1, 7.6
    """
    professor = _make_professor_user()
    course = _make_course_with_professor(professor_id=None)

    call_count = 0

    async def _execute(stmt, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        result = MagicMock()
        if call_count == 1:
            # First call: obtener_por_id (course lookup)
            result.scalar_one_or_none.return_value = course
        elif call_count == 2:
            # Second call: professor lookup (User query)
            result.scalar_one_or_none.return_value = professor
        else:
            # Subsequent calls: audit log flush/refresh
            result.scalar_one_or_none.return_value = None
            result.scalars.return_value.all.return_value = []
        return result

    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.execute = AsyncMock(side_effect=_execute)

    service = ProfessorCourseService(session)
    assignment = await service.assign_professor(course.id, professor.id)

    assert isinstance(assignment, ProfessorAssignmentRead)
    assert assignment.id == course.id
    assert assignment.professor_id == professor.id
    assert assignment.course_id == course.id


@pytest.mark.anyio
async def test_get_course_professor_returns_user_read():
    """
    get_course_professor returns UserRead with correct professor data.
    Validates: Requirements 7.2
    """
    professor = _make_professor_user()
    course = _make_course_with_professor(professor_id=professor.id)

    call_count = 0

    async def _execute(stmt, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        result = MagicMock()
        if call_count == 1:
            # First call: obtener_por_id (course lookup)
            result.scalar_one_or_none.return_value = course
        elif call_count == 2:
            # Second call: professor user lookup
            result.scalar_one_or_none.return_value = professor
        else:
            result.scalar_one_or_none.return_value = None
        return result

    session = AsyncMock()
    session.execute = AsyncMock(side_effect=_execute)

    service = ProfessorCourseService(session)
    user_read = await service.get_course_professor(course.id)

    assert isinstance(user_read, UserRead)
    assert user_read.id == professor.id
    assert user_read.email == professor.email
    assert user_read.full_name == professor.full_name
    assert user_read.role == RoleEnum.PROFESSOR


@pytest.mark.anyio
async def test_list_professor_courses_returns_course_read_with_professor_id():
    """
    list_professor_courses returns list[CourseRead] with professor_id included.
    Validates: Requirements 7.3, 7.5
    """
    professor = _make_professor_user()
    course1 = _make_course_with_professor(professor_id=professor.id, section="A")
    course2 = _make_course_with_professor(professor_id=professor.id, section="B")
    subject1 = _make_subject(id=course1.subject_id, name="Calculus")
    subject2 = _make_subject(id=course2.subject_id, name="Algebra")

    async def _execute(stmt, *args, **kwargs):
        result = MagicMock()
        result.all.return_value = [(course1, subject1), (course2, subject2)]
        return result

    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.execute = AsyncMock(side_effect=_execute)

    service = ProfessorCourseService(session)
    courses = await service.list_professor_courses(professor.id)

    assert len(courses) == 2
    assert all(isinstance(c, CourseRead) for c in courses)
    assert all(c.professor_id == professor.id for c in courses)
    assert courses[0].name == "Calculus"
    assert courses[1].name == "Algebra"


@pytest.mark.anyio
async def test_list_course_students_assigned_professor_succeeds():
    """
    list_course_students with assigned professor succeeds (RB-04 positive).
    Validates: Requirements 7.4
    """
    professor = _make_professor_user()
    course = _make_course_with_professor(professor_id=professor.id)
    student1 = _make_student_user(full_name="Alice")
    student2 = _make_student_user(full_name="Bob")

    call_count = 0

    async def _execute(stmt, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        result = MagicMock()
        if call_count == 1:
            # First call: verify_professor_assigned_to_course → obtener_por_id
            result.scalar_one_or_none.return_value = course
        elif call_count == 2:
            # Second call: listar_estudiantes_inscritos
            result.scalars.return_value.all.return_value = [student1, student2]
        else:
            result.scalar_one_or_none.return_value = None
            result.scalars.return_value.all.return_value = []
        return result

    session = AsyncMock()
    session.execute = AsyncMock(side_effect=_execute)

    service = ProfessorCourseService(session)
    students = await service.list_course_students(course.id, professor.id)

    assert len(students) == 2
    assert all(isinstance(s, UserRead) for s in students)
    assert students[0].full_name == "Alice"
    assert students[1].full_name == "Bob"


@pytest.mark.anyio
async def test_list_course_students_unassigned_professor_raises_403():
    """
    list_course_students with unassigned professor raises 403 (RB-04 negative).
    Validates: Requirements 7.4
    """
    from fastapi import HTTPException

    assigned_professor = _make_professor_user()
    other_professor = _make_professor_user()
    course = _make_course_with_professor(professor_id=assigned_professor.id)

    async def _execute(stmt, *args, **kwargs):
        result = MagicMock()
        # verify_professor_assigned_to_course → obtener_por_id returns course
        # whose professor_id != other_professor.id → 403
        result.scalar_one_or_none.return_value = course
        return result

    session = AsyncMock()
    session.execute = AsyncMock(side_effect=_execute)

    service = ProfessorCourseService(session)

    with pytest.raises(HTTPException) as exc_info:
        await service.list_course_students(course.id, other_professor.id)

    assert exc_info.value.status_code == 403
    assert "No tiene permiso" in exc_info.value.detail
