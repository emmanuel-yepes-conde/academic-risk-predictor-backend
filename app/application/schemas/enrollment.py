"""Pydantic DTOs for Enrollment operations."""

from datetime import datetime
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
