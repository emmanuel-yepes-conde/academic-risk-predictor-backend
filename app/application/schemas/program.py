"""Pydantic DTOs for Program operations."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ProgramCreate(BaseModel):
    """Schema de entrada para POST /programs. Todos los campos requeridos."""

    institution: str = Field(..., description="Institución (ej. USBCO)")
    degree_type: str = Field(..., description="Grado (ej. PREG)")
    program_code: str = Field(..., description="Código del programa (ej. M0200)")
    program_name: str = Field(..., description="Nombre del programa académico")
    academic_group: str = Field(..., description="Grupo académico (ej. MFPSI)")
    location: str = Field(..., description="Ubicación del programa (ej. SAN BENITO)")
    snies_code: int = Field(..., description="Código SNIES del Ministerio de Educación")


class ProgramUpdate(BaseModel):
    """Schema de entrada para PATCH /programs/{program_id}. Todos los campos opcionales."""

    institution: str | None = None
    degree_type: str | None = None
    program_code: str | None = None
    program_name: str | None = None
    academic_group: str | None = None
    location: str | None = None
    snies_code: int | None = None


class ProgramRead(BaseModel):
    id: UUID
    institution: str
    degree_type: str
    program_code: str
    program_name: str
    academic_group: str
    location: str
    snies_code: int
    created_at: datetime

    model_config = {"from_attributes": True}
