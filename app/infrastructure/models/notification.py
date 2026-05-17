"""
Modelo ORM para notificaciones in-app.
Cada registro = una notificación para un usuario (estudiante o profesor).
"""

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlmodel import Field, SQLModel


class Notification(SQLModel, table=True):
    __tablename__ = "notifications"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(nullable=False, index=True)

    # Clasificación
    type: str = Field(nullable=False, index=True)
    # Tipos posibles:
    #   RISK_ALTO        — riesgo alto calculado para el estudiante
    #   RISK_RECOVERED   — riesgo bajó a BAJO/MEDIO
    #   ATTENDANCE       — asistencia registrada
    #   GRADE_UPDATE     — profesor actualizó nota
    #   CLASS_CRISIS     — >35% del grupo en riesgo ALTO (para profesor)
    #   SYSTEM           — mensaje general del sistema

    # Contenido visible
    title: str = Field(nullable=False, max_length=120)
    body: str = Field(nullable=False)

    # Datos adicionales de contexto (course_id, enrollment_id, etc.)
    data: dict | None = Field(
        default=None,
        sa_column=sa.Column(sa.JSON, nullable=True),
    )

    read: bool = Field(default=False, nullable=False)
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=sa.Column(sa.DateTime, nullable=False, index=True),
    )
