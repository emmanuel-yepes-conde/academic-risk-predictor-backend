"""Pydantic DTOs for Campus operations."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CampusCreate(BaseModel):
    campus_code: str = Field(..., description="Código alfanumérico de la sede (ej. MED, BOG)")
    name: str = Field(..., description="Nombre descriptivo de la sede")
    city: str = Field(..., description="Ciudad donde se ubica la sede")
    active: bool = Field(default=True, description="Estado activo/inactivo de la sede")


class CampusUpdate(BaseModel):
    name: str | None = Field(default=None, description="Nombre descriptivo de la sede")
    city: str | None = Field(default=None, description="Ciudad donde se ubica la sede")
    active: bool | None = Field(default=None, description="Estado activo/inactivo de la sede")


class CampusRead(BaseModel):
    id: UUID
    university_id: UUID
    campus_code: str
    name: str
    city: str
    active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
