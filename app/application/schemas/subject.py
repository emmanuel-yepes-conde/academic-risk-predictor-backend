"""Pydantic DTOs para operaciones de Subject (definición de materia)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.enums import CourseStatusEnum


class SubjectCreate(BaseModel):
    code: str = Field(..., description="Código único de la materia (ej. MAT-101)")
    name: str = Field(..., description="Nombre de la materia")
    credits: int = Field(..., description="Número de créditos")
    program_id: UUID = Field(..., description="ID del programa al que pertenece")


class SubjectUpdate(BaseModel):
    code: str | None = None
    name: str | None = None
    credits: int | None = None


class SubjectStatusUpdate(BaseModel):
    status: CourseStatusEnum


class SubjectRead(BaseModel):
    id: UUID
    code: str
    name: str
    credits: int
    program_id: UUID
    status: CourseStatusEnum
    created_at: datetime

    model_config = {"from_attributes": True}


class SubjectBulkRowResult(BaseModel):
    row: int
    code: str
    status: str  # 'created' | 'error'
    detail: str | None = None
    subject: SubjectRead | None = None


class SubjectBulkUploadResponse(BaseModel):
    total_rows: int
    created: int
    failed: int
    results: list[SubjectBulkRowResult]


SubjectBulkRowResult.model_rebuild()
