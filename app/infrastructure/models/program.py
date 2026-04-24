"""
Modelo ORM SQLModel para la entidad Program (Programa académico).
"""

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlmodel import Field, SQLModel


class Program(SQLModel, table=True):
    __tablename__ = "programs"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    institution: str = Field(nullable=False)           # Institución (ej. USBCO)
    degree_type: str = Field(nullable=False)           # Grado (ej. PREG)
    program_code: str = Field(unique=True, nullable=False, index=True)  # Prog_Acad (ej. M0200)
    program_name: str = Field(nullable=False)          # Nombre_Programa
    location: str = Field(nullable=False)              # Ubicación_Prog (ej. SAN BENITO)
    snies_code: int = Field(unique=True, nullable=False, index=True)  # Código_SNIES (ej. 1361)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False),
    )
