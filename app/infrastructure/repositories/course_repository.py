"""
Course repository implementation (Req 6.2, 7.1, 7.2, 7.3, 3.4, 3.5).
listar_estudiantes_inscritos applies RB-04 filter by professor's courses.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.schemas.audit_log import AuditLogCreate
from app.application.schemas.course import CourseCreate
from app.domain.enums import OperationEnum
from app.domain.interfaces.course_repository import ICourseRepository
from app.infrastructure.models.course import Course
from app.infrastructure.models.enrollment import Enrollment
from app.infrastructure.models.professor_course import ProfessorCourse
from app.infrastructure.models.program import Program
from app.infrastructure.models.user import User
from app.infrastructure.repositories.audit_log_repository import AuditLogRepository


class CourseRepository(ICourseRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._audit = AuditLogRepository(session)

    async def crear(self, asignatura: CourseCreate) -> Course:
        course = Course(**asignatura.model_dump())
        self._session.add(course)
        await self._session.flush()
        await self._session.refresh(course)
        await self._audit.register(AuditLogCreate(
            table_name="courses",
            operation=OperationEnum.INSERT,
            record_id=course.id,
            new_data=asignatura.model_dump(),
        ))
        return course

    async def obtener_por_id(self, id: UUID) -> Course | None:
        result = await self._session.execute(select(Course).where(Course.id == id))
        return result.scalar_one_or_none()

    async def listar_por_docente(self, docente_id: UUID) -> list[Course]:
        """Return all courses assigned to the given professor."""
        stmt = (
            select(Course)
            .join(ProfessorCourse, ProfessorCourse.course_id == Course.id)
            .where(ProfessorCourse.professor_id == docente_id)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def listar_estudiantes_inscritos(self, course_id: UUID) -> list[User]:
        """
        Return students enrolled in the given course (RB-04).
        Only students with an active Enrollment record are returned.
        """
        stmt = (
            select(User)
            .join(Enrollment, Enrollment.student_id == User.id)
            .where(Enrollment.course_id == course_id)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def listar_por_programa(self, program_id: UUID) -> list[Course]:
        """Return all courses belonging to the given program (Req 3.4)."""
        stmt = select(Course).where(Course.program_id == program_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def listar_por_universidad_y_programa(
        self, university_id: UUID, program_id: UUID
    ) -> list[Course]:
        """
        Return courses for a program that belongs to the given university (Req 3.5).
        Validates the university→program hierarchy by joining through Program.
        """
        stmt = (
            select(Course)
            .join(Program, Program.id == Course.program_id)
            .where(
                Program.id == program_id,
                Program.university_id == university_id,
            )
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def listar_por_campus_y_programa(
        self, campus_id: UUID, program_id: UUID
    ) -> list[Course]:
        """
        Return courses for a program that belongs to the given campus (Req 4.2).
        Validates the campus→program hierarchy by joining through Program.
        """
        stmt = (
            select(Course)
            .join(Program, Program.id == Course.program_id)
            .where(
                Program.id == program_id,
                Program.campus_id == campus_id,
            )
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
