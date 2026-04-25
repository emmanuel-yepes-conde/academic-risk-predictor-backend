"""
Servicio de envío de correos electrónicos
Usa smtplib + email.mime de la librería estándar de Python.
Las llamadas síncronas se envuelven con asyncio.to_thread para no bloquear el event loop.
"""

import asyncio
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import settings

logger = logging.getLogger(__name__)

# ============================================================================
# COLORES DE MARCA
# ============================================================================
NAVY   = "#1A2B4A"
CYAN   = "#00B4D8"
CANVAS = "#F8FAFC"
TEXT   = "#0F172A"
MUTED  = "#64748B"


# ============================================================================
# TEMPLATES HTML
# ============================================================================

def _base_layout(header_color: str, header_text: str, body_html: str) -> str:
    """Envuelve el contenido en el layout base con header y footer de marca."""
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
        <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08);">

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
                    <span style="display:inline-block;background-color:{header_color};color:#ffffff;font-size:12px;font-weight:600;padding:4px 12px;border-radius:20px;letter-spacing:0.5px;">
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
                Este correo fue enviado automáticamente por <strong>Academic Risk Predictor</strong>.<br/>
                Si no esperabas este mensaje, puedes ignorarlo.<br/>
                <span style="color:{CYAN};">academicrisk.notifications@gmail.com</span>
              </p>
            </td>
          </tr>

          <!-- Bottom border strip -->
          <tr>
            <td style="background:linear-gradient(90deg,{NAVY} 0%,{CYAN} 100%);height:4px;"></td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def _risk_alert_html(
    professor_name: str,
    student_name: str,
    student_email: str,
    risk_level: str,
    course_name: str,
) -> str:
    """Genera el HTML para la alerta de riesgo dirigida al profesor."""
    body = f"""
      <h1 style="margin:0 0 8px 0;font-size:24px;font-weight:700;color:{NAVY};">
        Alerta de riesgo académico
      </h1>
      <p style="margin:0 0 24px 0;font-size:14px;color:{MUTED};">
        Notificación automática · {course_name}
      </p>

      <p style="margin:0 0 20px 0;font-size:16px;line-height:1.7;color:{TEXT};">
        Estimado/a <strong>{professor_name}</strong>,
      </p>

      <p style="margin:0 0 20px 0;font-size:16px;line-height:1.7;color:{TEXT};">
        El estudiante <strong>{student_name}</strong>
        (<a href="mailto:{student_email}" style="color:{CYAN};text-decoration:none;">{student_email}</a>)
        acaba de completar un análisis de riesgo académico con resultado
        <strong style="color:#DC2626;">ALTO</strong>.
      </p>

      <!-- Tarjeta de alerta -->
      <table width="100%" cellpadding="0" cellspacing="0" style="background-color:#FEF2F2;border-left:4px solid #DC2626;border-radius:8px;margin-bottom:24px;">
        <tr>
          <td style="padding:16px 20px;">
            <p style="margin:0 0 6px 0;font-size:13px;font-weight:700;color:#DC2626;text-transform:uppercase;letter-spacing:0.5px;">
              ⚠ Nivel de riesgo detectado
            </p>
            <p style="margin:0;font-size:20px;font-weight:700;color:{TEXT};">
              {risk_level.upper()}
            </p>
          </td>
        </tr>
      </table>

      <p style="margin:0 0 28px 0;font-size:16px;line-height:1.7;color:{TEXT};">
        Te recomendamos contactar a este estudiante para brindarle apoyo adicional
        y orientarlo en las áreas de mejora identificadas por el sistema.
      </p>

      <!-- CTA Button -->
      <table cellpadding="0" cellspacing="0" style="margin-bottom:28px;">
        <tr>
          <td style="background-color:{CYAN};border-radius:8px;">
            <a href="#" style="display:inline-block;padding:14px 32px;font-size:15px;font-weight:600;color:#ffffff;text-decoration:none;letter-spacing:0.3px;">
              Ver detalles en la plataforma
            </a>
          </td>
        </tr>
      </table>

      <p style="margin:0;font-size:14px;color:{MUTED};line-height:1.6;">
        Gracias por tu compromiso con el bienestar académico de tus estudiantes.
      </p>
    """
    return _base_layout(header_color="#DC2626", header_text="Alerta de Riesgo", body_html=body)


