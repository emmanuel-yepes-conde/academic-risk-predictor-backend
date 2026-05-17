"""
InAppNotificationsRouter — notificaciones in-app del usuario autenticado.

GET    /inapp/notifications              → no leídas (máx 50)
GET    /inapp/notifications/all          → todas, paginado
GET    /inapp/notifications/unread-count → conteo badge
PATCH  /inapp/notifications/{id}/read   → marcar una leída
PATCH  /inapp/notifications/read-all    → marcar todas leídas
DELETE /inapp/notifications/{id}        → eliminar
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, update, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies.auth import get_current_user, CurrentUser
from app.infrastructure.database import get_session
from app.infrastructure.models.notification import Notification

router = APIRouter(prefix="/inapp/notifications", tags=["In-App Notifications"])


class NotificationRead(BaseModel):
    id: UUID
    type: str
    title: str
    body: str
    data: Optional[dict]
    read: bool
    created_at: datetime

    class Config:
        from_attributes = True


@router.get("", response_model=list[NotificationRead])
async def get_unread(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> list[NotificationRead]:
    result = await db.execute(
        select(Notification)
        .where(Notification.user_id == current_user.id, Notification.read == False)  # noqa: E712
        .order_by(Notification.created_at.desc())
        .limit(50)
    )
    return result.scalars().all()


@router.get("/all", response_model=list[NotificationRead])
async def get_all(
    limit: int = Query(default=30, le=100),
    offset: int = Query(default=0),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> list[NotificationRead]:
    result = await db.execute(
        select(Notification)
        .where(Notification.user_id == current_user.id)
        .order_by(Notification.created_at.desc())
        .offset(offset).limit(limit)
    )
    return result.scalars().all()


@router.get("/unread-count")
async def get_unread_count(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> dict:
    result = await db.execute(
        select(func.count()).where(
            Notification.user_id == current_user.id,
            Notification.read == False,  # noqa: E712
        )
    )
    return {"count": result.scalar_one()}


@router.patch("/{notification_id}/read")
async def mark_read(
    notification_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> dict:
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == current_user.id,
        )
    )
    notif = result.scalar_one_or_none()
    if not notif:
        raise HTTPException(status_code=404, detail="Notificación no encontrada")
    notif.read = True
    await db.commit()
    return {"ok": True}


@router.patch("/read-all")
async def mark_all_read(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> dict:
    await db.execute(
        update(Notification)
        .where(Notification.user_id == current_user.id, Notification.read == False)  # noqa: E712
        .values(read=True)
    )
    await db.commit()
    return {"ok": True}


@router.delete("/{notification_id}")
async def delete_notification(
    notification_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> dict:
    await db.execute(
        delete(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == current_user.id,
        )
    )
    await db.commit()
    return {"ok": True}
