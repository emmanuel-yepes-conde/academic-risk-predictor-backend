"""Modelo de suscripciones a push notifications web (VAPID)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlmodel import Field, SQLModel


class PushSubscription(SQLModel, table=True):
    """
    Almacena las suscripciones WebPush de los usuarios.
    Cada registro corresponde a un dispositivo/navegador.
    """

    __tablename__ = "push_subscriptions"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        description="Identificador único de la suscripción",
    )
    user_id: uuid.UUID = Field(
        nullable=False,
        description="Usuario dueño de esta suscripción",
        index=True,
    )
    endpoint: str = Field(
        nullable=False,
        description="URL del push service del navegador (único por dispositivo)",
    )
    p256dh: str = Field(
        nullable=False,
        description="Clave pública del cliente (cifrado del payload)",
    )
    auth: str = Field(
        nullable=False,
        description="Secret de autenticación del cliente",
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        nullable=False,
    )

    class Config:
        # endpoint puede ser una URL larga
        arbitrary_types_allowed = True