def _predictor_reminder_html(student_name: str) -> str:
    """Genera el HTML para el recordatorio al estudiante."""
    body = f"""
      <h1 style="margin:0 0 8px 0;font-size:24px;font-weight:700;color:{NAVY};">
        ¿Has revisado tu riesgo académico esta semana?
      </h1>
      <p style="margin:0 0 28px 0;font-size:14px;color:{MUTED};">
        Tu bienestar académico nos importa
      </p>

      <p style="margin:0 0 20px 0;font-size:16px;line-height:1.7;color:{TEXT};">
        Hola <strong>{student_name}</strong>,
      </p>

      <p style="margin:0 0 20px 0;font-size:16px;line-height:1.7;color:{TEXT};">
        Te invitamos a usar el <strong>predictor de riesgo académico</strong> para conocer
        tu situación actual y recibir consejos personalizados que te ayuden a alcanzar
        tus metas este semestre.
      </p>

      <!-- Lista de beneficios -->
      <table width="100%" cellpadding="0" cellspacing="0" style="background-color:{CANVAS};border-radius:10px;margin-bottom:28px;">
        <tr>
          <td style="padding:20px 24px;">
            <p style="margin:0 0 12px 0;font-size:14px;font-weight:700;color:{NAVY};text-transform:uppercase;letter-spacing:0.5px;">
              ¿Qué obtienes al analizarte?
            </p>
            <table cellpadding="0" cellspacing="0" width="100%">
              <tr>
                <td style="padding:6px 0;font-size:15px;color:{TEXT};">
                  <span style="color:{CYAN};font-weight:700;margin-right:8px;">✓</span>
                  Conoce tu probabilidad real de riesgo académico
                </td>
              </tr>
              <tr>
                <td style="padding:6px 0;font-size:15px;color:{TEXT};">
                  <span style="color:{CYAN};font-weight:700;margin-right:8px;">✓</span>
                  Identifica tus áreas de mejora con análisis personalizado
                </td>
              </tr>
              <tr>
                <td style="padding:6px 0;font-size:15px;color:{TEXT};">
                  <span style="color:{CYAN};font-weight:700;margin-right:8px;">✓</span>
                  Accede a consejos específicos según tu situación
                </td>
              </tr>
              <tr>
                <td style="padding:6px 0;font-size:15px;color:{TEXT};">
                  <span style="color:{CYAN};font-weight:700;margin-right:8px;">✓</span>
                  Chat con el consejero académico virtual 24/7
                </td>
              </tr>
            </table>
          </td>
        </tr>
      </table>

      <!-- CTA Button -->
      <table cellpadding="0" cellspacing="0" style="margin-bottom:32px;">
        <tr>
          <td style="background-color:{CYAN};border-radius:8px;">
            <a href="#" style="display:inline-block;padding:14px 32px;font-size:15px;font-weight:600;color:#ffffff;text-decoration:none;letter-spacing:0.3px;">
              Analizar mi riesgo ahora
            </a>
          </td>
        </tr>
      </table>

      <p style="margin:0;font-size:16px;line-height:1.7;color:{TEXT};">
        Recuerda: el conocimiento es el primer paso para mejorar. ¡Mucho ánimo,
        <strong>{student_name}</strong>! 💪
      </p>
    """
    return _base_layout(header_color=CYAN, header_text="Recordatorio", body_html=body)


# ============================================================================
# ENVÍO SMTP (síncrono, se llama desde un executor)
# ============================================================================

def _send_email_sync(to_email: str, subject: str, html_content: str) -> None:
    """
    Envía un correo usando smtplib con STARTTLS.
    Esta función es síncrona y debe ser llamada con asyncio.to_thread().
    """
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"{settings.FROM_NAME} <{settings.FROM_EMAIL}>"
    msg["To"]      = to_email

    msg.attach(MIMEText(html_content, "html", "utf-8"))

    with smtplib.SMTP(settings.SMTP_SERVER, settings.SMTP_PORT, timeout=15) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        server.sendmail(settings.FROM_EMAIL, to_email, msg.as_string())


# ============================================================================
# API PÚBLICA DEL SERVICIO
# ============================================================================

async def send_risk_alert(
    professor_email: str,
    professor_name: str,
    student_name: str,
    student_email: str,
    risk_level: str,
    course_name: str,
) -> bool:
    """
    Notifica a un profesor que un estudiante tiene riesgo ALTO.

    Returns:
        True si el correo se envió correctamente, False si hubo un error.
    """
    subject = f"⚠️ Alerta de riesgo académico — {student_name}"
    html = _risk_alert_html(
        professor_name=professor_name,
        student_name=student_name,
        student_email=student_email,
        risk_level=risk_level,
        course_name=course_name,
    )
    try:
        await asyncio.to_thread(_send_email_sync, professor_email, subject, html)
        logger.info(
            "Alerta de riesgo enviada a %s para estudiante %s",
            professor_email,
            student_email,
        )
        return True
    except Exception as exc:
        logger.error(
            "Error al enviar alerta de riesgo a %s: %s",
            professor_email,
            exc,
            exc_info=True,
        )
        return False


async def send_predictor_reminder(student_email: str, student_name: str) -> bool:
    """
    Envía un recordatorio motivacional al estudiante para que use el predictor.

    Returns:
        True si el correo se envió correctamente, False si hubo un error.
    """
    subject = "📊 ¿Has revisado tu riesgo académico esta semana?"
    html = _predictor_reminder_html(student_name=student_name)
    try:
        await asyncio.to_thread(_send_email_sync, student_email, subject, html)
        logger.info("Recordatorio enviado a %s", student_email)
        return True
    except Exception as exc:
        logger.error(
            "Error al enviar recordatorio a %s: %s",
            student_email,
            exc,
            exc_info=True,
        )
        return False
