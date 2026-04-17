"""Pydantic DTOs for Consent operations."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ConsentRead(BaseModel):
    id: UUID
    student_id: UUID
    accepted: bool
    terms_version: str
    accepted_at: datetime

    model_config = {"from_attributes": True}
