"""
Webhook de WAHA (WhatsApp HTTP API).
Recibe mensajes entrantes de WhatsApp y responde con el análisis de riesgo académico.
"""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.services.waha_chatbot_service import WahaChatbotService
from app.core.config import settings
from app.infrastructure.database import get_session

logger = logging.getLogger(__name__)

router = APIRouter()


async def _send_message(phone: str, text: str, session_name: str) -> None:
    """Envía un mensaje de texto a través de la API de WAHA."""
    if not settings.WAHA_URL:
        logger.error("WAHA_URL no está configurado en las variables de entorno")
        return

    # Usar el JID tal como viene; si no tiene dominio, asumir @c.us
    chat_id = phone if "@" in phone else f"{phone}@c.us"
    url = f"{settings.WAHA_URL.rstrip('/')}/api/sendText"
    payload = {"session": session_name, "chatId": chat_id, "text": text}
    headers = {"X-Api-Key": settings.WAHA_API_KEY}

    print(f"[WAHA] Enviando a {chat_id} via {url}", flush=True)
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            if response.status_code >= 400:
                print(f"[WAHA] sendText ERROR {response.status_code}: {response.text[:300]}", flush=True)
            else:
                print(f"[WAHA] sendText OK (status={response.status_code})", flush=True)
    except Exception as e:
        print(f"[WAHA] EXCEPCION en sendText: {e}", flush=True)


@router.post("/waha/webhook")
async def waha_webhook(
    request: Request,
    db: AsyncSession = Depends(get_session),
):
    """
    Endpoint receptor del webhook de WAHA.
    Procesa mensajes entrantes y responde con el análisis de riesgo.
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="JSON inválido")

    # DEBUG — imprimir payload completo para diagnóstico
    import json as _json
    print(f"[WAHA-RAW] event={body.get('event')} | payload_keys={list(body.get('payload', {}).keys())}", flush=True)
    print(f"[WAHA-RAW] body={_json.dumps(body)[:600]}", flush=True)

    event = body.get("event")
    if event != "message":
        return JSONResponse({"status": "ignored", "reason": f"event={event}"})

    payload = body.get("payload", {})

    # Ignorar mensajes propios
    if payload.get("fromMe", False):
        return JSONResponse({"status": "ignored", "reason": "fromMe"})

    # Ignorar mensajes con media (imágenes, audios, etc.)
    if payload.get("hasMedia", False):
        return JSONResponse({"status": "ignored", "reason": "hasMedia"})

    from_jid: str = payload.get("from", "")
    if not from_jid:
        return JSONResponse({"status": "ignored", "reason": "no from"})

    text: str = (payload.get("body") or "").strip()
    if not text:
        return JSONResponse({"status": "ignored", "reason": "empty body"})

    # Usar el JID completo como clave de sesión y como destino de respuesta
    # Soporta tanto @c.us como @lid (formato nuevo de WhatsApp)
    phone = from_jid  # conservar el JID completo para enviar la respuesta
    session_name: str = body.get("session", "default")

    print(f"[WAHA] Mensaje de {phone} (session={session_name}): {text[:80]}", flush=True)
    print(f"[WAHA] WAHA_URL cargado: {repr(settings.WAHA_URL[:40] if settings.WAHA_URL else 'VACÍO')}", flush=True)

    try:
        chatbot = WahaChatbotService(db)
        response_text = await chatbot.handle_message(phone, text)
        print(f"[WAHA] Respuesta generada ({len(response_text)} chars): {response_text[:60]}", flush=True)
        await _send_message(phone, response_text, session_name)
    except Exception as e:
        print(f"[WAHA] ERROR procesando mensaje de {phone}: {e}", flush=True)
        logger.exception("Error procesando mensaje de %s", phone)
        try:
            await _send_message(
                phone,
                "Lo siento, ocurrió un error interno. Por favor intenta más tarde.",
                session_name,
            )
        except Exception as e2:
            print(f"[WAHA] ERROR enviando error a {phone}: {e2}", flush=True)

    return JSONResponse({"status": "ok"})
