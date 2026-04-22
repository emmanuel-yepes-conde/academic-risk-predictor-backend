"""
CourseRouter — endpoints CRUD para cursos, asignación profesor-curso
y acceso a estudiantes.
Requisitos: 5.1, 5.2, 7.1–7.6, 8.1–8.5, 9.1–9.7, 10.1–10.8, 11.1–11.8
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.schemas.course import (
    CourseCreate,
    CourseRead,
    CourseStatusUpdate,
    CourseUpdate,
)
from app.application.schemas.professor_course import ProfessorAssign, ProfessorAssignmentRead
from app.application.schemas.user import PaginatedResponse, UserRead
from app.application.services.course_service import CourseService
from app.application.services.professor_course_service import ProfessorCourseService
from app.api.v1.dependencies.auth import CurrentUser, get_current_user, require_roles
from app.domain.enums import CourseStatusEnum, RoleEnum
from app.infrastructure.database import get_session
from app.infrastructure.repositories.course_repository import CourseRepository

router = APIRouter()


# ---------------------------------------------------------------------------
# Dependency helpers
# ---------------------------------------------------------------------------

def _get_course_service(
    session: AsyncSession = Depends(get_session),
) -> CourseService:
    return CourseService(CourseRepository(session))


def _get_professor_course_service(
    session: AsyncSession = Depends(get_session),
) -> ProfessorCourseService:
    return ProfessorCourseService(session)


# ===========================================================================
# CRUD endpoints — deben ir ANTES de las rutas parametrizadas existentes
# ===========================================================================

@router.get(
    "/courses",
    response_model=PaginatedResponse[CourseRead],
    status_code=200,
    summary="Listar cursos con paginación",
    description="Retorna una lista paginada de cursos. Por defecto solo muestra cursos ACTIVE.",
    tags=["Cursos"],
)
async def list_courses(
    status: CourseStatusEnum | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: CurrentUser = Depends(get_current_user),
    service: CourseService = Depends(_get_course_service),
) -> PaginatedResponse[CourseRead]:
    return await service.list_courses(status, skip, limit)


@router.get(
    "/courses/{course_id}",
    response_model=CourseRead,
    status_code=200,
    summary="Obtener un curso por ID",
    description="Retorna los datos de un curso específico, o 404 si no existe.",
    tags=["Cursos"],
)
async def get_course(
    course_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: CourseService = Depends(_get_course_service),
) -> CourseRead:
    return await service.get_course(course_id)


@router.post(
    "/courses",
    response_model=CourseRead,
    status_code=201,
    summary="Crear un curso",
    description="Crea un nuevo curso. Requiere rol ADMIN. Valida unicidad de code.",
    tags=["Cursos"],
)
async def create_course(
    body: CourseCreate,
    current_user: CurrentUser = Depends(require_roles(RoleEnum.ADMIN)),
    service: CourseService = Depends(_get_course_service),
) -> CourseRead:
    return await service.create_course(body)


@router.patch(
    "/courses/{course_id}",
    response_model=CourseRead,
    status_code=200,
    summary="Actualizar parcialmente un curso",
    description="Actualiza los campos proporcionados de un curso existente. "
                "Requiere rol ADMIN. Valida unicidad de code.",
    tags=["Cursos"],
)
async def update_course(
    course_id: UUID,
    body: CourseUpdate,
    current_user: CurrentUser = Depends(require_roles(RoleEnum.ADMIN)),
    service: CourseService = Depends(_get_course_service),
) -> CourseRead:
    return await service.update_course(course_id, body)


@router.patch(
    "/courses/{course_id}/status",
    response_model=CourseRead,
    status_code=200,
    summary="Cambiar estado de un curso (soft delete / reactivación)",
    description="Cambia el estado de un curso a ACTIVE o INACTIVE. Requiere rol ADMIN.",
    tags=["Cursos"],
)
async def update_course_status(
    course_id: UUID,
    body: CourseStatusUpdate,
    current_user: CurrentUser = Depends(require_roles(RoleEnum.ADMIN)),
    service: CourseService = Depends(_get_course_service),
) -> CourseRead:
    return await service.update_course_status(course_id, body.status)


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
