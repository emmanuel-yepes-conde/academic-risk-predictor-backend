"""
ProgramRouter — endpoints para programas académicos y sus cursos.
Requisitos: 4.1–4.3, 5.3, 5.4, 6.1–6.7, 7.1–7.8
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies.auth import CurrentUser, get_current_user, require_roles
from app.application.schemas.course import CourseRead
from app.application.schemas.program import ProgramCreate, ProgramRead, ProgramUpdate
from app.application.schemas.subject import SubjectRead
from app.application.schemas.user import PaginatedResponse
from app.application.services.program_service import ProgramService
from app.application.services.subject_service import SubjectService
from app.domain.enums import RoleEnum
from app.infrastructure.database import get_session
from app.infrastructure.repositories.course_repository import CourseRepository
from app.infrastructure.repositories.program_repository import ProgramRepository
from app.infrastructure.repositories.subject_repository import SubjectRepository

router = APIRouter()


def _get_service(session: AsyncSession = Depends(get_session)) -> ProgramService:
    return ProgramService(ProgramRepository(session))


# ---------------------------------------------------------------------------
# GET /programs — any authenticated user
# ---------------------------------------------------------------------------


@router.get(
    "/programs",
    response_model=PaginatedResponse[ProgramRead],
    status_code=200,
    summary="Listar todos los programas académicos",
    description="Retorna programas académicos paginados (50 por página por defecto). Accesible para cualquier usuario autenticado.",
    tags=["Programas"],
)
async def list_programs(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    current_user: CurrentUser = Depends(get_current_user),
    service: ProgramService = Depends(_get_service),
) -> PaginatedResponse[ProgramRead]:
    return await service.list_programs(skip, limit)


# ---------------------------------------------------------------------------
# POST /programs — ADMIN only
# ---------------------------------------------------------------------------


@router.post(
    "/programs",
    response_model=ProgramRead,
    status_code=201,
    summary="Crear un programa académico",
    description="Crea un nuevo programa académico. Requiere rol ADMIN. "
                "Valida unicidad de program_code y snies_code.",
    tags=["Programas"],
)
async def create_program(
    body: ProgramCreate,
    current_user: CurrentUser = Depends(require_roles(RoleEnum.ADMIN)),
    service: ProgramService = Depends(_get_service),
) -> ProgramRead:
    return await service.create_program(body)


# ---------------------------------------------------------------------------
# PATCH /programs/{program_id} — ADMIN only
# ---------------------------------------------------------------------------


@router.patch(
    "/programs/{program_id}",
    response_model=ProgramRead,
    status_code=200,
    summary="Actualizar parcialmente un programa académico",
    description="Actualiza los campos proporcionados de un programa existente. "
                "Requiere rol ADMIN. Valida unicidad de program_code y snies_code.",
    tags=["Programas"],
)
async def update_program(
    program_id: UUID,
    body: ProgramUpdate,
    current_user: CurrentUser = Depends(require_roles(RoleEnum.ADMIN)),
    service: ProgramService = Depends(_get_service),
) -> ProgramRead:
    return await service.update_program(program_id, body)


# ---------------------------------------------------------------------------
# GET /programs/{program_id} — any authenticated user
# ---------------------------------------------------------------------------


@router.get(
    "/programs/{program_id}",
    response_model=ProgramRead,
    status_code=200,
    summary="Obtener un programa académico por ID",
    description="Retorna los datos de un programa académico por su ID. "
                "Accesible para cualquier usuario autenticado (STUDENT, PROFESSOR, ADMIN).",
    tags=["Programas"],
)
async def get_program(
    program_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: ProgramService = Depends(_get_service),
) -> ProgramRead:
    return await service.get_program(program_id)


# ---------------------------------------------------------------------------
# DELETE /programs/{program_id} — ADMIN only
# ---------------------------------------------------------------------------


@router.delete(
    "/programs/{program_id}",
    response_model=None,
    status_code=204,
    summary="Eliminar un programa académico",
    description=(
        "Elimina un programa académico y todos sus recursos asociados en cascada: "
        "cursos del programa, inscripciones de esos cursos. "
        "Los perfiles de estudiantes que referenciaban el programa conservan sus datos "
        "pero su program_id queda en NULL. "
        "Requiere rol ADMIN."
    ),
    tags=["Programas"],
)
async def delete_program(
    program_id: UUID,
    current_user: CurrentUser = Depends(require_roles(RoleEnum.ADMIN)),
    service: ProgramService = Depends(_get_service),
) -> None:
    await service.delete_program(program_id)


# ---------------------------------------------------------------------------
# GET /programs/{program_id}/subjects — catálogo de materias del programa
# ---------------------------------------------------------------------------


@router.get(
    "/programs/{program_id}/subjects",
    response_model=PaginatedResponse[SubjectRead],
    status_code=200,
    summary="Listar materias de un programa",
    description="Retorna las materias (definiciones) del programa, paginadas (50 por página). 404 si no existe.",
    tags=["Programas"],
)
async def list_subjects_by_program(
    program_id: UUID,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> PaginatedResponse[SubjectRead]:
    program = await ProgramRepository(session).get_by_id(program_id)
    if program is None:
        raise HTTPException(status_code=404, detail="Programa no encontrado")
    return await SubjectService(SubjectRepository(session)).list_by_program(
        program_id, skip=skip, limit=limit
    )


# ---------------------------------------------------------------------------
# GET /programs/{program_id}/courses — secciones activas del programa
# ---------------------------------------------------------------------------


@router.get(
    "/programs/{program_id}/courses",
    response_model=PaginatedResponse[CourseRead],
    status_code=200,
    summary="Listar secciones de un programa",
    description=(
        "Retorna las secciones (grupos) de todas las materias del programa, "
        "paginadas (50 por página). Incluye datos de materia denormalizados. "
        "404 si el programa no existe."
    ),
    tags=["Programas"],
)
async def list_courses_by_program(
    program_id: UUID,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> PaginatedResponse[CourseRead]:
    program = await ProgramRepository(session).get_by_id(program_id)
    if program is None:
        raise HTTPException(status_code=404, detail="Programa no encontrado")
    repo = CourseRepository(session)
    items = await repo.list_by_program(program_id, skip=skip, limit=limit)
    total = await repo.count_by_program(program_id)
    return PaginatedResponse(data=items, total=total, skip=skip, limit=limit)
