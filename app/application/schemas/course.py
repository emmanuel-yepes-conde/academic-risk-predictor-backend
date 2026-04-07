"""Pydantic DTOs for Course operations."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class CourseCreate(BaseModel):
    code: str
    name: str
    credits: int
    academic_period: str


class CourseRead(BaseModel):
    id: UUID
    code: str
    name: str
    credits: int
    academic_period: str
    created_at: datetime

    model_config = {"from_attributes": True}
