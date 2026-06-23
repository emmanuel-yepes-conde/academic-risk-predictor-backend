"""
Modelos ORM para el sistema de control de asistencias con QR.

ClassSession  → sesión de clase creada por el profesor (genera el QR)
Attendance    → registro de asistencia de un estudiante a una sesión
"""

import uuid
import secrets
from datetime import datetime

from sqlmodel import Field, SQLModel


class ClassSession(SQLModel, table=True):
    """
    Una sesión de clase abierta por el profesor.
    El QR rota cada `window_seconds` segundos mientras la sesión está activa.
    """
    __tablename__ = "class_sessions"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    course_id: uuid.UUID = Field(
        foreign_key="courses.id", nullable=False, index=True
    )
    professor_id: uuid.UUID = Field(nullable=False)

    # Ventana temporal del QR en segundos (el profesor elige: 30, 60, 120, 300…)
    window_seconds: int = Field(default=60, nullable=False)

    # Semilla aleatoria: combinada con floor(now / window_seconds) genera el token rotativo
    qr_seed: str = Field(
        default_factory=lambda: secrets.token_hex(16),
        nullable=False,
    )

    label: str | None = Field(default=None, nullable=True)   # ej. "Clase 5 — Derivadas"
    is_active: bool = Field(default=True, nullable=False)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    closed_at: datetime | None = Field(default=None, nullable=True)


class Attendance(SQLModel, table=True):
    """Un registro de asistencia: estudiante → sesión."""
    __tablename__ = "attendances"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    session_id: uuid.UUID = Field(nullable=False, index=True)
    student_id: uuid.UUID = Field(nullable=False, index=True)
    recorded_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    # Token QR que presentó el estudiante (para auditoría)
    qr_token_used: str = Field(nullable=False)
