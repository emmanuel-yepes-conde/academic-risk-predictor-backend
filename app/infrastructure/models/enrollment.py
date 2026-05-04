"""
Modelo ORM SQLModel para la entidad Enrollment (Inscripción).
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy import UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from app.domain.enums import EnrollmentStatusEnum


class Enrollment(SQLModel, table=True):
    __tablename__ = "enrollments"
    __table_args__ = (UniqueConstraint("student_id", "course_id"),)

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    student_id: uuid.UUID = Field(foreign_key="users.id", nullable=False, index=True)
    course_id: uuid.UUID = Field(foreign_key="courses.id", nullable=False, index=True)
    status: EnrollmentStatusEnum = Field(
        default=EnrollmentStatusEnum.ACTIVE,
        nullable=False,
        sa_column_kwargs={"server_default": "ACTIVE"},
    )
    enrollment_date: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False),
    )

    # Notas del estudiante: configuración de cortes + notas por actividad.
    # Estructura: {"first_cohort": {"weight": "30%", "parcial": {"note": 4.0, "weight": "20%"}, ...}, ...}
    # Escala 0.0–5.0. Nota mínima aprobatoria: 3.0.
    grades: dict | None = Field(
        default=None,
        sa_column=sa.Column(JSONB, nullable=True),
    )

    # Columnas calculadas: se actualizan en código al modificar grades.
    first_cohort_grade: Decimal | None = Field(
        default=None,
        sa_column=sa.Column(sa.Numeric(precision=3, scale=2), nullable=True),
    )
    second_cohort_grade: Decimal | None = Field(
        default=None,
        sa_column=sa.Column(sa.Numeric(precision=3, scale=2), nullable=True),
    )
    third_cohort_grade: Decimal | None = Field(
        default=None,
        sa_column=sa.Column(sa.Numeric(precision=3, scale=2), nullable=True),
    )
    final_grade: Decimal | None = Field(
        default=None,
        sa_column=sa.Column(sa.Numeric(precision=3, scale=2), nullable=True),
    )
