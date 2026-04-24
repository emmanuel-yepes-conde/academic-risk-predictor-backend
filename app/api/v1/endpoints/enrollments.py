"""
EnrollmentRouter — endpoints CRUD para inscripciones de estudiantes en cursos.
Requisitos: 1.1, 1.9, 2.1, 2.7, 3.1, 3.4, 4.1, 4.3, 5.1, 5.3
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.schemas.enrollment import (
    EnrollmentCreate,
    EnrollmentRead,
    EnrollmentStatusUpdate,
    EnrollmentUpdate,
)
from app.application.services.enrollment_service import EnrollmentService
from app.api.v1.dependencies.auth import (
    CurrentUser,
    get_current_user,
    require_roles,
    require_student_self_or_roles,
)
from app.domain.enums import EnrollmentStatusEnum, RoleEnum
from app.infrastructure.database import get_session
from app.infrastructure.repositories.enrollment_repository import EnrollmentRepository

router = APIRouter()


# ---------------------------------------------------------------------------
# Dependency helpers
# ---------------------------------------------------------------------------

def _get_enrollment_service(
    session: AsyncSession = Depends(get_session),
) -> EnrollmentService:
    repo = EnrollmentRepository(session)
    return EnrollmentService(repo, session)


# ===========================================================================
# CRUD endpoints
# ===========================================================================

@router.post(
    "/enrollments",
    response_model=EnrollmentRead,
    status_code=201,
    summary="Inscribir un estudiante en un curso",
    description=(
        "Crea una nueva inscripción para un estudiante en un curso. "
        "Si ya existe una inscripción cancelada para la misma combinación "
        "(student_id, course_id), se reactiva en lugar de crear una nueva. "
        "Requiere rol ADMIN."
    ),
    tags=["Inscripciones"],
)
async def create_enrollment(
    body: EnrollmentCreate,
    current_user: CurrentUser = Depends(require_roles(RoleEnum.ADMIN)),
    service: EnrollmentService = Depends(_get_enrollment_service),
) -> EnrollmentRead:
    return await service.create_enrollment(body, current_user.id)


@router.patch(
    "/enrollments/{enrollment_id}",
    response_model=EnrollmentRead,
    status_code=200,
    summary="Actualizar inscripción (cambio de curso)",
    description=(
        "Actualiza el curso de una inscripción existente. "
        "Valida que el curso destino exista, esté activo y que no exista "
        "una inscripción activa duplicada en el curso destino. "
        "Requiere rol ADMIN."
    ),
    tags=["Inscripciones"],
)
async def update_enrollment(
    enrollment_id: UUID,
    body: EnrollmentUpdate,
    current_user: CurrentUser = Depends(require_roles(RoleEnum.ADMIN)),
    service: EnrollmentService = Depends(_get_enrollment_service),
) -> EnrollmentRead:
    return await service.update_enrollment(enrollment_id, body, current_user.id)


@router.patch(
    "/enrollments/{enrollment_id}/status",
    response_model=EnrollmentRead,
    status_code=200,
    summary="Actualizar estado de inscripción",
    description=(
        "Actualiza el estado de una inscripción a cualquier estado válido: "
        "PENDING, ACTIVE, COMPLETED o CANCELLED. "
        "El registro se preserva en la base de datos con el campo status actualizado. "
        "Requiere rol ADMIN."
    ),
    tags=["Inscripciones"],
)
async def update_enrollment_status(
    enrollment_id: UUID,
    body: EnrollmentStatusUpdate,
    current_user: CurrentUser = Depends(require_roles(RoleEnum.ADMIN)),
    service: EnrollmentService = Depends(_get_enrollment_service),
) -> EnrollmentRead:
    return await service.update_enrollment_status(enrollment_id, body, current_user.id)


@router.get(
    "/enrollments/{enrollment_id}",
    response_model=EnrollmentRead,
    status_code=200,
    summary="Obtener detalle de una inscripción",
    description=(
        "Retorna los datos completos de una inscripción específica. "
        "Retorna 404 si la inscripción no existe. "
        "Requiere rol ADMIN."
    ),
    tags=["Inscripciones"],
)
async def get_enrollment(
    enrollment_id: UUID,
    current_user: CurrentUser = Depends(require_roles(RoleEnum.ADMIN)),
    service: EnrollmentService = Depends(_get_enrollment_service),
) -> EnrollmentRead:
    return await service.get_enrollment(enrollment_id)


@router.get(
    "/students/{student_id}/enrollments",
    response_model=list[EnrollmentRead],
    status_code=200,
    summary="Listar inscripciones de un estudiante",
    description=(
        "Retorna la lista de inscripciones de un estudiante. "
        "Si el usuario autenticado es STUDENT, permite auto-acceso a sus propias inscripciones "
        "(retorna todos los estados para la vista de progreso). "
        "Si el usuario autenticado es PROFESSOR, solo retorna inscripciones "
        "en cursos asignados al profesor (RB-04). "
        "Acepta un query param opcional `status` para filtrar por estado de inscripción. "
        "Requiere rol STUDENT (auto-acceso), ADMIN o PROFESSOR."
    ),
    tags=["Inscripciones"],
)
async def list_student_enrollments(
    student_id: UUID,
    status: EnrollmentStatusEnum | None = Query(
        default=None, description="Filtrar por estado de inscripción"
    ),
    current_user: CurrentUser = Depends(require_student_self_or_roles),
    service: EnrollmentService = Depends(_get_enrollment_service),
) -> list[EnrollmentRead]:
    return await service.list_student_enrollments(student_id, current_user, status)
