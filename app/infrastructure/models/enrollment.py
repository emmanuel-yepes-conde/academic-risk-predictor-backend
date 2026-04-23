"""
Modelo ORM SQLModel para la entidad Enrollment (Inscripción).
"""

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy import UniqueConstraint
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
