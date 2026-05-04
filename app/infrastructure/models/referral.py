"""
Modelo ORM SQLModel para la entidad Referral (Remisión a permanencia/consejería).
"""

import uuid
from datetime import datetime, date, timezone

import sqlalchemy as sa
from sqlmodel import Field, SQLModel

from app.domain.enums import AsistioEnum, ReferralStatusEnum, ReferralTypeEnum


class Referral(SQLModel, table=True):
    __tablename__ = "referrals"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)

    enrollment_id: uuid.UUID = Field(
        foreign_key="enrollments.id", nullable=False, index=True
    )
    created_by: uuid.UUID = Field(
        foreign_key="users.id", nullable=False, index=True,
        description="Profesor que crea la remisión",
    )

    # Tipo de remisión — columnas VARCHAR explícitas para evitar que SQLAlchemy
    # infiera tipos ENUM de PostgreSQL que no existen en la DB.
    tipo_remision: ReferralTypeEnum = Field(
        sa_column=sa.Column(sa.String(100), nullable=False),
    )
    tipo_remision_otro: str | None = Field(
        default=None,
        sa_column=sa.Column(sa.Text, nullable=True),
        description="Descripción libre cuando tipo_remision == 'Otros'",
    )

    observaciones: str = Field(
        sa_column=sa.Column(sa.Text, nullable=False),
        description="Observaciones del docente al momento de remitir",
    )

    # Campos que actualiza el consejero/permanencia después
    observaciones_remision: str | None = Field(
        default=None,
        sa_column=sa.Column(sa.Text, nullable=True),
        description="Observaciones del consejero tras la atención",
    )

    fecha_remision: date = Field(
        sa_column=sa.Column(sa.Date, nullable=False),
        description="Fecha en que se realiza la remisión",
    )

    asistio: AsistioEnum = Field(
        default=AsistioEnum.SIN_CONFIRMAR,
        sa_column=sa.Column(
            sa.String(30),
            nullable=False,
            server_default="Sin confirmar",
        ),
    )

    status: ReferralStatusEnum = Field(
        default=ReferralStatusEnum.PENDIENTE,
        sa_column=sa.Column(
            sa.String(20),
            nullable=False,
            server_default="PENDIENTE",
        ),
    )

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False),
    )
