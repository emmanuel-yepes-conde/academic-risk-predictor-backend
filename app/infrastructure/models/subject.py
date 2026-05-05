"""
Modelo ORM para Subject (definición de materia).
Separa el concepto académico (qué se enseña) de la oferta semestral (Course/sección).
"""

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlmodel import Field, SQLModel

from app.domain.enums import CourseStatusEnum


class Subject(SQLModel, table=True):
    __tablename__ = "subjects"
    __table_args__ = (
        sa.UniqueConstraint("code", "program_id", name="uq_subject_code_program"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    code: str = Field(nullable=False, index=True)
    name: str = Field(nullable=False)
    credits: int = Field(nullable=False)
    program_id: uuid.UUID = Field(
        foreign_key="programs.id", nullable=False, index=True
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
