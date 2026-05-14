"""
Modelo ORM para Course (sección/grupo de una materia).
Representa una oferta concreta: Subject + período + grupo + profesor.
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
    subject_id: uuid.UUID = Field(
        foreign_key="subjects.id", nullable=False, index=True
    )
    section: str = Field(nullable=False, default="A")
    academic_period: str = Field(nullable=False)
    professor_id: uuid.UUID | None = Field(
        default=None, foreign_key="users.id", nullable=True, index=True
    )
    status: CourseStatusEnum = Field(
        default=CourseStatusEnum.ACTIVE,
        nullable=False,
        sa_column_kwargs={"server_default": "ACTIVE"},
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False),
    )

    # Estructura: [{"id": "first_cohort", "name": "Corte Uno", "percentage": 30, "date": "2026-03-08"}, ...]
    evaluation_config: dict | None = Field(
        default=None,
        sa_column=sa.Column(sa.JSON().with_variant(JSONB, "postgresql"), nullable=True),
    )

    __table_args__ = (
        sa.UniqueConstraint("subject_id", "section", "academic_period",
                            name="uq_course_subject_section_period"),
    )
