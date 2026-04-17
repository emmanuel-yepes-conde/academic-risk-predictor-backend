"""
Modelo ORM SQLModel para la entidad Consent (Consentimiento ML).
"""

import uuid
from datetime import datetime

from sqlmodel import Field, SQLModel


class Consent(SQLModel, table=True):
    __tablename__ = "consents"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    student_id: uuid.UUID = Field(
        foreign_key="users.id", unique=True, nullable=False
    )
    accepted: bool = Field(nullable=False)
    terms_version: str = Field(nullable=False)
    accepted_at: datetime = Field(
        default_factory=datetime.utcnow
    )
