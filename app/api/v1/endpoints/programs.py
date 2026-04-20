"""
ProgramRouter — endpoints para programas académicos y sus cursos.
Requisitos: 4.2, 4.3, 4.4, 5.3, 5.4
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.schemas.course import CourseRead
from app.infrastructure.database import get_session
from app.infrastructure.repositories.course_repository import CourseRepository
from app.infrastructure.repositories.program_repository import ProgramRepository

router = APIRouter()


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
