"""Pydantic DTOs for ProfessorCourse operations."""

from uuid import UUID

from pydantic import BaseModel, Field


class ProfessorAssign(BaseModel):
    professor_id: UUID = Field(..., description="ID del usuario con rol PROFESSOR a asignar al curso")


class ProfessorCourseRead(BaseModel):
    id: UUID
    professor_id: UUID
    course_id: UUID

    model_config = {"from_attributes": True}
