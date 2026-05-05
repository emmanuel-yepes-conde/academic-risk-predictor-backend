"""
Servicio de notificaciones por correo usando Azure Communication Services (ACS).
Coexiste con el servicio SMTP existente (app/services/email_service.py).

Se activa cuando ACS_CONNECTION_STRING está configurado en el .env.
Si no está configurado, los métodos retornan False sin lanzar excepciones.
"""

import logging
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

# ============================================================================
# COLORES DE MARCA (mismos que email_service.py)
# ============================================================================
NAVY   = "#1A2B4A"
CYAN   = "#00B4D8"
CANVAS = "#F8FAFC"
TEXT   = "#0F172A"
MUTED  = "#64748B"
GREEN  = "#00754A"


# ============================================================================
# TEMPLATES HTML
# ============================================================================

def _base_layout(header_color: str, header_text: str, body_html: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{header_text}</title>
</head>
<body style="margin:0;padding:0;background-color:{CANVAS};font-family:Arial,Helvetica,sans-serif;color:{TEXT};">
  <table width="100%" cellpadding="0" cellspacing="0" style="background-color:{CANVAS};padding:32px 16px;">
    <tr>
      <td align="center">
        <table width="600" cellpadding="0" cellspacing="0"
          style="max-width:600px;width:100%;background:#ffffff;border-radius:12px;
                 overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08);">

          <!-- Header -->
          <tr>
            <td style="background-color:{NAVY};padding:32px 40px;">
              <table width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  <td>
                    <span style="font-size:22px;font-weight:700;color:#ffffff;letter-spacing:0.5px;">
                      Academic <span style="color:{CYAN};">Risk</span>
                    </span>
                  </td>
                  <td align="right">
                    <span style="display:inline-block;background-color:{header_color};color:#ffffff;
                                 font-size:12px;font-weight:600;padding:4px 12px;border-radius:20px;
                                 letter-spacing:0.5px;">
                      {header_text}
                    </span>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Body -->
          <tr>
            <td style="padding:40px 40px 32px 40px;">
              {body_html}
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="background-color:{CANVAS};padding:24px 40px;border-top:1px solid #E2E8F0;">
              <p style="margin:0;font-size:12px;color:{MUTED};line-height:1.6;">
                Este correo fue enviado automáticamente por
                <strong>Academic Risk Predictor</strong>.<br/>
                Si no esperabas este mensaje, puedes ignorarlo.
              </p>
            </td>
          </tr>

          <!-- Bottom stripe -->
          <tr>
            <td style="background:linear-gradient(90deg,{NAVY} 0%,{CYAN} 100%);height:4px;"></td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def _referral_student_html(
    student_name: str,
    professor_name: str,
    course_name: str,
    tipo_remision: str,
    observaciones: str,
    fecha_remision: str,
) -> str:
    """Notificación al estudiante: fue remitido a consejería."""
    body = f"""
      <h1 style="margin:0 0 8px 0;font-size:24px;font-weight:700;color:{NAVY};">
        Has sido remitido a consejería
      </h1>
      <p style="margin:0 0 24px 0;font-size:14px;color:{MUTED};">
        Tu docente te ha referido al área de permanencia · {course_name}
      </p>

      <p style="margin:0 0 20px 0;font-size:16px;line-height:1.7;color:{TEXT};">
        Hola <strong>{student_name}</strong>,
      </p>

      <p style="margin:0 0 20px 0;font-size:16px;line-height:1.7;color:{TEXT};">
        El docente <strong>{professor_name}</strong> ha generado una remisión a consejería
        académica en tu nombre. El área de permanencia se pondrá en contacto contigo
        próximamente.
      </p>

      <!-- Tarjeta de detalle -->
      <table width="100%" cellpadding="0" cellspacing="0"
        style="background-color:#F0FDF4;border-left:4px solid {GREEN};
               border-radius:8px;margin-bottom:24px;">
        <tr>
          <td style="padding:20px 24px;">
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr>
                <td style="padding:6px 0;font-size:13px;color:{MUTED};">
                  <strong style="color:{NAVY};">Tipo de remisión</strong>
                </td>
                <td style="padding:6px 0;font-size:14px;color:{TEXT};text-align:right;">
                  {tipo_remision}
                </td>
              </tr>
              <tr>
                <td style="padding:6px 0;font-size:13px;color:{MUTED};">
                  <strong style="color:{NAVY};">Fecha</strong>
                </td>
                <td style="padding:6px 0;font-size:14px;color:{TEXT};text-align:right;">
                  {fecha_remision}
                </td>
              </tr>
              <tr>
                <td colspan="2" style="padding-top:12px;border-top:1px solid #D1FAE5;">
                  <p style="margin:0 0 4px 0;font-size:12px;font-weight:700;
                             text-transform:uppercase;letter-spacing:0.5px;color:{MUTED};">
                    Observaciones del docente
                  </p>
                  <p style="margin:0;font-size:14px;color:{TEXT};line-height:1.6;">
                    {observaciones}
                  </p>
                </td>
              </tr>
            </table>
          </td>
        </tr>
      </table>

      <p style="margin:0;font-size:14px;color:{MUTED};line-height:1.6;">
        Si tienes alguna duda, comunícate directamente con el área de permanencia
        o con tu docente.
      </p>
    """
    return _base_layout(header_color=GREEN, header_text="Nueva Remisión", body_html=body)


