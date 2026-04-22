"""Pydantic DTOs for Program operations."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ProgramCreate(BaseModel):
    campus_id: UUID
    institution: str = Field(..., description="Nombre de la institución")
    degree_type: str = Field(default="PREG", description="Tipo de grado, ej: PREG, POST")
    program_code: str = Field(..., description="Código del programa, ej: IS-2024")
    program_name: str = Field(..., description="Nombre completo del programa")
    pensum: str = Field(default="", description="Pensum/versión del plan de estudios")
    academic_group: str = Field(default="", description="Grupo académico")
    location: str = Field(default="", description="Sede/ubicación")
    snies_code: int = Field(..., description="Código SNIES único del programa")


class ProgramRead(BaseModel):
    id: UUID
    university_id: UUID
    campus_id: UUID
    institution: str
    degree_type: str
    program_code: str
    program_name: str
    pensum: str
    academic_group: str
    location: str
    snies_code: int
    created_at: datetime

    model_config = {"from_attributes": True}
