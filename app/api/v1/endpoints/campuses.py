"""
CampusRouter — endpoints CRUD para campus anidados bajo universidades
y endpoints jerárquicos universidad → campus → programa → curso.
Requisitos: 2.1–2.7, 4.1–4.4
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies.auth import CurrentUser, get_current_user
from app.application.schemas.campus import CampusCreate, CampusRead, CampusUpdate
from app.application.schemas.course import CourseRead
from app.application.schemas.program import ProgramRead
from app.application.schemas.user import PaginatedResponse
from app.application.services.campus_service import CampusService
from app.infrastructure.database import get_session
from app.infrastructure.repositories.campus_repository import CampusRepository
from app.infrastructure.repositories.course_repository import CourseRepository
from app.infrastructure.repositories.program_repository import ProgramRepository
from app.infrastructure.repositories.university_repository import UniversityRepository

router = APIRouter()


# ---------------------------------------------------------------------------
# Dependency helpers
# ---------------------------------------------------------------------------

def _get_campus_service(
    session: AsyncSession = Depends(get_session),
) -> CampusService:
    return CampusService(
        campus_repo=CampusRepository(session),
        university_repo=UniversityRepository(session),
        program_repo=ProgramRepository(session),
        course_repo=CourseRepository(session),
    )


# ===========================================================================
# CRUD de campus (Req 2.1–2.7)
# ===========================================================================

@router.post(
    "/universities/{university_id}/campuses",
    response_model=CampusRead,
    status_code=201,
    summary="Crear un nuevo campus",
    description=(
        "Crea un campus asociado a la universidad indicada. "
        "Requiere rol ADMIN. Retorna 404 si la universidad no existe, "
        "409 si la combinación university_id + campus_code ya existe."
    ),
    tags=["Campus"],
)
async def create_campus(
    university_id: UUID,
    body: CampusCreate,
    current_user: CurrentUser = Depends(get_current_user),
    service: CampusService = Depends(_get_campus_service),
) -> CampusRead:
    return await service.create(university_id, body, current_user.role)


@router.get(
    "/universities/{university_id}/campuses",
    response_model=PaginatedResponse[CampusRead],
    status_code=200,
    summary="Listar campus de una universidad",
    description=(
        "Retorna la lista paginada de campus pertenecientes a la universidad "
        "indicada, con parámetros skip y limit."
    ),
    tags=["Campus"],
)
async def list_campuses(
    university_id: UUID,
    skip: int = Query(0, ge=0, description="Número de registros a omitir"),
    limit: int = Query(20, ge=1, le=100, description="Cantidad máxima de registros"),
    service: CampusService = Depends(_get_campus_service),
) -> PaginatedResponse[CampusRead]:
    return await service.list_by_university(university_id, skip=skip, limit=limit)


@router.get(
    "/universities/{university_id}/campuses/{campus_id}",
    response_model=CampusRead,
    status_code=200,
    summary="Obtener campus por ID",
    description=(
        "Retorna los datos de un campus específico. "
        "Retorna 404 si no existe o no pertenece a la universidad indicada."
    ),
    tags=["Campus"],
)
async def get_campus(
    university_id: UUID,
    campus_id: UUID,
    service: CampusService = Depends(_get_campus_service),
) -> CampusRead:
    return await service.get(university_id, campus_id)


@router.patch(
    "/universities/{university_id}/campuses/{campus_id}",
    response_model=CampusRead,
    status_code=200,
    summary="Actualizar campus",
    description=(
        "Actualiza parcialmente los datos de un campus (name, city, active). "
        "Requiere rol ADMIN. Retorna 403 si no es ADMIN, "
        "404 si el campus no existe o no pertenece a la universidad."
    ),
    tags=["Campus"],
)
async def update_campus(
    university_id: UUID,
    campus_id: UUID,
    body: CampusUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    service: CampusService = Depends(_get_campus_service),
) -> CampusRead:
    return await service.update(university_id, campus_id, body, current_user.role)


# ===========================================================================
# Endpoints jerárquicos (Req 4.1–4.4)
# ===========================================================================

@router.get(
    "/universities/{university_id}/campuses/{campus_id}/programs",
    response_model=PaginatedResponse[ProgramRead],
    status_code=200,
    summary="Listar programas de un campus",
    description=(
        "Retorna la lista paginada de programas pertenecientes al campus indicado. "
        "Valida que el campus pertenezca a la universidad. "
        "Retorna 404 si el campus no existe o no pertenece a la universidad."
    ),
    tags=["Campus"],
)
async def list_programs_by_campus(
    university_id: UUID,
    campus_id: UUID,
    skip: int = Query(0, ge=0, description="Número de registros a omitir"),
    limit: int = Query(20, ge=1, le=100, description="Cantidad máxima de registros"),
    service: CampusService = Depends(_get_campus_service),
) -> PaginatedResponse[ProgramRead]:
    return await service.list_programs_by_campus(
        university_id, campus_id, skip=skip, limit=limit
    )


@router.get(
    "/universities/{university_id}/campuses/{campus_id}/programs/{program_id}/courses",
    response_model=list[CourseRead],
    status_code=200,
    summary="Listar cursos de un programa dentro de un campus",
    description=(
        "Retorna los cursos del programa indicado, validando la cadena completa "
        "de pertenencia: universidad → campus → programa. "
        "Retorna 404 si el campus no pertenece a la universidad o si el programa "
        "no pertenece al campus."
    ),
    tags=["Campus"],
)
async def list_courses_by_campus_and_program(
    university_id: UUID,
    campus_id: UUID,
    program_id: UUID,
    service: CampusService = Depends(_get_campus_service),
) -> list[CourseRead]:
    return await service.list_courses_by_campus_and_program(
        university_id, campus_id, program_id
    )
