"""
Modelo ORM SQLModel para la entidad StudentProfile (Perfil académico del estudiante).
"""

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import sqlalchemy as sa
from sqlmodel import Field, SQLModel


class StudentProfile(SQLModel, table=True):
    __tablename__ = "student_profiles"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(
        foreign_key="users.id", unique=True, nullable=False, index=True
    )  # Relación 1-a-1 con users
    student_institutional_id: str = Field(
        unique=True, nullable=False, index=True
    )  # ID_Estud (ej. 30000032391)
    document_type: str = Field(nullable=False)         # Tp_Doc_ID (CC, TI, CE, ...)
    document_number: str = Field(nullable=False)       # Doc_ID
    birth_date: date | None = Field(default=None, nullable=True)       # Fecha_Nac
    gender: str | None = Field(default=None, nullable=True)            # Sexo (M/F)
    phone: str | None = Field(default=None, nullable=True)             # Teléfono
    socioeconomic_stratum: int | None = Field(default=None, nullable=True)  # Estrato_SocEcon (1-6)
    # Campos de período de inscripción
    academic_cycle: int | None = Field(default=None, nullable=True)    # Ciclo_Lvo
    academic_year: int | None = Field(default=None, nullable=True)     # Año_Acad
    semester: int | None = Field(default=None, nullable=True)          # Semestre
    program_action: str | None = Field(default=None, nullable=True)    # Acc_Prog (ej. RLOA)
    enrollment_status: str | None = Field(default=None, nullable=True) # Estado (ej. AC)
    enrolled_credits: Decimal | None = Field(default=None, nullable=True)  # Cred_Matric
    other_credits: Decimal | None = Field(default=None, nullable=True)     # Cred_Otro_Curso
    academic_level: int | None = Field(default=None, nullable=True)    # Nivel
    cohort: str | None = Field(default=None, nullable=True)            # Cohorte
    action_reason: str | None = Field(default=None, nullable=True)     # Mvo_Acción
    program_id: uuid.UUID | None = Field(
        default=None, foreign_key="programs.id", nullable=True
    )  # FK → programs.id
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False),
    )
