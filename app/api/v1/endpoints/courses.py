"""
CourseRouter — endpoints para cursos, asignación profesor-curso
y acceso a estudiantes.
Requisitos: 5.1, 5.2
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.schemas.course import CourseRead
from app.application.schemas.professor_course import ProfessorAssign, ProfessorAssignmentRead
from app.application.schemas.user import UserRead
from app.application.services.professor_course_service import ProfessorCourseService
from app.infrastructure.database import get_session

router = APIRouter()


# ---------------------------------------------------------------------------
# Dependency helpers
# ---------------------------------------------------------------------------

def _get_professor_course_service(
    session: AsyncSession = Depends(get_session),
) -> ProfessorCourseService:
    return ProfessorCourseService(session)


# ===========================================================================
# Asignación profesor-curso y acceso a estudiantes
# ===========================================================================

@router.post(
    "/courses/{course_id}/professor",
    response_model=ProfessorAssignmentRead,
    status_code=200,
    summary="Asignar o reemplazar profesor de un curso",
    description=(
        "Asigna un profesor al curso indicado. Si el curso ya tiene un profesor "
        "asignado, lo reemplaza. El usuario debe tener rol PROFESSOR."
    ),
    tags=["Cursos"],
)
async def assign_professor_to_course(
    course_id: UUID,
    body: ProfessorAssign,
    service: ProfessorCourseService = Depends(_get_professor_course_service),
) -> ProfessorAssignmentRead:
    return await service.assign_professor(course_id, body.professor_id)


@router.get(
    "/courses/{course_id}/professor",
    response_model=UserRead,
    status_code=200,
    summary="Obtener profesor asignado a un curso",
    description=(
        "Retorna los datos del profesor asignado al curso indicado, "
        "o 404 si el curso no tiene profesor asignado."
    ),
    tags=["Cursos"],
)
async def get_course_professor(
    course_id: UUID,
    service: ProfessorCourseService = Depends(_get_professor_course_service),
) -> UserRead:
    return await service.get_course_professor(course_id)


@router.get(
    "/professors/{professor_id}/courses",
    response_model=list[CourseRead],
    status_code=200,
    summary="Listar cursos asignados a un profesor",
    description="Retorna la lista de cursos asignados al profesor indicado.",
    tags=["Profesores"],
)
async def list_courses_by_professor(
    professor_id: UUID,
    service: ProfessorCourseService = Depends(_get_professor_course_service),
) -> list[CourseRead]:
    return await service.list_professor_courses(professor_id)


@router.get(
    "/courses/{course_id}/students",
    response_model=list[UserRead],
    status_code=200,
    summary="Listar estudiantes inscritos en un curso",
    description=(
        "Retorna los estudiantes inscritos en el curso indicado. "
        "El profesor solicitante debe estar asignado al curso (RB-04). "
        "Retorna 403 si el profesor no está asignado."
    ),
    tags=["Cursos"],
)
async def list_course_students(
    course_id: UUID,
    professor_id: UUID = Query(..., description="ID del profesor que solicita el acceso"),
    service: ProfessorCourseService = Depends(_get_professor_course_service),
) -> list[UserRead]:
    return await service.list_course_students(course_id, professor_id)
