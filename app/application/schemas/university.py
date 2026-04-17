"""Pydantic DTOs for University operations."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class UniversityCreate(BaseModel):
    name: str = Field(..., description="Nombre oficial de la universidad")
    code: str = Field(..., description="Código único alfanumérico de la universidad")
    country: str = Field(..., description="País de la institución")
    city: str = Field(..., description="Ciudad sede principal")
    active: bool = Field(default=True, description="Estado activo/inactivo de la universidad")


class UniversityUpdate(BaseModel):
    name: str | None = Field(default=None, description="Nombre oficial de la universidad")
    country: str | None = Field(default=None, description="País de la institución")
    city: str | None = Field(default=None, description="Ciudad sede principal")
    active: bool | None = Field(default=None, description="Estado activo/inactivo de la universidad")


class UniversityRead(BaseModel):
    id: UUID
    name: str
    code: str
    country: str
    city: str
    active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