def _referral_consejeria_html(
    student_name: str,
    student_email: str,
    professor_name: str,
    course_name: str,
    tipo_remision: str,
    observaciones: str,
    fecha_remision: str,
) -> str:
    """Notificación al área de consejería: nuevo caso pendiente."""
    body = f"""
      <h1 style="margin:0 0 8px 0;font-size:24px;font-weight:700;color:{NAVY};">
        Nueva remisión pendiente
      </h1>
      <p style="margin:0 0 24px 0;font-size:14px;color:{MUTED};">
        Caso asignado por docente · {course_name}
      </p>

      <p style="margin:0 0 20px 0;font-size:16px;line-height:1.7;color:{TEXT};">
        El docente <strong>{professor_name}</strong> ha creado una remisión a permanencia.
        A continuación los detalles del caso:
      </p>

      <!-- Tarjeta del estudiante -->
      <table width="100%" cellpadding="0" cellspacing="0"
        style="background-color:#EFF6FF;border-left:4px solid #3B82F6;
               border-radius:8px;margin-bottom:24px;">
        <tr>
          <td style="padding:20px 24px;">
            <p style="margin:0 0 12px 0;font-size:13px;font-weight:700;
                       text-transform:uppercase;letter-spacing:0.5px;color:#1D4ED8;">
              Datos del estudiante
            </p>
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr>
                <td style="padding:5px 0;font-size:13px;color:{MUTED};width:140px;">
                  <strong style="color:{NAVY};">Nombre</strong>
                </td>
                <td style="padding:5px 0;font-size:14px;color:{TEXT};">
                  {student_name}
                </td>
              </tr>
              <tr>
                <td style="padding:5px 0;font-size:13px;color:{MUTED};">
                  <strong style="color:{NAVY};">Correo</strong>
                </td>
                <td style="padding:5px 0;font-size:14px;">
                  <a href="mailto:{student_email}"
                     style="color:{CYAN};text-decoration:none;">{student_email}</a>
                </td>
              </tr>
              <tr>
                <td style="padding:5px 0;font-size:13px;color:{MUTED};">
                  <strong style="color:{NAVY};">Tipo remisión</strong>
                </td>
                <td style="padding:5px 0;font-size:14px;color:{TEXT};">
                  {tipo_remision}
                </td>
              </tr>
              <tr>
                <td style="padding:5px 0;font-size:13px;color:{MUTED};">
                  <strong style="color:{NAVY};">Fecha remisión</strong>
                </td>
                <td style="padding:5px 0;font-size:14px;color:{TEXT};">
                  {fecha_remision}
                </td>
              </tr>
            </table>
          </td>
        </tr>
      </table>

      <!-- Observaciones -->
      <table width="100%" cellpadding="0" cellspacing="0"
        style="background-color:{CANVAS};border:1px solid #E2E8F0;
               border-radius:8px;margin-bottom:24px;">
        <tr>
          <td style="padding:16px 20px;">
            <p style="margin:0 0 6px 0;font-size:12px;font-weight:700;
                       text-transform:uppercase;letter-spacing:0.5px;color:{MUTED};">
              Observaciones del docente
            </p>
            <p style="margin:0;font-size:14px;color:{TEXT};line-height:1.6;">
              {observaciones}
            </p>
          </td>
        </tr>
      </table>

      <!-- Estado badge -->
      <table cellpadding="0" cellspacing="0" style="margin-bottom:24px;">
        <tr>
          <td style="background-color:rgba(234,88,12,0.10);border:1px solid rgba(234,88,12,0.25);
                     border-radius:20px;padding:6px 16px;">
            <span style="font-size:13px;font-weight:700;color:#C2410C;">
              ● PENDIENTE
            </span>
          </td>
        </tr>
      </table>

      <p style="margin:0;font-size:14px;color:{MUTED};line-height:1.6;">
        Por favor actualiza el estado de la remisión una vez hayas atendido al estudiante.
      </p>
    """
    return _base_layout(header_color="#C2410C", header_text="Nuevo Caso", body_html=body)


