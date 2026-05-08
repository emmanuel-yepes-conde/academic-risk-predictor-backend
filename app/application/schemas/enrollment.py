"""Pydantic DTOs for Enrollment operations."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.enums import EnrollmentStatusEnum


class EnrollmentCreate(BaseModel):
    student_id: UUID = Field(..., description="ID del estudiante a inscribir")
    course_id: UUID = Field(..., description="ID del curso en el que se inscribe")


class EnrollmentUpdate(BaseModel):
    course_id: UUID = Field(..., description="ID del nuevo curso destino")


class EnrollmentStatusUpdate(BaseModel):
    status: EnrollmentStatusEnum = Field(..., description="Nuevo estado: PENDING, ACTIVE, COMPLETED o CANCELLED")


class EnrollmentRead(BaseModel):
    id: UUID
    student_id: UUID
    course_id: UUID
    status: EnrollmentStatusEnum
    enrollment_date: datetime
    updated_at: datetime
    # Academic indicator fields (flat columns) — null until set by a professor
    asistencia:      Decimal | None = None
    seguimiento:     Decimal | None = None
    nota_parcial_1:  Decimal | None = None
    logins:          int     | None = None
    uso_tutorias:    bool    | None = None

    model_config = {"from_attributes": True}


class GradesRead(BaseModel):
    """Notas de un estudiante en una inscripción con columnas calculadas por cohorte."""

    id: UUID
    student_id: UUID
    course_id: UUID
    grades: dict | None
    first_cohort_grade: Decimal | None
    second_cohort_grade: Decimal | None
    third_cohort_grade: Decimal | None
    final_grade: Decimal | None

    model_config = {"from_attributes": True}


class GradesUpdate(BaseModel):
    grades: dict = Field(
        ...,
        description=(
            "Estructura de notas por cohorte. Ejemplo: "
            "{\"first_cohort\": {\"weight\": \"30%\", \"parcial\": {\"note\": 4.0, \"weight\": \"20%\"}, "
            "\"seguimiento\": {\"act1\": {\"note\": 3.5, \"weight\": \"10%\"}}}}"
        ),
    )


class CourseGradesStructureRead(BaseModel):
    course_id: UUID
    grades: dict | None


class IndicatorsUpdate(BaseModel):
    """Indicadores planos que el docente registra por inscripción."""

    asistencia:     float | None = Field(default=None, ge=0, le=100,  description="Porcentaje de asistencia (0–100)")
    seguimiento:    float | None = Field(default=None, ge=0, le=5,    description="Nota de seguimiento (0.0–5.0)")
    nota_parcial_1: float | None = Field(default=None, ge=0, le=5,    description="Nota parcial 1 (0.0–5.0)")
    logins:         int   | None = Field(default=None, ge=0,           description="Número de logins en plataforma LMS")
    uso_tutorias:   bool  | None = Field(default=None,                 description="Si el estudiante usó tutorías")


class RiskFromEnrollmentRequest(BaseModel):
    """Payload alternativo para predicción manual por cohortes.
    No se usa en el endpoint de riesgo por matrícula."""

    nota_corte_1: float = Field(..., ge=0, le=5, description="Nota corte 1 (0–5)")
    nota_corte_2: float = Field(..., ge=0, le=5, description="Nota corte 2 (0–5)")
    nota_corte_final: float = Field(..., ge=0, le=5, description="Nota corte final (0–5)")
    nota_total: float = Field(..., ge=0, le=5, description="Nota total ponderada (0–5)")
