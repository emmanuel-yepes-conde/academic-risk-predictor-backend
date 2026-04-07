"""
Modelo ORM SQLModel para la entidad ProfessorCourse (Docente-Asignatura).
"""

import uuid

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


class ProfessorCourse(SQLModel, table=True):
    __tablename__ = "professor_courses"
    __table_args__ = (UniqueConstraint("professor_id", "course_id"),)

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    professor_id: uuid.UUID = Field(foreign_key="users.id", nullable=False)
    course_id: uuid.UUID = Field(foreign_key="courses.id", nullable=False)
