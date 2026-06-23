"""Endpoints CRUD para Subject (definición de materia) + carga masiva CSV."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.schemas.subject import (
    SubjectBulkUploadResponse,
    SubjectCreate,
    SubjectRead,
    SubjectStatusUpdate,
    SubjectUpdate,
)
from app.application.services.subject_service import SubjectService
from app.api.v1.dependencies.auth import CurrentUser, get_current_user, require_roles
from app.domain.enums import RoleEnum
from app.infrastructure.database import get_session
from app.infrastructure.repositories.subject_repository import SubjectRepository

router = APIRouter()


def _get_service(session: AsyncSession = Depends(get_session)) -> SubjectService:
    return SubjectService(SubjectRepository(session))


@router.post(
    "/subjects",
    response_model=SubjectRead,
    status_code=201,
    summary="Crear una materia",
    description="Crea la definición de una materia para un programa. Requiere rol ADMIN.",
    tags=["Materias"],
)
async def create_subject(
    data: SubjectCreate,
    current_user: CurrentUser = Depends(require_roles(RoleEnum.ADMIN)),
    service: SubjectService = Depends(_get_service),
) -> SubjectRead:
    return await service.create_subject(data)


@router.get(
    "/subjects/{subject_id}",
    response_model=SubjectRead,
    status_code=200,
    summary="Obtener una materia por ID",
    tags=["Materias"],
)
async def get_subject(
    subject_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: SubjectService = Depends(_get_service),
) -> SubjectRead:
    return await service.get_subject(subject_id)


@router.patch(
    "/subjects/{subject_id}",
    response_model=SubjectRead,
    status_code=200,
    summary="Actualizar parcialmente una materia",
    description="Actualiza code, name o credits. Requiere rol ADMIN.",
    tags=["Materias"],
)
async def update_subject(
    subject_id: UUID,
    data: SubjectUpdate,
    current_user: CurrentUser = Depends(require_roles(RoleEnum.ADMIN)),
    service: SubjectService = Depends(_get_service),
) -> SubjectRead:
    return await service.update_subject(subject_id, data)


@router.patch(
    "/subjects/{subject_id}/status",
    response_model=SubjectRead,
    status_code=200,
    summary="Cambiar estado de una materia",
    tags=["Materias"],
)
async def update_subject_status(
    subject_id: UUID,
    data: SubjectStatusUpdate,
    current_user: CurrentUser = Depends(require_roles(RoleEnum.ADMIN)),
    service: SubjectService = Depends(_get_service),
) -> SubjectRead:
    return await service.update_status(subject_id, data)


@router.delete(
    "/subjects/{subject_id}",
    response_model=None,
    status_code=204,
    summary="Eliminar una materia",
    description=(
        "Elimina una materia y todos sus recursos asociados en cascada: "
        "secciones, inscripciones, notas, remisiones, sesiones de clase y "
        "asistencias. Los usuarios (estudiantes y profesores) se conservan; "
        "solo se eliminan sus vínculos con la materia. Requiere rol ADMIN."
    ),
    tags=["Materias"],
)
async def delete_subject(
    subject_id: UUID,
    current_user: CurrentUser = Depends(require_roles(RoleEnum.ADMIN)),
    service: SubjectService = Depends(_get_service),
) -> None:
    await service.delete_subject(subject_id)


@router.post(
    "/subjects/bulk",
    response_model=SubjectBulkUploadResponse,
    status_code=200,
    summary="Carga masiva de materias desde CSV",
    description=(
        "Crea múltiples materias a partir de un CSV. "
        "Columnas requeridas: code, name, credits. "
        "El program_id se recibe como query parameter. "
        "Si el CSV incluye columna program_id o academic_period, se ignoran. "
        "Requiere rol ADMIN."
    ),
    tags=["Materias"],
)
async def bulk_create_subjects(
    program_id: UUID = Query(..., description="UUID del programa al que pertenecen las materias"),
    file: UploadFile = File(..., description="Archivo CSV"),
    current_user: CurrentUser = Depends(require_roles(RoleEnum.ADMIN)),
    service: SubjectService = Depends(_get_service),
) -> SubjectBulkUploadResponse:
    content = await file.read()
    return await service.bulk_create_from_csv(content, program_id)
