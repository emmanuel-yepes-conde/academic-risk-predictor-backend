"""
UniversityRouter — endpoints CRUD para universidades, jerarquía académica
y asignación profesor-curso.
Requisitos: 1.2–1.7, 2.4, 3.4, 3.5, 4.1–4.6, 5.1, 5.3
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.schemas.course import CourseRead
from app.application.schemas.professor_course import ProfessorAssign, ProfessorCourseRead
from app.application.schemas.program import ProgramRead
from app.application.schemas.university import UniversityCreate, UniversityRead, UniversityUpdate
from app.application.schemas.user import PaginatedResponse, UserRead
from app.application.services.professor_course_service import ProfessorCourseService
from app.application.services.university_service import UniversityService
from app.domain.enums import RoleEnum
from app.infrastructure.database import get_session
from app.infrastructure.models.program import Program
from app.infrastructure.repositories.course_repository import CourseRepository
from app.infrastructure.repositories.university_repository import UniversityRepository

router = APIRouter()


# ---------------------------------------------------------------------------
# Dependency helpers
# ---------------------------------------------------------------------------

def _get_university_service(
    session: AsyncSession = Depends(get_session),
) -> UniversityService:
    return UniversityService(UniversityRepository(session))


def _get_session(session: AsyncSession = Depends(get_session)) -> AsyncSession:
    return session


def _get_professor_course_service(
    session: AsyncSession = Depends(get_session),
) -> ProfessorCourseService:
    return ProfessorCourseService(session)


# ===========================================================================
# 8.1 — CRUD de universidades
# ===========================================================================

@router.post(
    "/universities",
    response_model=UniversityRead,
    status_code=201,
    summary="Crear una nueva universidad",
    description="Registra una nueva universidad en el sistema. Requiere rol ADMIN.",
    tags=["Universidades"],
)
async def create_university(
    body: UniversityCreate,
    actor_role: RoleEnum = Query(..., description="Rol del actor que realiza la operación"),
    service: UniversityService = Depends(_get_university_service),
) -> UniversityRead:
    return await service.create(body, actor_role)


@router.get(
    "/universities",
    response_model=PaginatedResponse[UniversityRead],
    status_code=200,
    summary="Listar universidades",
    description="Retorna la lista paginada de universidades registradas.",
    tags=["Universidades"],
)
async def list_universities(
    skip: int = Query(0, ge=0, description="Número de registros a omitir"),
    limit: int = Query(20, ge=1, le=100, description="Cantidad máxima de registros"),
    service: UniversityService = Depends(_get_university_service),
) -> PaginatedResponse[UniversityRead]:
    return await service.list(skip=skip, limit=limit)


@router.get(
    "/universities/{university_id}",
    response_model=UniversityRead,
    status_code=200,
    summary="Obtener universidad por ID",
    description="Retorna los datos de una universidad específica o 404 si no existe.",
    tags=["Universidades"],
)
async def get_university(
    university_id: UUID,
    service: UniversityService = Depends(_get_university_service),
) -> UniversityRead:
    return await service.get(university_id)


@router.patch(
    "/universities/{university_id}",
    response_model=UniversityRead,
    status_code=200,
    summary="Actualizar universidad",
    description="Actualiza parcialmente los datos de una universidad. Requiere rol ADMIN.",
    tags=["Universidades"],
)
async def update_university(
    university_id: UUID,
    body: UniversityUpdate,
    actor_role: RoleEnum = Query(..., description="Rol del actor que realiza la operación"),
    service: UniversityService = Depends(_get_university_service),
) -> UniversityRead:
    return await service.update(university_id, body, actor_role)


# ===========================================================================
# 8.2 — Endpoints jerárquicos
# ===========================================================================

@router.get(
    "/universities/{university_id}/programs",
    response_model=PaginatedResponse[ProgramRead],
    status_code=200,
    summary="Listar programas de una universidad",
    description=(
        "Retorna los programas académicos pertenecientes a la universidad indicada, "
        "con paginación. Garantiza aislamiento de datos por universidad."
    ),
    tags=["Universidades"],
)
async def list_programs_by_university(
    university_id: UUID,
    skip: int = Query(0, ge=0, description="Número de registros a omitir"),
    limit: int = Query(20, ge=1, le=100, description="Cantidad máxima de registros"),
    session: AsyncSession = Depends(get_session),
) -> PaginatedResponse[ProgramRead]:
    # Verify university exists
    uni_result = await session.execute(
        select(func.count()).select_from(
            select(Program.id).where(Program.university_id == university_id).correlate(None).subquery()
        )
    )
    # We don't 404 on the university here — an empty list is valid.
    # But we do need total + page.
    count_stmt = (
        select(func.count())
        .select_from(Program)
        .where(Program.university_id == university_id)
    )
    total_result = await session.execute(count_stmt)
    total = total_result.scalar_one()

    stmt = (
        select(Program)
        .where(Program.university_id == university_id)
        .offset(skip)
        .limit(limit)
    )
    result = await session.execute(stmt)
    programs = list(result.scalars().all())

    return PaginatedResponse[ProgramRead](
        data=[ProgramRead.model_validate(p) for p in programs],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/programs/{program_id}/courses",
    response_model=list[CourseRead],
    status_code=200,
    summary="Listar cursos de un programa",
    description="Retorna los cursos pertenecientes al programa indicado.",
    tags=["Programas"],
)
async def list_courses_by_program(
    program_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> list[CourseRead]:
    repo = CourseRepository(session)
    courses = await repo.listar_por_programa(program_id)
    return [CourseRead.model_validate(c) for c in courses]


@router.get(
    "/universities/{university_id}/programs/{program_id}/courses",
    response_model=list[CourseRead],
    status_code=200,
    summary="Listar cursos de un programa dentro de una universidad",
    description=(
        "Retorna los cursos del programa indicado, validando que el programa "
        "pertenezca a la universidad. Retorna 404 si el programa no pertenece "
        "a la universidad."
    ),
    tags=["Universidades"],
)
async def list_courses_by_university_and_program(
    university_id: UUID,
    program_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> list[CourseRead]:
    # Validate that the program belongs to the university
    program_result = await session.execute(
        select(Program).where(
            Program.id == program_id,
            Program.university_id == university_id,
        )
    )
    program = program_result.scalar_one_or_none()
    if program is None:
        raise HTTPException(
            status_code=404,
            detail="El programa no pertenece a la universidad indicada",
        )

    repo = CourseRepository(session)
    courses = await repo.listar_por_universidad_y_programa(university_id, program_id)
    return [CourseRead.model_validate(c) for c in courses]


# ===========================================================================
# 8.3 — Asignación profesor-curso y acceso a estudiantes
# ===========================================================================

@router.post(
    "/courses/{course_id}/professor",
    response_model=ProfessorCourseRead,
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
) -> ProfessorCourseRead:
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
