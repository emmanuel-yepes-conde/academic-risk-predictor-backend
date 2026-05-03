"""Pydantic DTOs for Enrollment operations."""

from datetime import datetime
from decimal import Decimal
from typing import Optional
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


class EnrollmentGradesUpdate(BaseModel):
    """Payload to set academic indicators for an enrollment (sent by professors)."""
    asistencia:     Optional[float] = Field(None, ge=0, le=100,  description="Attendance % (0-100)")
    seguimiento:    Optional[float] = Field(None, ge=0, le=5.0,  description="Engagement grade (0-5)")
    nota_parcial_1: Optional[float] = Field(None, ge=0, le=5.0,  description="First partial exam grade (0-5)")
    logins:         Optional[int]   = Field(None, ge=0,           description="LMS session count")
    uso_tutorias:   Optional[bool]  = Field(None,                 description="Whether the student uses tutoring")


class EnrollmentRead(BaseModel):
    id: UUID
    student_id: UUID
    course_id: UUID
    status: EnrollmentStatusEnum
    enrollment_date: datetime
    updated_at: datetime
    # Academic indicators — null if not yet set by professor
    asistencia:     Optional[Decimal] = None
    seguimiento:    Optional[Decimal] = None
    nota_parcial_1: Optional[Decimal] = None
    logins:         Optional[int]     = None
    uso_tutorias:   Optional[bool]    = None

    model_config = {"from_attributes": True}
