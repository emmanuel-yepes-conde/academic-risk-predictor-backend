"""
ProgramRouter — endpoints para programas académicos y sus cursos.
Requisitos: 4.2, 4.3, 4.4, 5.3, 5.4, 6.1–6.7, 7.1–7.8
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies.auth import CurrentUser, require_roles
from app.application.schemas.course import CourseRead
from app.application.schemas.program import ProgramCreate, ProgramRead, ProgramUpdate
from app.application.services.program_service import ProgramService
from app.domain.enums import RoleEnum
from app.infrastructure.database import get_session
from app.infrastructure.repositories.course_repository import CourseRepository
from app.infrastructure.repositories.program_repository import ProgramRepository

router = APIRouter()


def _get_service(session: AsyncSession = Depends(get_session)) -> ProgramService:
    return ProgramService(ProgramRepository(session))


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
# GET /programs/{program_id}/courses
# ---------------------------------------------------------------------------


@router.get(
    "/programs/{program_id}/courses",
    response_model=list[CourseRead],
    status_code=200,
    summary="Listar cursos de un programa",
    description=(
        "Retorna los cursos pertenecientes al programa indicado. "
        "Retorna 404 si el programa no existe."
    ),
    tags=["Programas"],
)
async def list_courses_by_program(
    program_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> list[CourseRead]:
    program = await ProgramRepository(session).get_by_id(program_id)
    if program is None:
        raise HTTPException(status_code=404, detail="Programa no encontrado")

    courses = await CourseRepository(session).listar_por_programa(program_id)
    return [CourseRead.model_validate(c) for c in courses]
