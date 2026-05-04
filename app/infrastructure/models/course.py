"""
Modelo ORM SQLModel para la entidad Course (Asignatura).
"""

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from app.domain.enums import CourseStatusEnum


class Course(SQLModel, table=True):
    __tablename__ = "courses"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    code: str = Field(unique=True, nullable=False, index=True)
    name: str = Field(nullable=False)
    credits: int = Field(nullable=False)
    academic_period: str = Field(nullable=False)
    program_id: uuid.UUID = Field(
        foreign_key="programs.id", nullable=False, index=True
    )  # FK → programs.id
    professor_id: uuid.UUID | None = Field(
        default=None, foreign_key="users.id", nullable=True, index=True
    )  # FK → users.id (profesor asignado, nullable)
    status: CourseStatusEnum = Field(
        default=CourseStatusEnum.ACTIVE,
        nullable=False,
        sa_column_kwargs={"server_default": "ACTIVE"},
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False),
    )

    # Configuración de evaluación: cortes, pesos y fechas.
    # Estructura: [{"id": "first_cohort", "name": "Corte Uno", "percentage": 30, "date": "2026-03-08"}, ...]
    evaluation_config: dict | None = Field(
        default=None,
        sa_column=sa.Column(JSONB, nullable=True),
    )
