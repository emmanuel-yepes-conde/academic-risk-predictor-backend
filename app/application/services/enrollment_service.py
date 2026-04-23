"""
EnrollmentService — lógica de negocio para operaciones CRUD de inscripciones.

Requisitos: 1.1–1.9, 2.1–2.7, 3.1–3.5, 4.1–4.4, 5.1–5.3
"""

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.schemas.enrollment import (
    EnrollmentCreate,
    EnrollmentRead,
    EnrollmentStatusUpdate,
    EnrollmentUpdate,
)
from app.domain.enums import CourseStatusEnum, EnrollmentStatusEnum, RoleEnum
from app.domain.interfaces.enrollment_repository import IEnrollmentRepository
from app.infrastructure.models.course import Course
from app.infrastructure.models.user import User


class EnrollmentService:
    """
    Servicio de aplicación que encapsula la lógica de negocio de inscripciones.
    Recibe IEnrollmentRepository vía inyección de constructor (DIP).
    Recibe AsyncSession para consultas auxiliares (validar estudiante, validar curso).
    """

    def __init__(self, repo: IEnrollmentRepository, session: AsyncSession) -> None:
        self._repo = repo
        self._session = session

    # ------------------------------------------------------------------
    # Auxiliary validation helpers
    # ------------------------------------------------------------------

    async def _validate_student(self, student_id: UUID) -> User:
        """Validate that student_id corresponds to an existing user with role STUDENT."""
        result = await self._session.execute(
            select(User).where(User.id == student_id)
        )
        user = result.scalar_one_or_none()
        if user is None or user.role != RoleEnum.STUDENT:
            raise HTTPException(
                status_code=422,
                detail="El usuario indicado no existe o no tiene rol de estudiante",
            )
        return user

    async def _validate_course(self, course_id: UUID) -> Course:
        """Validate that course_id corresponds to an existing course with status ACTIVE."""
        result = await self._session.execute(
            select(Course).where(Course.id == course_id)
        )
        course = result.scalar_one_or_none()
        if course is None or course.status != CourseStatusEnum.ACTIVE:
            raise HTTPException(
                status_code=404,
                detail="Curso no encontrado",
            )
        return course

    # ------------------------------------------------------------------
    # CRUD operations
    # ------------------------------------------------------------------

    async def create_enrollment(
        self, data: EnrollmentCreate, user_id: UUID
    ) -> EnrollmentRead:
        """
        Crea o reactiva una inscripción.

        Flujo:
        1. Buscar inscripción existente por (student_id, course_id).
        2. Si existe con status ACTIVE → 409.
        3. Si existe con status CANCELLED → reactivar (update_status a ACTIVE).
        4. Si no existe → validar estudiante (rol STUDENT), validar curso (ACTIVE), crear.

        Requisitos: 1.1–1.8
        """
        # Check for existing enrollment (any status)
        existing = await self._repo.get_by_student_and_course(
            data.student_id, data.course_id
        )

        if existing is not None:
            if existing.status == EnrollmentStatusEnum.ACTIVE:
                raise HTTPException(
                    status_code=409,
                    detail="El estudiante ya está inscrito en este curso",
                )
            # CANCELLED → reactivate
            enrollment = await self._repo.update_status(
                existing.id, EnrollmentStatusEnum.ACTIVE, user_id
            )
            return EnrollmentRead.model_validate(enrollment)

        # No existing enrollment — validate entities before creating
        await self._validate_student(data.student_id)
        await self._validate_course(data.course_id)

        enrollment = await self._repo.create(
            {
                "student_id": data.student_id,
                "course_id": data.course_id,
            },
            user_id,
        )
        return EnrollmentRead.model_validate(enrollment)

    async def update_enrollment(
        self, enrollment_id: UUID, data: EnrollmentUpdate, user_id: UUID
    ) -> EnrollmentRead:
        """
        Actualiza el curso de una inscripción (cambio de curso).

        Validaciones:
        1. La inscripción debe existir → 404.
        2. El curso destino debe existir y estar ACTIVE → 404.
        3. No debe existir inscripción ACTIVE para (student_id, nuevo course_id) → 409.

        Requisitos: 2.1–2.6
        """
        # Validate enrollment exists
        enrollment = await self._repo.get_by_id(enrollment_id)
        if enrollment is None:
            raise HTTPException(
                status_code=404,
                detail="Inscripción no encontrada",
            )

        # Validate destination course exists and is ACTIVE
        await self._validate_course(data.course_id)

        # Check for duplicate ACTIVE enrollment in destination
        duplicate = await self._repo.get_by_student_and_course(
            enrollment.student_id, data.course_id
        )
        if duplicate is not None and duplicate.status == EnrollmentStatusEnum.ACTIVE:
            raise HTTPException(
                status_code=409,
                detail="El estudiante ya está inscrito en el curso destino",
            )

        # Update course
        updated = await self._repo.update_course(
            enrollment_id, data.course_id, user_id
        )
        return EnrollmentRead.model_validate(updated)

    async def update_enrollment_status(
        self, enrollment_id: UUID, body: "EnrollmentStatusUpdate", user_id: UUID
    ) -> EnrollmentRead:
        """
        Actualiza el estado de una inscripción a cualquier estado válido
        (PENDING, ACTIVE, COMPLETED, CANCELLED).

        Requisitos: 2.2, 2.3, 2.4, 3.1–3.3
        """
        enrollment = await self._repo.get_by_id(enrollment_id)
        if enrollment is None:
            raise HTTPException(
                status_code=404,
                detail="Inscripción no encontrada",
            )

        updated = await self._repo.update_status(
            enrollment_id, body.status, user_id
        )
        return EnrollmentRead.model_validate(updated)

    async def get_enrollment(self, enrollment_id: UUID) -> EnrollmentRead:
        """
        Obtiene el detalle de una inscripción.

        Requisitos: 5.1–5.2
        """
        enrollment = await self._repo.get_by_id(enrollment_id)
        if enrollment is None:
            raise HTTPException(
                status_code=404,
                detail="Inscripción no encontrada",
            )
        return EnrollmentRead.model_validate(enrollment)

    async def list_student_enrollments(
        self,
        student_id: UUID,
        current_user: object,
        status: EnrollmentStatusEnum | None = None,
    ) -> list[EnrollmentRead]:
        """
        Lista las inscripciones de un estudiante.

        - STUDENT: retorna todas las inscripciones (todos los estados) cuando status es None.
        - PROFESSOR: filtra por cursos del profesor (RB-04) + filtro de estado opcional.
        - ADMIN: cuando status es None, retorna solo ACTIVE (comportamiento actual preservado).

        Requisitos: 1.1, 1.5, 3.1, 3.2, 3.4, 4.1–4.4
        """
        if current_user.role == RoleEnum.PROFESSOR:
            enrollments = await self._repo.list_by_student_filtered_by_professor(
                student_id, current_user.id, status=status
            )
        elif current_user.role == RoleEnum.STUDENT:
            # STUDENT — return all statuses when no filter (progress view)
            enrollments = await self._repo.list_by_student(
                student_id, status=status
            )
        else:
            # ADMIN — default to ACTIVE when no filter (preserve current behavior)
            effective_status = status if status is not None else EnrollmentStatusEnum.ACTIVE
            enrollments = await self._repo.list_by_student(
                student_id, status=effective_status
            )

        return [EnrollmentRead.model_validate(e) for e in enrollments]
