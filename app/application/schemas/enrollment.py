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


class RiskFromEnrollmentRequest(BaseModel):
    """Datos adicionales que el estudiante provee para calcular su riesgo.
    El sistema extrae automáticamente nota_parcial_1 y promedio_seguimiento de grades."""

    promedio_asistencia: float = Field(
        ..., ge=0, le=100, description="Porcentaje de asistencia (0–100)"
    )
    inicios_sesion_plataforma: int = Field(
        ..., ge=0, description="Número de logins en la plataforma LMS"
    )
    uso_tutorias: int = Field(
        ..., ge=0, le=10, description="Número de sesiones de tutoría utilizadas (0–10)"
    )
