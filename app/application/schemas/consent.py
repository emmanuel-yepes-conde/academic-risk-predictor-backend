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


class ConsentStatus(BaseModel):
    """Estado actual del consentimiento ML para el estudiante autenticado.

    ``has_accepted`` es ``True`` solo si existe registro con ``accepted=True``
    y ``terms_version`` igual a la versión vigente (``current_terms_version``).
    """

    has_accepted: bool
    current_terms_version: str
    consent: ConsentRead | None = None


class ConsentAcceptRequest(BaseModel):
    accepted: bool = True
