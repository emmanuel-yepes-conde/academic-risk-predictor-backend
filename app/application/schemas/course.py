"""Pydantic DTOs para Course (sección/grupo de una materia)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.enums import CourseStatusEnum


class CourseCreate(BaseModel):
    subject_id: UUID = Field(..., description="ID de la materia (Subject)")
    section: str = Field(default="A", description="Identificador del grupo (ej. A, B, 1, 2)")
    academic_period: str = Field(..., description="Período académico (ej. 2025-I)")
    professor_id: UUID | None = Field(default=None, description="Profesor asignado (opcional)")


class CourseUpdate(BaseModel):
    section: str | None = None
    academic_period: str | None = None
    professor_id: UUID | None = None


class CourseStatusUpdate(BaseModel):
    status: CourseStatusEnum = Field(..., description="Nuevo estado (ACTIVE o INACTIVE)")


class CourseRead(BaseModel):
    """
    Sección de una materia. Incluye campos denormalizados del Subject
    (code, name, credits, program_id) para conveniencia del cliente.
    """
    id: UUID
    subject_id: UUID
    section: str
    academic_period: str
    professor_id: UUID | None = None
    status: CourseStatusEnum
    created_at: datetime
    # Denormalizados desde Subject:
    code: str
    name: str
    credits: int
    program_id: UUID

    model_config = {"from_attributes": False}