# ============================================================================
# ENVÍO ACS
# ============================================================================

def _is_configured() -> bool:
    """Verifica que ACS esté configurado antes de intentar enviar."""
    return bool(getattr(settings, "ACS_CONNECTION_STRING", None))


async def _send_acs(
    to_email: str,
    subject: str,
    html_content: str,
    plain_text: Optional[str] = None,
) -> bool:
    """
    Envía un correo usando el SDK de Azure Communication Services.
    La llamada al SDK es síncrona; se ejecuta en un thread para no bloquear.
    """
    import asyncio
    from azure.communication.email import EmailClient
    from azure.core.exceptions import HttpResponseError

    def _sync_send() -> None:
        client = EmailClient.from_connection_string(settings.ACS_CONNECTION_STRING)
        message = {
            "senderAddress": settings.ACS_SENDER_EMAIL,
            "recipients": {
                "to": [{"address": to_email}],
            },
            "content": {
                "subject": subject,
                "html": html_content,
                "plainText": plain_text or subject,
            },
        }
        poller = client.begin_send(message)
        result = poller.result()
        if result.get("status", "").upper() not in ("SUCCEEDED", ""):
            raise RuntimeError(f"ACS send status: {result.get('status')}")

    try:
        await asyncio.to_thread(_sync_send)
        logger.info("ACS email enviado a %s · asunto: %s", to_email, subject)
        return True
    except Exception as exc:
        logger.error("ACS email falló para %s: %s", to_email, exc, exc_info=True)
        return False


# ============================================================================
# API PÚBLICA
# ============================================================================

async def notify_referral_created(
    *,
    student_name: str,
    student_email: str,
    professor_name: str,
    course_name: str,
    tipo_remision: str,
    observaciones: str,
    fecha_remision: str,
) -> dict[str, bool]:
    """
    Envía dos correos cuando se crea una remisión:
      - Al estudiante: se le informa que fue remitido.
      - A consejería: recibe los detalles del caso.

    Retorna un dict con el resultado de cada envío:
      {"student": True/False, "consejeria": True/False}
    """
    if not _is_configured():
        logger.warning(
            "ACS_CONNECTION_STRING no configurado — notificaciones ACS desactivadas"
        )
        return {"student": False, "consejeria": False}

    consejeria_email: str = settings.ACS_CONSEJERIA_EMAIL

    student_html = _referral_student_html(
        student_name=student_name,
        professor_name=professor_name,
        course_name=course_name,
        tipo_remision=tipo_remision,
        observaciones=observaciones,
        fecha_remision=fecha_remision,
    )
    consejeria_html = _referral_consejeria_html(
        student_name=student_name,
        student_email=student_email,
        professor_name=professor_name,
        course_name=course_name,
        tipo_remision=tipo_remision,
        observaciones=observaciones,
        fecha_remision=fecha_remision,
    )

    import asyncio
    student_ok, consejeria_ok = await asyncio.gather(
        _send_acs(
            to_email=student_email,
            subject=f"Remisión a consejería académica — {course_name}",
            html_content=student_html,
        ),
        _send_acs(
            to_email=consejeria_email,
            subject=f"Nueva remisión: {student_name} — {course_name}",
            html_content=consejeria_html,
        ),
    )

    return {"student": student_ok, "consejeria": consejeria_ok}
