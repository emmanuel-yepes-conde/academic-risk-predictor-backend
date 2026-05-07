"""Pydantic DTOs para Course (sección/grupo de una materia)."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

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
    evaluation_config: dict | None = None

    model_config = {"from_attributes": False}


class CutActivity(BaseModel):
    id: str = Field(..., description="Identificador de la actividad (ej: 'act_parcial')")
    name: str = Field(..., description="Nombre de la actividad, ej: 'Parcial 1'")
    percentage: int = Field(..., ge=0, le=100, description="Porcentaje de la actividad dentro del corte")


class CutConfig(BaseModel):
    id: str = Field(..., description="first_cohort | second_cohort | third_cohort")
    name: str = Field(..., description="Nombre del corte, ej: 'Corte Uno'")
    percentage: int = Field(..., ge=0, le=100, description="Peso total del corte en %")
    evaluation_date: date | None = Field(default=None, description="Fecha de evaluación del corte")
    activities: list[CutActivity] = Field(default_factory=list, description="Actividades que componen el corte")


class EvaluationConfigUpdate(BaseModel):
    # Compatibilidad:
    # - Nuevo payload: {"evaluation_config": {...}}
    # - Legacy payload: {"cuts": [...]}
    evaluation_config: dict | None = Field(default=None, description="Configuración completa a persistir")
    cuts: list[CutConfig] | None = Field(default=None, description="Lista de cortes (formato legacy)")

    @model_validator(mode="after")
    def _validate_payload(self) -> "EvaluationConfigUpdate":
        if self.evaluation_config is None and self.cuts is None:
            raise ValueError("Debe enviar 'evaluation_config' o 'cuts'")
        return self

    def to_storage_config(self) -> dict:
        if self.evaluation_config is not None:
            return self.evaluation_config
        return {"cuts": [cut.model_dump(mode="json") for cut in (self.cuts or [])]}
