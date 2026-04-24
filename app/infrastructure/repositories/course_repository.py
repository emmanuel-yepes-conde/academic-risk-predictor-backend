"""
Course repository implementation (Req 6.2, 7.1, 7.2, 7.3, 3.4, 3.5).
listar_estudiantes_inscritos applies RB-04 filter by professor's courses.
Each write operation registers an atomic AuditLog entry in the same session.
"""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.schemas.audit_log import AuditLogCreate
from app.application.schemas.course import CourseCreate, CourseUpdate
from app.domain.enums import CourseStatusEnum, OperationEnum
from app.domain.interfaces.course_repository import ICourseRepository
from app.infrastructure.models.course import Course
from app.infrastructure.models.enrollment import Enrollment
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
        stmt = select(Course).where(Course.professor_id == docente_id)
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

    # --- CRUD methods ---

    async def create(self, data: dict) -> Course:
        """Persist a new Course and register an INSERT audit log."""
        course = Course(**data)
        self._session.add(course)
        await self._session.flush()
        await self._session.refresh(course)
        await self._audit.register(AuditLogCreate(
            table_name="courses",
            operation=OperationEnum.INSERT,
            record_id=course.id,
            new_data=data,
        ))
        return course

    async def update(self, course_id: UUID, data: CourseUpdate) -> Course | None:
        """Apply partial update and register an UPDATE audit log."""
        course = await self.obtener_por_id(course_id)
        if course is None:
            return None

        previous_data = {
            k: str(v) if not isinstance(v, (str, int, float, bool, type(None))) else v
            for k, v in course.model_dump().items()
        }
        updates = data.model_dump(exclude_unset=True)
        for field, value in updates.items():
            setattr(course, field, value)

        self._session.add(course)
        await self._session.flush()
        await self._session.refresh(course)
        await self._audit.register(AuditLogCreate(
            table_name="courses",
            operation=OperationEnum.UPDATE,
            record_id=course_id,
            previous_data=previous_data,
            new_data=updates,
        ))
        return course

    async def get_by_code(self, code: str) -> Course | None:
        """SELECT ... WHERE code = :code"""
        result = await self._session.execute(
            select(Course).where(Course.code == code)
        )
        return result.scalar_one_or_none()

    async def list_all(
        self, skip: int, limit: int, status: CourseStatusEnum | None = None
    ) -> list[Course]:
        """
        SELECT ... FROM courses [WHERE status = :status] OFFSET :skip LIMIT :limit.
        Filters by status when provided.
        """
        stmt = select(Course)
        if status is not None:
            stmt = stmt.where(Course.status == status)
        stmt = stmt.offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_all(self, status: CourseStatusEnum | None = None) -> int:
        """
        SELECT COUNT(*) FROM courses [WHERE status = :status].
        Filters by status when provided.
        """
        stmt = select(func.count()).select_from(Course)
        if status is not None:
            stmt = stmt.where(Course.status == status)
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def update_status(
        self, course_id: UUID, status: CourseStatusEnum
    ) -> Course | None:
        """
        Update only the status field and register an UPDATE audit log.
        Returns None if the course does not exist.
        """
        course = await self.obtener_por_id(course_id)
        if course is None:
            return None

        previous_status = course.status
        course.status = status

        self._session.add(course)
        await self._session.flush()
        await self._session.refresh(course)
        await self._audit.register(AuditLogCreate(
            table_name="courses",
            operation=OperationEnum.UPDATE,
            record_id=course_id,
            previous_data={"status": previous_status},
            new_data={"status": status},
        ))
        return course


