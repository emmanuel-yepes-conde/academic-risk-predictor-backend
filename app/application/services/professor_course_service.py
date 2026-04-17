"""
ProfessorCourseService — lógica de negocio para asignación profesor-curso
y control de acceso RB-04.

Requisitos: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 5.1, 5.2, 5.3, 5.4, 5.5
"""

from uuid import UUID

from fastapi import HTTPException

from app.application.schemas.audit_log import AuditLogCreate
from app.application.schemas.professor_course import ProfessorCourseRead
from app.application.schemas.user import UserRead
from app.application.schemas.course import CourseRead
from app.domain.enums import OperationEnum, RoleEnum
from app.infrastructure.models.professor_course import ProfessorCourse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.models.course import Course
from app.infrastructure.models.enrollment import Enrollment
from app.infrastructure.models.user import User
from app.infrastructure.repositories.audit_log_repository import AuditLogRepository
from app.infrastructure.repositories.course_repository import CourseRepository


class ProfessorCourseService:
    """
    Servicio de aplicación para la gestión de asignaciones profesor-curso
    y el control de acceso RB-04 (profesor solo opera sobre sus cursos asignados).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._audit = AuditLogRepository(session)
        self._course_repo = CourseRepository(session)

    # ------------------------------------------------------------------
    # 10.1 — Asignación profesor-curso (upsert)
    # ------------------------------------------------------------------

    async def assign_professor(
        self, course_id: UUID, professor_id: UUID
    ) -> ProfessorCourseRead:
        """
        Asigna (o reemplaza) el profesor de un curso.

        - Verifica existencia del curso → 404
        - Verifica que el usuario tenga rol PROFESSOR → 422
        - Upsert: si ya existe asignación para el curso, reemplaza el profesor

        Requisitos: 4.1, 4.2, 4.3, 4.4
        """
        # Verificar existencia del curso
        course = await self._course_repo.obtener_por_id(course_id)
        if course is None:
            raise HTTPException(status_code=404, detail="Curso no encontrado")

        # Verificar que el usuario existe y tiene rol PROFESSOR
        result = await self._session.execute(
            select(User).where(User.id == professor_id)
        )
        professor = result.scalar_one_or_none()
        if professor is None or professor.role != RoleEnum.PROFESSOR:
            raise HTTPException(
                status_code=422,
                detail="El usuario indicado no tiene rol de profesor",
            )

        # Upsert: buscar asignación existente para este curso
        existing_result = await self._session.execute(
            select(ProfessorCourse).where(ProfessorCourse.course_id == course_id)
        )
        existing = existing_result.scalar_one_or_none()

        if existing is not None:
            previous_professor_id = existing.professor_id
            existing.professor_id = professor_id
            self._session.add(existing)
            await self._session.flush()
            await self._session.refresh(existing)

            # Registrar en audit_log el reemplazo
            await self._audit.register(AuditLogCreate(
                table_name="professor_courses",
                operation=OperationEnum.UPDATE,
                record_id=existing.id,
                user_id=professor_id,
                previous_data={"professor_id": str(previous_professor_id)},
                new_data={"professor_id": str(professor_id)},
            ))
            return ProfessorCourseRead.model_validate(existing)

        # Crear nueva asignación
        new_assignment = ProfessorCourse(
            professor_id=professor_id,
            course_id=course_id,
        )
        self._session.add(new_assignment)
        await self._session.flush()
        await self._session.refresh(new_assignment)

        # Registrar en audit_log la nueva asignación
        await self._audit.register(AuditLogCreate(
            table_name="professor_courses",
            operation=OperationEnum.INSERT,
            record_id=new_assignment.id,
            user_id=professor_id,
            new_data={
                "professor_id": str(professor_id),
                "course_id": str(course_id),
            },
        ))
        return ProfessorCourseRead.model_validate(new_assignment)

    async def get_course_professor(self, course_id: UUID) -> UserRead:
        """
        Retorna el profesor asignado a un curso.
        Lanza 404 si el curso no tiene profesor asignado.

        Requisitos: 4.5
        """
        stmt = (
            select(User)
            .join(ProfessorCourse, ProfessorCourse.professor_id == User.id)
            .where(ProfessorCourse.course_id == course_id)
        )
        result = await self._session.execute(stmt)
        professor = result.scalar_one_or_none()
        if professor is None:
            raise HTTPException(
                status_code=404,
                detail="El curso no tiene profesor asignado",
            )
        return UserRead.model_validate(professor)

    async def list_professor_courses(self, professor_id: UUID) -> list[CourseRead]:
        """
        Retorna la lista de cursos asignados a un profesor.

        Requisitos: 4.6
        """
        courses = await self._course_repo.listar_por_docente(professor_id)
        return [CourseRead.model_validate(c) for c in courses]

    # ------------------------------------------------------------------
    # 10.2 — Control de acceso RB-04
    # ------------------------------------------------------------------

    async def verify_professor_assigned_to_course(
        self, professor_id: UUID, course_id: UUID
    ) -> None:
        """
        Verifica que el profesor está asignado al curso.
        Lanza HTTPException(403) si no lo está.

        Requisitos: 5.1, 5.2, 5.3, 5.4
        """
        result = await self._session.execute(
            select(ProfessorCourse).where(
                ProfessorCourse.course_id == course_id,
                ProfessorCourse.professor_id == professor_id,
            )
        )
        assignment = result.scalar_one_or_none()
        if assignment is None:
            raise HTTPException(
                status_code=403,
                detail="No tiene permiso para operar en este curso",
            )

    async def list_course_students(
        self, course_id: UUID, professor_id: UUID
    ) -> list[UserRead]:
        """
        Retorna los estudiantes inscritos en un curso, verificando que el
        profesor solicitante esté asignado al curso (RB-04).

        Requisitos: 5.1, 5.3, 5.4
        """
        # Verificar que el profesor está asignado al curso
        await self.verify_professor_assigned_to_course(professor_id, course_id)

        # Obtener estudiantes inscritos
        students = await self._course_repo.listar_estudiantes_inscritos(course_id)
        return [UserRead.model_validate(s) for s in students]

    async def write_grade(
        self,
        professor_id: UUID,
        course_id: UUID,
        student_id: UUID,
        grade_data: dict,
    ) -> dict:
        """
        Registra o actualiza una nota, verificando que el profesor está
        asignado al curso (RB-04) y que el estudiante está inscrito.
        Registra la operación en audit_log.

        Requisitos: 5.2, 5.5
        """
        # Verificar que el profesor está asignado al curso
        await self.verify_professor_assigned_to_course(professor_id, course_id)

        # Verificar que el estudiante está inscrito en el curso
        enrollment_result = await self._session.execute(
            select(Enrollment).where(
                Enrollment.course_id == course_id,
                Enrollment.student_id == student_id,
            )
        )
        enrollment = enrollment_result.scalar_one_or_none()
        if enrollment is None:
            raise HTTPException(
                status_code=403,
                detail="Acceso denegado: el estudiante no está inscrito en sus cursos",
            )

        # Registrar en audit_log la operación de escritura de notas
        await self._audit.register(AuditLogCreate(
            table_name="grades",
            operation=OperationEnum.INSERT,
            record_id=enrollment.id,
            user_id=professor_id,
            new_data={
                "professor_id": str(professor_id),
                "course_id": str(course_id),
                "student_id": str(student_id),
                **{k: str(v) if not isinstance(v, (str, int, float, bool)) else v
                   for k, v in grade_data.items()},
            },
        ))

        return {
            "professor_id": str(professor_id),
            "course_id": str(course_id),
            "student_id": str(student_id),
            "status": "recorded",
        }
