"""
notification_service — crea notificaciones in-app y las envía por
WhatsApp y/o email según las preferencias del usuario.

Uso desde cualquier endpoint/cron:
    from app.services.notification_service import notify

    await notify(
        db=db,
        user=student,
        type="RISK_ALTO",
        title="Riesgo alto detectado",
        body="Tu riesgo en Cálculo Diferencial es del 82%.",
        data={"course_id": str(course.id)},
    )
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.infrastructure.models.notification import Notification
from app.infrastructure.models.user import User

logger = logging.getLogger(__name__)

# Prefijos de texto por tipo para el mensaje WhatsApp (sin emojis)
_WA_ICON = {
    "RISK_ALTO":      "🔴",
    "RISK_MEDIO":     "🟡",
    "RISK_BAJO":      "🟢",
    "RISK_RECOVERED": "🟢",
    "ATTENDANCE":     "✅",
    "GRADE_UPDATE":   "📝",
    "CLASS_CRISIS":   "⚠️",
    "SYSTEM":         "ℹ️",
}


async def notify(
    db: AsyncSession,
    user: User,
    type: str,
    title: str,
    body: str,
    data: Optional[dict] = None,
    send_whatsapp: bool = True,
    send_email: bool = False,
) -> Notification:
    """
    Crea una notificación in-app y, según las prefs del usuario,
    la envía por WhatsApp y/o email.

    Siempre guarda en DB aunque fallen los canales externos.
    """
    # 1. Guardar en DB
    notif = Notification(
        user_id=user.id,
        type=type,
        title=title,
        body=body,
        data=data,
    )
    db.add(notif)
    await db.commit()
    await db.refresh(notif)

    # 2. WhatsApp (si el usuario lo habilitó y tiene número)
    if send_whatsapp and getattr(user, "whatsapp_enabled", True) and getattr(user, "phone", None):
        try:
            await _send_whatsapp(user.phone, type, title, body)
        except Exception as exc:
            logger.warning("[notify] WhatsApp falló para %s: %s", user.id, exc)

    # 3. Email (si el usuario lo habilitó y hay servicio configurado)
    if send_email and getattr(user, "email_enabled", True) and user.email:
        try:
            await _send_email(user.email, user.full_name, title, body)
        except Exception as exc:
            logger.warning("[notify] Email falló para %s: %s", user.id, exc)

    return notif


async def notify_by_user_id(
    db: AsyncSession,
    user_id: UUID,
    type: str,
    title: str,
    body: str,
    data: Optional[dict] = None,
) -> None:
    """Versión ligera que solo guarda en DB (sin buscar preferencias del usuario)."""
    notif = Notification(
        user_id=user_id,
        type=type,
        title=title,
        body=body,
        data=data,
    )
    db.add(notif)
    await db.commit()


# ─── Helpers privados ─────────────────────────────────────────────────────────

async def _send_whatsapp(phone: str, type: str, title: str, body: str) -> None:
    if not settings.WAHA_URL:
        logger.warning("[notify] WAHA_URL no configurado — WhatsApp no enviado (type=%s)", type)
        return
    numero = phone.strip().replace(" ", "").replace("-", "").replace("+", "")
    if not numero.startswith("57") and len(numero) == 10:
        numero = f"57{numero}"
    prefix = _WA_ICON.get(type, "ℹ️")
    texto = f"{prefix} *{title}*\n\n{body}"
    chat_id = f"{numero}@c.us"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{settings.WAHA_URL.rstrip('/')}/api/sendText",
                json={"chatId": chat_id, "text": texto, "session": "default"},
                headers={"X-Api-Key": settings.WAHA_API_KEY},
            )
        if resp.status_code >= 400:
            logger.warning(
                "[notify] WhatsApp sendText falló → %s %s (chat=%s, type=%s)",
                resp.status_code, resp.text[:120], chat_id, type
            )
        else:
            logger.info("[notify] WhatsApp enviado → %s (type=%s)", chat_id, type)
    except Exception as exc:
        logger.warning("[notify] WhatsApp excepción → %s (chat=%s, type=%s)", exc, chat_id, type)


async def _send_email(
    email: str,
    name: str,
    title: str,
    body: str,
    html_content: str | None = None,
) -> bool:
    """
    Envía email con routing por dominio:
    - @uniminuto.edu.co / @uniminuto.edu → Azure ACS (con fallback SMTP)
    - Cualquier otro dominio             → SMTP directamente

    Acepta html_content pre-construido; si no se pasa, genera un HTML mínimo.
    Retorna True si se envió, False si falló (nunca lanza excepción).
    """
    try:
        from app.services.acs_email_service import _dispatch

        if not html_content:
            html_content = f"""<!DOCTYPE html><html><body
              style="margin:0;padding:24px;background:#f8fafc;
                     font-family:Arial,Helvetica,sans-serif;">
              <div style="max-width:560px;margin:0 auto;background:#fff;
                          border-radius:12px;padding:32px;
                          box-shadow:0 2px 12px rgba(0,0,0,0.08);">
                <div style="background:#1E3932;border-radius:8px;
                            padding:14px 20px;margin-bottom:24px;">
                  <span style="color:#fff;font-size:16px;font-weight:700;">
                    Academic <span style="color:#d4e9e2;">Risk</span>
                  </span>
                </div>
                <h2 style="color:#1E3932;font-size:17px;margin:0 0 12px 0;">
                  {title}
                </h2>
                <p style="color:#4a5568;font-size:14px;line-height:1.7;
                          white-space:pre-wrap;margin:0 0 20px 0;">
                  {body}
                </p>
                <hr style="border:none;border-top:1px solid #e2e8f0;margin:0"/>
                <p style="color:#9ca3af;font-size:11px;margin:16px 0 0 0;">
                  Mensaje automático — Academic Risk Predictor
                </p>
              </div>
            </body></html>"""

        ok = await _dispatch(to_email=email, subject=title, html_content=html_content)
        if ok:
            logger.info("[notify] Email enviado → %s (%s)", email, title)
        else:
            logger.warning("[notify] _dispatch retornó False para %s — revisa logs de ACS/SMTP", email)
        return ok
    except ImportError as exc:
        logger.error("[notify] acs_email_service no disponible: %s", exc)
        return False
    except Exception as exc:
        # Era logger.debug → INVISIBLE en producción. Cambiado a warning.
        logger.warning("[notify] Email falló para %s: %s", email, exc)
        return False
