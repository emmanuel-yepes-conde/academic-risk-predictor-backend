"""Pydantic DTOs para la entidad Referral (remisión a permanencia)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.enums import AsistioEnum, ReferralStatusEnum, ReferralTypeEnum

# ── Tipos de remisión expuestos al frontend ───────────────────────────────────

REFERRAL_TYPE_OPTIONS = [
    ReferralTypeEnum.BAJO_RENDIMIENTO,
    ReferralTypeEnum.INASISTENCIA,
    ReferralTypeEnum.INCUMPLIMIENTO,
    ReferralTypeEnum.PROBLEMAS_PERSONALES,
    ReferralTypeEnum.DIFICULTADES_ECONOMICAS,
    ReferralTypeEnum.PROBLEMAS_SALUD,
    ReferralTypeEnum.OTROS,
]


# ── Create ─────────────────────────────────────────────────────────────────────

class ReferralCreate(BaseModel):
    referral_type:       ReferralTypeEnum = Field(..., description="Tipo de remisión")
    referral_type_other: str | None       = Field(
        default=None,
        max_length=255,
        description="Descripción libre cuando referral_type == 'Otros'",
    )
    observations:  str  = Field(..., min_length=5, description="Observaciones del docente")
    referral_date: date = Field(..., description="Fecha de la remisión (YYYY-MM-DD)")


# ── Update (consejero/profesor actualiza después) ─────────────────────────────

class ReferralUpdate(BaseModel):
    counselor_observations: str | None        = Field(default=None)
    attended:               AsistioEnum | None = Field(default=None)
    status:                 ReferralStatusEnum | None = Field(default=None)


# ── Read ───────────────────────────────────────────────────────────────────────

class ReferralRead(BaseModel):
    id:                     UUID
    enrollment_id:          UUID
    created_by:             UUID
    referral_type:          ReferralTypeEnum
    referral_type_other:    str | None
    observations:           str
    counselor_observations: str | None
    referral_date:          date
    attended:               AsistioEnum
    status:                 ReferralStatusEnum
    created_at:             datetime
    updated_at:             datetime

    model_config = {"from_attributes": True}


# ── EvaluationConfig (cortes de curso) ────────────────────────────────────────

class CutActivity(BaseModel):
    id:         str = Field(..., description="Identificador de la actividad (ej: 'act_parcial')")
    name:       str = Field(..., description="Nombre de la actividad, ej: 'Parcial 1'")
    percentage: int = Field(..., ge=0, le=100, description="Porcentaje de la actividad dentro del corte")


class CutConfig(BaseModel):
    id:              str                = Field(..., description="first_cohort | second_cohort | third_cohort")
    name:            str                = Field(..., description="Nombre del corte, ej: 'Corte Uno'")
    percentage:      int                = Field(..., ge=0, le=100, description="Peso total del corte en %")
    evaluation_date: Optional[date]     = Field(default=None, description="Fecha de evaluación del corte")
    activities:      list[CutActivity]  = Field(default_factory=list, description="Actividades que componen el corte")


class EvaluationConfigUpdate(BaseModel):
    cuts: list[CutConfig] = Field(
        ...,
        description="Lista de cortes con nombre, porcentaje y fecha",
    )


class EvaluationConfigRead(BaseModel):
    course_id: UUID
    cuts:      list[CutConfig]

    model_config = {"from_attributes": True}
