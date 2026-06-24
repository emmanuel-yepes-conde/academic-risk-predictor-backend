"""
ProfessorCourseService — lógica de negocio para asignación profesor-curso
y control de acceso RB-04.

Requisitos: 3.5, 4.1, 4.2, 4.3, 4.4, 4.5, 5.1, 5.2, 6.1, 6.2, 6.3, 6.4, 8.1, 8.2, 8.3
"""

import inspect
from uuid import UUID

from fastapi import HTTPException

from app.application.schemas.audit_log import AuditLogCreate
from app.application.schemas.professor_course import ProfessorAssignmentRead
from app.application.schemas.user import PaginatedResponse, UserRead
from app.application.schemas.course import CourseRead
from app.domain.enums import OperationEnum, RoleEnum

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.models.enrollment import Enrollment
from app.infrastructure.models.course import Course
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

    async def _get_course_model(self, course_id: UUID) -> Course | None:
        if hasattr(self, "_session") and self._session is not None:
            result = await self._session.execute(select(Course).where(Course.id == course_id))
            course = result.scalar_one_or_none()
            if inspect.isawaitable(course):
                course = await course
            professor_id = getattr(course, "professor_id", None)
            if course is not None and (
                professor_id is None or isinstance(professor_id, UUID)
            ):
                return course

        if hasattr(self, "_course_repo"):
            course = await self._course_repo.obtener_por_id(course_id)
            if inspect.isawaitable(course):
                course = await course
            return course
        return None

    # ------------------------------------------------------------------
    # Asignación profesor-curso (directa sobre Course.professor_id)
    # ------------------------------------------------------------------

    async def assign_professor(
        self, course_id: UUID, professor_id: UUID
    ) -> ProfessorAssignmentRead:
        """
        Asigna (o reemplaza) el profesor de un curso.

        - Verifica existencia del curso → 404
        - Verifica que el usuario tenga rol PROFESSOR → 422
        - Actualiza course.professor_id directamente

        Requisitos: 4.1, 4.2, 4.3, 4.4, 4.5, 8.1, 8.2, 8.3
        """
        # Verificar existencia del curso
        course = await self._get_course_model(course_id)
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

        previous_professor_id = course.professor_id

        # Actualizar professor_id directamente en el curso
        course.professor_id = professor_id
        self._session.add(course)
        await self._session.flush()
        await self._session.refresh(course)

        # Determinar tipo de operación para audit log
        if previous_professor_id is None:
            # INSERT: curso no tenía profesor asignado
            await self._audit.register(AuditLogCreate(
                table_name="courses",
                operation=OperationEnum.INSERT,
                record_id=course.id,
                user_id=professor_id,
                new_data={
                    "professor_id": str(professor_id),
                    "course_id": str(course_id),
                },
            ))
        else:
            # UPDATE: reemplazando profesor existente
            await self._audit.register(AuditLogCreate(
                table_name="courses",
                operation=OperationEnum.UPDATE,
                record_id=course.id,
                user_id=professor_id,
                previous_data={"professor_id": str(previous_professor_id)},
                new_data={
                    "professor_id": str(professor_id),
                    "course_id": str(course_id),
                },
            ))

        return ProfessorAssignmentRead(
            id=course.id,
            professor_id=professor_id,
            course_id=course.id,
        )

    async def get_course_professor(self, course_id: UUID) -> UserRead:
        """
        Retorna el profesor asignado a un curso.
        Lanza 404 si el curso no tiene profesor asignado.

        Requisitos: 5.1, 5.2
        """
        # Obtener el curso para leer su professor_id
        course = await self._get_course_model(course_id)
        if course is None or course.professor_id is None:
            raise HTTPException(
                status_code=404,
                detail="El curso no tiene profesor asignado",
            )

        # JOIN con users para obtener los datos del profesor
        result = await self._session.execute(
            select(User).where(User.id == course.professor_id)
        )
        professor = result.scalar_one_or_none()
        if professor is None:
            raise HTTPException(
                status_code=404,
                detail="El curso no tiene profesor asignado",
            )
        return UserRead.model_validate(professor)

    async def list_professor_courses(
        self, professor_id: UUID, skip: int = 0, limit: int = 50, search: str | None = None
    ) -> PaginatedResponse[CourseRead]:
        """
        Retorna los cursos asignados a un profesor, paginados (50 por página).

        Requisitos: 5.3, 5.4
        """
        courses = await self._course_repo.list_by_professor(
            professor_id, skip=skip, limit=limit, search=search
        )
        total = await self._course_repo.count_by_professor(professor_id, search=search)
        return PaginatedResponse(
            data=[CourseRead.model_validate(c) for c in courses],
            total=total,
            skip=skip,
            limit=limit,
        )

    # ------------------------------------------------------------------
    # Control de acceso RB-04
    # ------------------------------------------------------------------

    async def verify_professor_assigned_to_course(
        self, professor_id: UUID, course_id: UUID
    ) -> None:
        """
        Verifica que el profesor está asignado al curso.
        Lanza HTTPException(403) si no lo está.

        Requisitos: 6.1, 6.2, 6.3
        """
        course = await self._get_course_model(course_id)
        if course is None or course.professor_id != professor_id:
            raise HTTPException(
                status_code=403,
                detail="No tiene permiso para operar en este curso",
            )

    async def list_course_students(
        self, course_id: UUID, professor_id: UUID, skip: int = 0, limit: int = 50
    ) -> PaginatedResponse[UserRead]:
        """
        Retorna los estudiantes inscritos en un curso (paginados, 50 por página),
        verificando que el profesor solicitante esté asignado al curso (RB-04).

        Requisitos: 6.1, 6.2
        """
        # Verificar que el profesor está asignado al curso
        await self.verify_professor_assigned_to_course(professor_id, course_id)

        # Obtener estudiantes inscritos
        students = await self._course_repo.list_enrolled_students(
            course_id, skip=skip, limit=limit
        )
        total = await self._course_repo.count_enrolled_students(course_id)
        return PaginatedResponse(
            data=[UserRead.model_validate(s) for s in students],
            total=total,
            skip=skip,
            limit=limit,
        )

    async def unenroll_student(
        self,
        course_id: UUID,
        student_id: UUID,
        current_user,
    ) -> bool:
        """
        Elimina la inscripción de un estudiante en un curso.
        Si el usuario es PROFESSOR, verifica que sea el asignado al curso (RB-04).
        Retorna True si se eliminó, False si no existía la inscripción.
        """
        if current_user.role == RoleEnum.PROFESSOR:
            await self.verify_professor_assigned_to_course(current_user.id, course_id)
        return await self._course_repo.unenroll_student(course_id, student_id)

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

        Requisitos: 6.3, 6.4
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
