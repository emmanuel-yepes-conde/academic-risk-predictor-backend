"""
Servicio de Web Push Notifications (VAPID).

Flujo:
  1. Frontend suscribe al usuario → endpoint + p256dh + auth
  2. Backend guarda la suscripción en push_subscriptions
  3. Al detectar riesgo ALTO, llamar a send_push_to_user()
  4. pywebpush cifra y envía al push service del navegador
  5. El service worker muestra la notificación en el celular

Costo: $0 — las push notifications web no tienen costo de mensajería.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.infrastructure.models.push_subscription import PushSubscription

logger = logging.getLogger(__name__)


async def send_push_to_user(
    user_id: str,
    title: str,
    body: str,
    url: str = "/",
    session: Optional[AsyncSession] = None,
) -> int:
    """
    Envía una push notification a todos los dispositivos registrados de un usuario.

    Args:
        user_id:  UUID del usuario destinatario
        title:    Título de la notificación (aparece en negrita)
        body:     Cuerpo del mensaje
        url:      URL que se abre al hacer clic (relativa al frontend)
        session:  Sesión de BD para buscar suscripciones

    Returns:
        Número de notificaciones enviadas exitosamente
    """
    if not settings.VAPID_PRIVATE_KEY_B64 or not settings.VAPID_PUBLIC_KEY:
        logger.warning("[Push] VAPID no configurado — notificación omitida")
        return 0

    if session is None:
        logger.warning("[Push] Sin sesión de BD — notificación omitida")
        return 0

    try:
        from pywebpush import webpush, WebPushException
        import base64
        from cryptography.hazmat.primitives.serialization import (
            Encoding, PrivateFormat, NoEncryption,
        )
        from cryptography.hazmat.primitives.asymmetric.ec import (
            EllipticCurvePrivateKey,
        )
        from cryptography.hazmat.backends import default_backend
        from cryptography.hazmat.primitives.serialization import load_der_private_key
    except ImportError:
        logger.error("[Push] pywebpush no está instalado — pip install pywebpush")
        return 0

    # Recuperar suscripciones del usuario
    import uuid as _uuid
    try:
        uid = _uuid.UUID(str(user_id))
    except ValueError:
        logger.warning(f"[Push] user_id inválido: {user_id}")
        return 0

    result = await session.execute(
        select(PushSubscription).where(PushSubscription.user_id == uid)
    )
    subscriptions = result.scalars().all()

    if not subscriptions:
        return 0

    # Decodificar clave privada VAPID desde base64
    try:
        key_b64 = settings.VAPID_PRIVATE_KEY_B64
        # Añadir padding correcto (sin este cálculo base64 falla si ya tiene '=')
        key_b64 += "=" * (-len(key_b64) % 4)
        der_bytes = base64.urlsafe_b64decode(key_b64)
        private_key = load_der_private_key(der_bytes, password=None, backend=default_backend())
        vapid_private_pem = private_key.private_bytes(
            encoding=Encoding.PEM,
            format=PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=NoEncryption(),
        ).decode()
    except Exception as exc:
        logger.error(f"[Push] Error decodificando clave VAPID: {exc}")
        return 0

    payload = json.dumps({"title": title, "body": body, "url": url})
    sent = 0
    expired_endpoints: list[str] = []

    for sub in subscriptions:
        try:
            webpush(
                subscription_info={
                    "endpoint": sub.endpoint,
                    "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                },
                data=payload,
                vapid_private_key=vapid_private_pem,
                vapid_claims={
                    "sub": f"mailto:{settings.VAPID_CONTACT_EMAIL}",
                },
            )
            sent += 1
            logger.info(f"[Push] ✅ Enviado a usuario {user_id} → {sub.endpoint[:60]}…")

        except Exception as exc:
            # 410 Gone = suscripción expirada, hay que eliminarla
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            if status_code == 410:
                expired_endpoints.append(sub.endpoint)
                logger.info(f"[Push] Suscripción expirada, eliminando: {sub.endpoint[:60]}…")
            else:
                logger.error(f"[Push] Error enviando notificación: {exc}")

    # Limpiar suscripciones expiradas
    for endpoint in expired_endpoints:
        result2 = await session.execute(
            select(PushSubscription).where(PushSubscription.endpoint == endpoint)
        )
        expired_sub = result2.scalar_one_or_none()
        if expired_sub:
            await session.delete(expired_sub)
    if expired_endpoints:
        await session.commit()

    return sent


def build_risk_alert_message(
    student_name: str,
    course_name: str,
    risk_level: str,
    risk_pct: float,
    course_id: str,
    analisis_primera_linea: str = "",
) -> dict[str, str]:
    """
    Construye el payload de notificación push para una alerta de riesgo ALTO.
    El body incluye la primera línea del análisis natural si está disponible.
    """
    nivel_label = {"ALTO": "[RIESGO ALTO]", "MEDIO": "[RIESGO MEDIO]", "BAJO": "[RIESGO BAJO]"}.get(risk_level, f"[{risk_level}]")
    if analisis_primera_linea:
        body = analisis_primera_linea
    else:
        body = (
            f"Tu nivel de riesgo es {risk_level} ({risk_pct:.0f}%). "
            "Ingresa a la plataforma para ver el analisis completo."
        )
    return {
        "title": f"{nivel_label} {course_name}",
        "body": body,
        "url": f"/materia/{course_id}",
    }
