"""
Modelo ORM SQLModel para la entidad User.
"""

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlmodel import Field, SQLModel

from app.domain.enums import RoleEnum, UserStatusEnum


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    email: str = Field(unique=True, nullable=False, index=True)
    institutional_email: str | None = Field(
        default=None, unique=True, nullable=True, index=True
    )  # Correo_E — correo institucional USBCO (ej. PIPE@TAU.USBMED.EDU.CO)
    full_name: str = Field(nullable=False)
    role: RoleEnum = Field(nullable=False)
    microsoft_oid: str | None = Field(default=None, unique=True, nullable=True)
    google_oid: str | None = Field(default=None, unique=True, nullable=True)
    password_hash: str | None = Field(default=None, nullable=True)
    ml_consent: bool = Field(default=False)
    status: UserStatusEnum = Field(
        default=UserStatusEnum.ACTIVE,
        nullable=False,
        sa_column_kwargs={"server_default": "ACTIVE"},
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False),
    )
