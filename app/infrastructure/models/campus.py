"""
Modelo ORM SQLModel para la entidad Campus (Sede universitaria).
"""

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


class Campus(SQLModel, table=True):
    __tablename__ = "campuses"
    __table_args__ = (
        UniqueConstraint("university_id", "campus_code", name="uq_university_campus_code"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    university_id: uuid.UUID = Field(
        foreign_key="universities.id", nullable=False, index=True
    )
    campus_code: str = Field(nullable=False, index=True)
    name: str = Field(nullable=False)
    city: str = Field(nullable=False)
    active: bool = Field(default=True, nullable=False)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False),
    )
