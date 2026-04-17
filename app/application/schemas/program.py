"""Pydantic DTOs for Program operations."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ProgramRead(BaseModel):
    id: UUID
    university_id: UUID
    campus_id: UUID
    institution: str
    degree_type: str
    program_code: str
    program_name: str
    pensum: str
    academic_group: str
    location: str
    snies_code: int
    created_at: datetime

    model_config = {"from_attributes": True}
