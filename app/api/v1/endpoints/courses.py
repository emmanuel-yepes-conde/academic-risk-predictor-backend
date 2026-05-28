"""
CourseRouter — endpoints CRUD para secciones de materias,
asignación profesor-sección y acceso a estudiantes.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.schemas.course import (
    CourseCreate,
    CourseRead,
    CourseStatusUpdate,
    CourseUpdate,
    EvaluationConfigUpdate,
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


def _get_course_service(
    session: AsyncSession = Depends(get_session),
) -> CourseService:
    return CourseService(CourseRepository(session))


def _get_professor_course_service(
    session: AsyncSession = Depends(get_session),
) -> ProfessorCourseService:
    return ProfessorCourseService(session)


@router.get(
    "/courses",
    response_model=PaginatedResponse[CourseRead],
    status_code=200,
    summary="Listar secciones con paginación",
    description="Retorna secciones (grupos) con datos de la materia denormalizados.",
    tags=["Secciones"],
)
async def list_courses(
    status: CourseStatusEnum | None = Query(None),
    subject_id: UUID | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: CurrentUser = Depends(get_current_user),
    service: CourseService = Depends(_get_course_service),
) -> PaginatedResponse[CourseRead]:
    return await service.list_courses(status, skip, limit, subject_id)


@router.get(
    "/courses/{course_id}",
    response_model=CourseRead,
    status_code=200,
    summary="Obtener una sección por ID",
    tags=["Secciones"],
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
    summary="Crear una sección",
    description=(
        "Crea una sección de una materia para un período académico. "
        "Requiere subject_id, section (ej. 'A'), academic_period. "
        "Requiere rol ADMIN."
    ),
    tags=["Secciones"],
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
    summary="Actualizar parcialmente una sección",
    description="Actualiza section, academic_period o professor_id. Requiere rol ADMIN.",
    tags=["Secciones"],
)
async def update_course(
    course_id: UUID,
    body: CourseUpdate,
    current_user: CurrentUser = Depends(require_roles(RoleEnum.ADMIN)),
    service: CourseService = Depends(_get_course_service),
) -> CourseRead:
    return await service.update_course(course_id, body)


@router.patch(
    "/courses/{course_id}/evaluation-config",
    response_model=CourseRead,
    status_code=200,
    summary="Guardar distribución de evaluación de una sección",
    description="Persiste la configuración de cortes y componentes. Requiere rol PROFESSOR o ADMIN.",
    tags=["Secciones"],
)
async def save_evaluation_config(
    course_id: UUID,
    body: EvaluationConfigUpdate,
    current_user: CurrentUser = Depends(require_roles(RoleEnum.PROFESSOR, RoleEnum.ADMIN)),
    service: CourseService = Depends(_get_course_service),
) -> CourseRead:
    return await service.save_evaluation_config(course_id, body, current_user)


@router.patch(
    "/courses/{course_id}/status",
    response_model=CourseRead,
    status_code=200,
    summary="Cambiar estado de una sección",
    tags=["Secciones"],
)
async def update_course_status(
    course_id: UUID,
    body: CourseStatusUpdate,
    current_user: CurrentUser = Depends(require_roles(RoleEnum.ADMIN)),
    service: CourseService = Depends(_get_course_service),
) -> CourseRead:
    return await service.update_course_status(course_id, body)


# ===========================================================================
# Asignación profesor y acceso a estudiantes
# ===========================================================================

@router.post(
    "/courses/{course_id}/professor",
    response_model=ProfessorAssignmentRead,
    status_code=200,
    summary="Asignar o reemplazar profesor de una sección",
    tags=["Secciones"],
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
    summary="Obtener profesor asignado a una sección",
    tags=["Secciones"],
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
    summary="Listar secciones asignadas a un profesor",
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
    summary="Listar estudiantes inscritos en una sección",
    tags=["Secciones"],
)
async def list_course_students(
    course_id: UUID,
    professor_id: UUID = Query(..., description="ID del profesor que solicita el acceso"),
    service: ProfessorCourseService = Depends(_get_professor_course_service),
) -> list[UserRead]:
    return await service.list_course_students(course_id, professor_id)


@router.get(
    "/professors/{professor_id}/courses-summary",
    response_model=dict[str, int],
    status_code=200,
    summary="Conteo de estudiantes por curso de un profesor (bulk)",
    description=(
        "Devuelve un mapa {course_id: student_count} para todos los cursos "
        "asignados al profesor, en una sola query. Evita el N+1 del dashboard."
    ),
    tags=["Profesores"],
)
async def get_professor_courses_summary(
    professor_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: CourseService = Depends(_get_course_service),
) -> dict[str, int]:
    counts = await service._repo.get_student_counts_for_professor(professor_id)
    return {str(k): v for k, v in counts.items()}


@router.delete(
    "/courses/{course_id}/students/{student_id}",
    status_code=200,
    summary="Eliminar estudiante de un curso",
    description="Desvincula al estudiante del curso. Requiere rol PROFESSOR (propio curso) o ADMIN.",
    tags=["Secciones"],
)
async def unenroll_student_from_course(
    course_id: UUID,
    student_id: UUID,
    current_user: CurrentUser = Depends(require_roles(RoleEnum.PROFESSOR, RoleEnum.ADMIN)),
    service: ProfessorCourseService = Depends(_get_professor_course_service),
) -> dict:
    removed = await service.unenroll_student(course_id, student_id, current_user)
    if not removed:
        raise HTTPException(status_code=404, detail="El estudiante no está inscrito en este curso")
    return {"success": True, "message": "Estudiante eliminado del curso"}
