"""
Modelo ORM SQLModel para la entidad Enrollment (Inscripción).
"""

import uuid
from datetime import datetime

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


class Enrollment(SQLModel, table=True):
    __tablename__ = "enrollments"
    __table_args__ = (UniqueConstraint("student_id", "course_id"),)

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    student_id: uuid.UUID = Field(foreign_key="users.id", nullable=False)
    course_id: uuid.UUID = Field(foreign_key="courses.id", nullable=False)
    enrollment_date: datetime = Field(
        default_factory=datetime.utcnow
    )
