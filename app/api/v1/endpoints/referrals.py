"""
ReferralRouter — endpoints para remisiones a permanencia/consejería y
configuración de evaluación de cursos.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.schemas.referral import (
    EvaluationConfigRead,
    EvaluationConfigUpdate,
    ReferralCreate,
    ReferralRead,
    ReferralUpdate,
)
from app.application.schemas.user import PaginatedResponse
from app.application.services.referral_service import ReferralService
from app.api.v1.dependencies.auth import CurrentUser, get_current_user, require_roles
from app.domain.enums import RoleEnum
from app.infrastructure.database import get_session
from app.infrastructure.repositories.referral_repository import ReferralRepository

router = APIRouter()


def _get_service(session: AsyncSession = Depends(get_session)) -> ReferralService:
    return ReferralService(ReferralRepository(session), session)


# ── Remisiones ────────────────────────────────────────────────────────────────

@router.post(
    "/enrollments/{enrollment_id}/referrals",
    response_model=ReferralRead,
    status_code=201,
    summary="Crear una remisión para un estudiante",
    tags=["Remisiones"],
)
async def create_referral(
    enrollment_id: UUID,
    body: ReferralCreate,
    current_user: CurrentUser = Depends(get_current_user),
    service: ReferralService = Depends(_get_service),
) -> ReferralRead:
    return await service.create(enrollment_id, body, current_user)


@router.get(
    "/enrollments/{enrollment_id}/referrals",
    response_model=PaginatedResponse[ReferralRead],
    status_code=200,
    summary="Listar remisiones de una inscripción",
    tags=["Remisiones"],
)
async def list_referrals_by_enrollment(
    enrollment_id: UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: CurrentUser = Depends(get_current_user),
    service: ReferralService = Depends(_get_service),
) -> PaginatedResponse[ReferralRead]:
    return await service.list_by_enrollment(enrollment_id, current_user, skip=skip, limit=limit)


@router.get(
    "/courses/{course_id}/referrals",
    response_model=PaginatedResponse[ReferralRead],
    status_code=200,
    summary="Listar todas las remisiones de un curso",
    tags=["Remisiones"],
)
async def list_referrals_by_course(
    course_id: UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: CurrentUser = Depends(get_current_user),
    service: ReferralService = Depends(_get_service),
) -> PaginatedResponse[ReferralRead]:
    return await service.list_by_course(course_id, current_user, skip=skip, limit=limit)


@router.patch(
    "/referrals/{referral_id}",
    response_model=ReferralRead,
    status_code=200,
    summary="Actualizar una remisión (asistió, observaciones, estado)",
    tags=["Remisiones"],
)
async def update_referral(
    referral_id: UUID,
    body: ReferralUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    service: ReferralService = Depends(_get_service),
) -> ReferralRead:
    return await service.update(referral_id, body, current_user)


# ── Configuración de evaluación (cortes del curso) ────────────────────────────

@router.get(
    "/courses/{course_id}/evaluation-config",
    response_model=EvaluationConfigRead,
    status_code=200,
    summary="Obtener configuración de cortes del curso",
    tags=["Configuración de Evaluación"],
)
async def get_evaluation_config(
    course_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: ReferralService = Depends(_get_service),
) -> EvaluationConfigRead:
    return await service.get_evaluation_config(course_id, current_user)


@router.put(
    "/courses/{course_id}/evaluation-config",
    response_model=EvaluationConfigRead,
    status_code=200,
    summary="Guardar configuración de cortes del curso",
    tags=["Configuración de Evaluación"],
)
async def set_evaluation_config(
    course_id: UUID,
    body: EvaluationConfigUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    service: ReferralService = Depends(_get_service),
) -> EvaluationConfigRead:
    return await service.set_evaluation_config(course_id, body, current_user)
