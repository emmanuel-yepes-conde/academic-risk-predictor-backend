"""Pydantic DTOs for Course operations."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.enums import CourseStatusEnum


class CourseCreate(BaseModel):
    code: str = Field(..., description="Código único del curso (ej. MAT101)")
    name: str = Field(..., description="Nombre del curso")
    credits: int = Field(..., description="Número de créditos del curso")
    academic_period: str = Field(..., description="Período académico (ej. 2024-1)")
    program_id: UUID = Field(..., description="ID del programa al que pertenece el curso")


class CourseUpdate(BaseModel):
    """Schema de entrada para PATCH /courses/{course_id}. Todos los campos opcionales."""
    code: str | None = None
    name: str | None = None
    credits: int | None = None
    academic_period: str | None = None
    program_id: UUID | None = None


class CourseStatusUpdate(BaseModel):
    """Schema de entrada para PATCH /courses/{course_id}/status."""
    status: CourseStatusEnum = Field(..., description="Nuevo estado del curso (ACTIVE o INACTIVE)")


class CourseRead(BaseModel):
    id: UUID
    code: str
    name: str
    credits: int
    academic_period: str
    program_id: UUID
    professor_id: UUID | None = None
    status: CourseStatusEnum
    created_at: datetime

    model_config = {"from_attributes": True}
