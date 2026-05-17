"""
Endpoints para gestionar suscripciones a Web Push Notifications.

POST   /push/subscribe    — registrar dispositivo
DELETE /push/unsubscribe  — eliminar suscripción
GET    /push/vapid-public — exponer la clave pública VAPID al frontend
"""

from __future__ import annotations

import uuid
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.infrastructure.database import get_session
from app.infrastructure.models.push_subscription import PushSubscription
from app.api.v1.dependencies.auth import CurrentUser, get_current_user

router = APIRouter(prefix="/push", tags=["Push Notifications"])
logger = logging.getLogger(__name__)


# ─── Schemas ──────────────────────────────────────────────────────────────────

class PushSubscribeRequest(BaseModel):
    endpoint: str
    keys: dict  # {p256dh: str, auth: str}
    expirationTime: Optional[int] = None


class PushUnsubscribeRequest(BaseModel):
    endpoint: str


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/vapid-public")
async def get_vapid_public_key():
    """
    Devuelve la clave pública VAPID para que el frontend la use al suscribirse.
    Este endpoint es público (no requiere auth).
    """
    if not settings.VAPID_PUBLIC_KEY:
        raise HTTPException(status_code=503, detail="Push notifications no configuradas")
    return {"public_key": settings.VAPID_PUBLIC_KEY}


@router.post("/subscribe", status_code=201)
async def subscribe(
    body: PushSubscribeRequest,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Registra o actualiza una suscripción push para el usuario autenticado.
    Upsert: si el endpoint ya existe se actualizan las claves.
    """
    user_id = uuid.UUID(str(current_user.id))
    p256dh  = body.keys.get("p256dh", "")
    auth    = body.keys.get("auth", "")

    if not body.endpoint or not p256dh or not auth:
        raise HTTPException(status_code=422, detail="Suscripción incompleta (endpoint, p256dh, auth son requeridos)")

    # Buscar suscripción existente para este endpoint
    result = await session.execute(
        select(PushSubscription).where(PushSubscription.endpoint == body.endpoint)
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.p256dh  = p256dh
        existing.auth    = auth
        existing.user_id = user_id
        await session.commit()
        logger.info(f"[Push] Suscripción actualizada para user {user_id}")
        return {"status": "updated"}

    sub = PushSubscription(
        user_id  = user_id,
        endpoint = body.endpoint,
        p256dh   = p256dh,
        auth     = auth,
    )
    session.add(sub)
    await session.commit()
    logger.info(f"[Push] Nueva suscripción registrada para user {user_id}")
    return {"status": "subscribed"}


@router.delete("/unsubscribe")
async def unsubscribe(
    body: PushUnsubscribeRequest,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Elimina la suscripción push para el endpoint indicado."""
    result = await session.execute(
        select(PushSubscription).where(PushSubscription.endpoint == body.endpoint)
    )
    sub = result.scalar_one_or_none()

    if not sub:
        return {"status": "not_found"}

    # Solo el dueño puede eliminar su suscripción
    if str(sub.user_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="No autorizado")

    await session.delete(sub)
    await session.commit()
    logger.info(f"[Push] Suscripción eliminada para user {current_user.id}")
    return {"status": "unsubscribed"}
