"""
CourseRepository — persistencia de secciones (Course).
Todos los queries hacen JOIN con subjects para devolver CourseRead plano.
"""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.schemas.audit_log import AuditLogCreate
from app.application.schemas.course import CourseRead, CourseUpdate, EvaluationConfigUpdate
from app.domain.enums import CourseStatusEnum, OperationEnum
from app.domain.interfaces.course_repository import ICourseRepository
from app.infrastructure.models.course import Course
from app.infrastructure.models.enrollment import Enrollment
from app.infrastructure.models.student_profile import StudentProfile
from app.infrastructure.models.subject import Subject
from app.infrastructure.models.user import User
from app.infrastructure.repositories.audit_log_repository import AuditLogRepository


def _to_read(course: Course, subject: Subject) -> CourseRead:
    """Combina Course + Subject en un CourseRead plano."""
    evaluation_config = course.evaluation_config
    if not isinstance(evaluation_config, dict):
        evaluation_config = None
    return CourseRead(
        id=course.id,
        subject_id=course.subject_id,
        section=course.section,
        academic_period=course.academic_period,
        professor_id=course.professor_id,
        status=course.status,
        created_at=course.created_at,
        code=subject.code,
        name=subject.name,
        credits=subject.credits,
        program_id=subject.program_id,
        evaluation_config=evaluation_config,
    )


def _base_joined_stmt():
    return select(Course, Subject).join(Subject, Course.subject_id == Subject.id)


class CourseRepository(ICourseRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._audit = AuditLogRepository(session)

    async def create(self, data: dict) -> CourseRead:
        course = Course(**data)
        self._session.add(course)
        await self._session.flush()
        await self._session.refresh(course)
        await self._audit.register(AuditLogCreate(
            table_name="courses",
            operation=OperationEnum.INSERT,
            record_id=course.id,
            new_data={k: str(v) if not isinstance(v, (str, int, float, bool, type(None))) else v
                      for k, v in data.items()},
        ))
        result = await self._session.execute(
            _base_joined_stmt().where(Course.id == course.id)
        )
        row = result.first()
        return _to_read(row[0], row[1])

    async def get_by_id(self, course_id: UUID) -> CourseRead | None:
        result = await self._session.execute(
            _base_joined_stmt().where(Course.id == course_id)
        )
        row = result.first()
        return _to_read(row[0], row[1]) if row else None

    async def get_by_code(self, code: str) -> CourseRead | None:
        result = await self._session.execute(
            _base_joined_stmt().where(Subject.code == code)
        )
        row = result.first()
        return _to_read(row[0], row[1]) if row else None

    async def list_by_subject(self, subject_id: UUID) -> list[CourseRead]:
        result = await self._session.execute(
            _base_joined_stmt().where(Course.subject_id == subject_id)
        )
        return [_to_read(c, s) for c, s in result.all()]

    async def list_by_professor(self, professor_id: UUID) -> list[CourseRead]:
        result = await self._session.execute(
            _base_joined_stmt().where(Course.professor_id == professor_id)
        )
        return [_to_read(c, s) for c, s in result.all()]

    async def list_by_program(self, program_id: UUID) -> list[CourseRead]:
        result = await self._session.execute(
            _base_joined_stmt().where(Subject.program_id == program_id)
        )
        return [_to_read(c, s) for c, s in result.all()]

    async def list_all(
        self,
        skip: int,
        limit: int,
        status: CourseStatusEnum | None = None,
        subject_id: UUID | None = None,
    ) -> list[CourseRead]:
        stmt = _base_joined_stmt()
        if status is not None:
            stmt = stmt.where(Course.status == status)
        if subject_id is not None:
            stmt = stmt.where(Course.subject_id == subject_id)
        stmt = stmt.offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        return [_to_read(c, s) for c, s in result.all()]

    async def count_all(
        self,
        status: CourseStatusEnum | None = None,
        subject_id: UUID | None = None,
    ) -> int:
        stmt = select(func.count()).select_from(Course)
        if status is not None:
            stmt = stmt.where(Course.status == status)
        if subject_id is not None:
            stmt = stmt.where(Course.subject_id == subject_id)
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def update(self, course_id: UUID, data: CourseUpdate) -> CourseRead | None:
        result = await self._session.execute(
            select(Course).where(Course.id == course_id)
        )
        course = result.scalar_one_or_none()
        if course is None:
            return None
        previous = {
            k: str(v) if not isinstance(v, (str, int, float, bool, type(None))) else v
            for k, v in course.model_dump().items()
        }
        updates = data.model_dump(exclude_unset=True)
        for field, value in updates.items():
            setattr(course, field, value)
        self._session.add(course)
        await self._session.flush()
        await self._audit.register(AuditLogCreate(
            table_name="courses",
            operation=OperationEnum.UPDATE,
            record_id=course_id,
            previous_data=previous,
            new_data=updates,
        ))
        return await self.get_by_id(course_id)

    async def update_status(
        self, course_id: UUID, status: CourseStatusEnum
    ) -> CourseRead | None:
        result = await self._session.execute(
            select(Course).where(Course.id == course_id)
        )
        course = result.scalar_one_or_none()
        if course is None:
            return None
        previous_status = course.status
        course.status = status
        self._session.add(course)
        await self._session.flush()
        await self._audit.register(AuditLogCreate(
            table_name="courses",
            operation=OperationEnum.UPDATE,
            record_id=course_id,
            previous_data={"status": previous_status},
            new_data={"status": status},
        ))
        return await self.get_by_id(course_id)

    async def save_evaluation_config(
        self, course_id: UUID, config: dict
    ) -> CourseRead | None:
        result = await self._session.execute(
            select(Course).where(Course.id == course_id)
        )
        course = result.scalar_one_or_none()
        if course is None:
            return None
        course.evaluation_config = config
        self._session.add(course)
        await self._session.flush()
        return await self.get_by_id(course_id)

    async def list_enrolled_students(self, course_id: UUID) -> list[User]:
        from sqlalchemy.orm import selectinload  # lazy import para evitar ciclos
        stmt = (
            select(User)
            .join(Enrollment, Enrollment.student_id == User.id)
            .where(Enrollment.course_id == course_id)
        )
        result = await self._session.execute(stmt)
        users = list(result.scalars().all())

        # Enriquecer con student_institutional_id desde StudentProfile
        if users:
            user_ids = [u.id for u in users]
            profiles_stmt = select(StudentProfile).where(StudentProfile.user_id.in_(user_ids))
            profiles_result = await self._session.execute(profiles_stmt)
            profiles_map = {p.user_id: p.student_institutional_id for p in profiles_result.scalars().all()}
            for user in users:
                # Asignar como atributo dinámico — UserRead lo leerá via from_attributes
                user.__dict__['student_institutional_id'] = profiles_map.get(user.id)

        return users

    # --- Compatibilidad con código legacy ---

    async def obtener_por_id(self, id: UUID) -> CourseRead | None:
        return await self.get_by_id(id)

    async def crear(self, data) -> CourseRead:
        payload = data.model_dump() if hasattr(data, "model_dump") else dict(data)
        return await self.create(payload)

    async def listar_por_docente(self, docente_id: UUID) -> list[CourseRead]:
        return await self.list_by_professor(docente_id)

    async def listar_estudiantes_inscritos(self, course_id: UUID) -> list[User]:
        return await self.list_enrolled_students(course_id)

    async def listar_por_programa(self, program_id: UUID) -> list[CourseRead]:
        return await self.list_by_program(program_id)
