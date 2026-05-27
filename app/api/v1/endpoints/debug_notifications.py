"""
Endpoint de diagnóstico de canales de notificación.

Solo disponible para ADMIN. Permite probar WAHA, SMTP y ACS directamente
desde la app desplegada sin hacer deploy de scripts adicionales.

Rutas:
  POST /api/v1/debug/notify/waha    → envía WA de prueba
  POST /api/v1/debug/notify/email   → envía correo de prueba (respeta EMAIL_FORCE_SMTP)
  GET  /api/v1/debug/notify/status  → estado de configuración de canales
"""

import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.v1.dependencies.auth import CurrentUser, get_current_user
from app.core.config import settings
from app.domain.enums import RoleEnum

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/debug/notify", tags=["Debug — Notificaciones"])


def _require_admin(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if current_user.role != RoleEnum.ADMIN:
        raise HTTPException(status_code=403, detail="Solo administradores")
    return current_user


# ─── Schemas ─────────────────────────────────────────────────────────────────

class WahaTestBody(BaseModel):
    phone: str = "3126226684"


class EmailTestBody(BaseModel):
    email: str = "deividlujan200@gmail.com"


# ─── GET /status ──────────────────────────────────────────────────────────────

@router.get("/status")
async def notification_status(_: CurrentUser = Depends(_require_admin)) -> dict:
    """Devuelve el estado de configuración de cada canal."""
    waha_ok = bool(settings.WAHA_URL and settings.WAHA_API_KEY)
    smtp_ok = bool(settings.SMTP_SERVER and settings.SMTP_USERNAME and settings.SMTP_PASSWORD)
    acs_ok  = bool(settings.ACS_CONNECTION_STRING)

    # Verificar sesión WAHA
    waha_session_status = "not_checked"
    if waha_ok:
        try:
            async with httpx.AsyncClient(timeout=8) as c:
                r = await c.get(
                    f"{settings.WAHA_URL.rstrip('/')}/api/sessions/default",
                    headers={"X-Api-Key": settings.WAHA_API_KEY},
                )
            data = r.json()
            waha_session_status = data.get("status", "UNKNOWN")
        except Exception as exc:
            waha_session_status = f"error: {exc}"

    return {
        "channels": {
            "waha": {
                "configured": waha_ok,
                "url": settings.WAHA_URL or None,
                "session_status": waha_session_status,
            },
            "smtp": {
                "configured": smtp_ok,
                "server": f"{settings.SMTP_SERVER}:{settings.SMTP_PORT}" if smtp_ok else None,
                "username": settings.SMTP_USERNAME or None,
            },
            "acs": {
                "configured": acs_ok,
                "sender": settings.ACS_SENDER_EMAIL or None,
                "force_smtp_override": getattr(settings, "EMAIL_FORCE_SMTP", False),
            },
        },
        "email_routing": "SMTP (forzado)" if getattr(settings, "EMAIL_FORCE_SMTP", False) else "ACS para @uniminuto / SMTP para resto",
    }


# ─── POST /waha ───────────────────────────────────────────────────────────────

@router.post("/waha")
async def test_waha(
    body: WahaTestBody,
    _: CurrentUser = Depends(_require_admin),
) -> dict:
    """Envía un mensaje de WhatsApp de prueba al número indicado."""
    if not settings.WAHA_URL:
        raise HTTPException(status_code=503, detail="WAHA_URL no configurado")

    numero = body.phone.strip().replace(" ", "").replace("-", "").replace("+", "")
    if not numero.startswith("57") and len(numero) == 10:
        numero = f"57{numero}"
    chat_id = f"{numero}@c.us"

    text = (
        "🧪 *Prueba de diagnóstico — Academic Risk*\n\n"
        "Este mensaje confirma que el canal WhatsApp está funcionando correctamente. ✅"
    )

    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(
                f"{settings.WAHA_URL.rstrip('/')}/api/sendText",
                json={"chatId": chat_id, "text": text, "session": "default"},
                headers={"X-Api-Key": settings.WAHA_API_KEY},
            )
        if r.status_code < 400:
            logger.info("[debug-notify] WAHA prueba enviada → %s", chat_id)
            return {"ok": True, "chat_id": chat_id, "status_code": r.status_code}
        else:
            logger.warning("[debug-notify] WAHA falló → %s %s", r.status_code, r.text[:200])
            return {"ok": False, "chat_id": chat_id, "status_code": r.status_code, "detail": r.text[:200]}
    except Exception as exc:
        logger.error("[debug-notify] WAHA excepción: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc))


# ─── POST /email ──────────────────────────────────────────────────────────────

@router.post("/email")
async def test_email(
    body: EmailTestBody,
    _: CurrentUser = Depends(_require_admin),
) -> dict:
    """
    Envía un correo de prueba. Respeta EMAIL_FORCE_SMTP:
    - EMAIL_FORCE_SMTP=true  → SMTP directamente (para pruebas, no gasta tokens ACS)
    - EMAIL_FORCE_SMTP=false → routing normal (ACS para @uniminuto, SMTP para resto)
    """
    from app.services.notification_service import _send_email

    channel = "SMTP (forzado)" if getattr(settings, "EMAIL_FORCE_SMTP", False) else "routing normal"
    logger.info("[debug-notify] Enviando email de prueba a %s via %s", body.email, channel)

    ok = await _send_email(
        email=body.email,
        name="Admin",
        title=f"🧪 Prueba Academic Risk — {channel}",
        body=(
            f"Este correo confirma que el canal de email está funcionando.\n\n"
            f"Canal: {channel}\n"
            f"Servidor SMTP: {settings.SMTP_SERVER}:{settings.SMTP_PORT}"
        ),
    )

    if ok:
        return {"ok": True, "email": body.email, "channel": channel}
    else:
        raise HTTPException(
            status_code=502,
            detail=f"El correo no se pudo enviar a {body.email}. Revisa los logs del servidor.",
        )


# ─── POST /chatbot/force-timeout ─────────────────────────────────────────────

@router.post("/chatbot/force-timeout")
async def force_chatbot_timeout(
    _: CurrentUser = Depends(_require_admin),
) -> dict:
    """
    Fuerza el chequeo de timeouts del chatbot ignorando el tiempo transcurrido.
    Útil para probar los mensajes de seguimiento/despedida sin esperar 3 minutos.
    """
    from app.application.services.waha_chatbot_service import (
        check_chatbot_timeouts,
        _sessions,
    )

    sessions_before = dict(_sessions)
    await check_chatbot_timeouts(force=True)
    sessions_after = dict(_sessions)

    processed = [
        phone for phone in sessions_before
        if phone not in sessions_after
        or sessions_before[phone].get("step") != sessions_after.get(phone, {}).get("step")
    ]

    return {
        "ok": True,
        "sessions_found": len(sessions_before),
        "sessions_processed": len(processed),
        "phones": processed,
    }
