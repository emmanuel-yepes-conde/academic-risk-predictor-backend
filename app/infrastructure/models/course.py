"""
Modelo ORM SQLModel para la entidad Course (Asignatura).
"""

import uuid
from datetime import datetime

from sqlmodel import Field, SQLModel


class Course(SQLModel, table=True):
    __tablename__ = "courses"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    code: str = Field(unique=True, nullable=False, index=True)
    name: str = Field(nullable=False)
    credits: int = Field(nullable=False)
    academic_period: str = Field(nullable=False)
    created_at: datetime = Field(
        default_factory=datetime.utcnow
    )
