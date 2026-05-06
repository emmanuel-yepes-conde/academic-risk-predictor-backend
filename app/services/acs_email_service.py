"""
Servicio de notificaciones por correo usando Azure Communication Services (ACS).
Coexiste con el servicio SMTP existente (app/services/email_service.py).

Se activa cuando ACS_CONNECTION_STRING está configurado en el .env.
Si no está configurado, los métodos retornan False sin lanzar excepciones.
"""

import asyncio
import logging
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

# ── Paleta de marca ───────────────────────────────────────────────────────────
DARK   = "#1E3932"
GREEN  = "#00754A"
BRAND  = "#006241"
LIGHT  = "#d4e9e2"
CANVAS = "#F8FAFC"
TEXT   = "#0F172A"
MUTED  = "#64748B"
WHITE  = "#ffffff"

RISK_HIGH  = "#DC2626"
RISK_MED   = "#D97706"
RISK_LOW   = GREEN

# ── Logo (URL pública en GitHub) ─────────────────────────────────────────────
_LOGO_SRC = "https://raw.githubusercontent.com/Davidslf/Montiara/refs/heads/main/AR-LOGO.png"


# ============================================================================
# LAYOUT BASE — Responsive
# ============================================================================

def _base_layout(badge_color: str, badge_text: str, body_html: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>Academic Risk</title>
  <style>
    @media only screen and (max-width:600px) {{
      .email-wrap      {{ padding: 16px 8px !important; }}
      .email-card      {{ border-radius: 8px !important; }}
      .email-body      {{ padding: 24px 20px 20px 20px !important; }}
      .email-hdr       {{ padding: 20px 20px !important; }}
      .email-footer    {{ padding: 16px 20px !important; }}
      .info-table      {{ font-size:13px !important; }}
      .main-title      {{ font-size:18px !important; }}
      .risk-pct        {{ font-size:22px !important; }}
      td.col-email     {{ display:none !important; }}
      .hdr-logo-cell   {{ display:block !important; width:100% !important; }}
      .hdr-badge-cell  {{ display:block !important; width:100% !important;
                          text-align:left !important;
                          padding-left:0 !important;
                          padding-top:12px !important; }}
    }}
  </style>
</head>
<body style="margin:0;padding:0;background:{CANVAS};
             font-family:Arial,Helvetica,sans-serif;color:{TEXT};">

  <table class="email-wrap" width="100%" cellpadding="0" cellspacing="0"
         style="background:{CANVAS};padding:32px 16px;">
    <tr><td align="center">

      <table class="email-card" width="100%" cellpadding="0" cellspacing="0"
             style="max-width:600px;background:{WHITE};border-radius:12px;
                    overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08);">

        <!-- HEADER -->
        <tr>
          <td class="email-hdr"
              style="background:{DARK};padding:24px 36px;">
            <table width="100%" cellpadding="0" cellspacing="0"><tr>

              <!-- Logo + nombre -->
              <td class="hdr-logo-cell"
                  style="vertical-align:middle;">
                <table cellpadding="0" cellspacing="0"><tr>
                  <td style="vertical-align:middle;padding-right:10px;">
                    <img src="{_LOGO_SRC}" width="34" height="34"
                         alt="AR" style="display:block;border:0;"/>
                  </td>
                  <td style="vertical-align:middle;">
                    <span style="font-size:18px;font-weight:700;
                                 color:{WHITE};letter-spacing:0.2px;">
                      Academic
                      <span style="color:{LIGHT};">Risk</span>
                    </span>
                  </td>
                </tr></table>
              </td>

              <!-- Badge -->
              <td class="hdr-badge-cell"
                  style="vertical-align:middle;text-align:right;
                         padding-left:16px;white-space:nowrap;">
                <span style="display:inline-block;background:{badge_color};
                             color:{WHITE};font-size:10px;font-weight:700;
                             padding:5px 14px;border-radius:20px;
                             letter-spacing:0.7px;text-transform:uppercase;">
                  {badge_text}
                </span>
              </td>

            </tr></table>
          </td>
        </tr>

        <!-- BODY -->
        <tr>
          <td class="email-body"
              style="padding:36px 36px 28px 36px;">
            {body_html}
          </td>
        </tr>

        <!-- FOOTER -->
        <tr>
          <td class="email-footer"
              style="background:{CANVAS};padding:18px 36px;
                     border-top:1px solid #E2E8F0;text-align:center;">
            <p style="margin:0;font-size:12px;color:{MUTED};line-height:1.6;">
              Mensaje generado automáticamente por
              <strong>Academic Risk</strong>.<br/>
              Por favor no responder a este correo.
            </p>
          </td>
        </tr>

        <!-- FRANJA -->
        <tr>
          <td style="background:linear-gradient(90deg,{DARK} 0%,{GREEN} 100%);
                     height:4px;"></td>
        </tr>

      </table>

    </td></tr>
  </table>
</body>
</html>"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _btn(text: str, href: str = "#") -> str:
    return f"""<table width="100%" cellpadding="0" cellspacing="0"
       style="margin-top:28px;">
  <tr>
    <td align="center">
      <table cellpadding="0" cellspacing="0">
        <tr>
          <td style="background:{GREEN};border-radius:8px;">
            <a href="{href}"
               style="display:inline-block;padding:13px 32px;
                      font-size:14px;font-weight:600;color:{WHITE};
                      text-decoration:none;letter-spacing:0.2px;">
              {text}
            </a>
          </td>
        </tr>
      </table>
    </td>
  </tr>
</table>"""


def _info_card(rows: list[tuple[str, str]]) -> str:
    rows_html = "".join(
        f"""<tr>
              <td style="padding:6px 0;font-size:13px;color:{MUTED};
                         width:150px;vertical-align:top;">
                <strong style="color:{DARK};">{label}</strong>
              </td>
              <td style="padding:6px 0;font-size:13px;
                         color:{TEXT};vertical-align:top;">
                {value}
              </td>
            </tr>"""
        for label, value in rows
    )
    return f"""<table class="info-table" width="100%" cellpadding="0" cellspacing="0"
  style="background:{LIGHT};border-radius:10px;
         border-left:4px solid {GREEN};margin:20px 0;">
  <tr><td style="padding:18px 20px;">
    <table width="100%" cellpadding="0" cellspacing="0">
      {rows_html}
    </table>
  </td></tr>
</table>"""


def _section_label(text: str) -> str:
    return (f'<p style="margin:0 0 6px 0;font-size:11px;font-weight:700;'
            f'text-transform:uppercase;letter-spacing:0.7px;color:{MUTED};">'
            f'{text}</p>')


def _recommendation_list(items: list[str]) -> str:
    rows = "".join(
        f'<tr><td style="padding:5px 0;font-size:14px;color:{TEXT};">'
        f'<span style="color:{GREEN};font-weight:700;margin-right:10px;">&#8594;</span>'
        f'{item}</td></tr>'
        for item in items
    )
    return f"""<table width="100%" cellpadding="0" cellspacing="0"
  style="background:{LIGHT};border-radius:10px;margin:20px 0;">
  <tr><td style="padding:18px 20px;">
    <p style="margin:0 0 12px 0;font-size:11px;font-weight:700;
               text-transform:uppercase;letter-spacing:0.5px;color:{DARK};">
      Acciones recomendadas
    </p>
    <table cellpadding="0" cellspacing="0" width="100%">
      {rows}
    </table>
  </td></tr>
</table>"""


# ============================================================================
# TEMPLATE 1 — Recordatorio de primer acceso (→ Estudiante)
# ============================================================================

def _first_access_html(student_name: str) -> str:
    body = f"""
      <h1 class="main-title"
          style="margin:0 0 6px 0;font-size:21px;font-weight:700;
                 color:{DARK};text-align:center;">
        Tu semestre ya lleva un mes
      </h1>
      <p style="margin:0 0 28px 0;font-size:13px;color:{MUTED};
                text-align:center;">
        Recordatorio de acceso a la plataforma
      </p>

      <p style="margin:0 0 16px 0;font-size:15px;line-height:1.7;color:{TEXT};">
        Hola <strong>{student_name}</strong>,
      </p>
      <p style="margin:0 0 20px 0;font-size:15px;line-height:1.7;color:{TEXT};">
        Notamos que aún no has ingresado a <strong>Academic Risk</strong>.
        La plataforma te ayuda a conocer tu situación académica actual y
        anticiparte a posibles dificultades durante el semestre.
      </p>

      {_recommendation_list([
          "Consultar tu nivel de riesgo académico actual",
          "Identificar las materias que requieren más atención",
          "Recibir recomendaciones personalizadas de estudio",
          "Hablar con el consejero académico virtual",
      ])}

      <p style="margin:0;font-size:14px;color:{MUTED};
                line-height:1.6;text-align:center;">
        Cuanto antes conozcas tu situación, más tiempo tienes
        para actuar. El semestre avanza.
      </p>
      {_btn("Ingresar a Academic Risk")}
    """
    return _base_layout(GREEN, "Recordatorio", body)


# ============================================================================
# TEMPLATE 2 — Alerta de riesgo de pérdida (→ Estudiante)
# ============================================================================

def _student_risk_alert_html(
    student_name: str,
    course_name: str,
    risk_pct: float,
    risk_level: str,
) -> str:
    color = RISK_HIGH if risk_level == "ALTO" else RISK_MED
    body = f"""
      <h1 class="main-title"
          style="margin:0 0 6px 0;font-size:21px;font-weight:700;
                 color:{DARK};text-align:center;">
        Tu desempeño en {course_name} requiere atención
      </h1>
      <p style="margin:0 0 28px 0;font-size:13px;color:{MUTED};
                text-align:center;">
        Alerta de riesgo académico
      </p>

      <p style="margin:0 0 16px 0;font-size:15px;line-height:1.7;color:{TEXT};">
        Hola <strong>{student_name}</strong>,
      </p>
      <p style="margin:0 0 20px 0;font-size:15px;line-height:1.7;color:{TEXT};">
        El sistema detectó indicadores que podrían afectar tu rendimiento
        en <strong>{course_name}</strong>. Te compartimos esta información
        para que puedas actuar a tiempo.
      </p>

      <table width="100%" cellpadding="0" cellspacing="0"
             style="background:#FEF2F2;border-left:4px solid {color};
                    border-radius:8px;margin:0 0 20px 0;">
        <tr><td style="padding:16px 20px;text-align:center;">
          <p style="margin:0 0 4px 0;font-size:10px;font-weight:700;
                     color:{color};text-transform:uppercase;
                     letter-spacing:0.7px;">
            Nivel de riesgo detectado
          </p>
          <p class="risk-pct"
             style="margin:6px 0 4px 0;font-size:28px;font-weight:700;
                    color:{TEXT};">
            {risk_pct:.0f}%
            <span style="font-size:13px;font-weight:700;
                         color:{color};margin-left:6px;">
              {risk_level}
            </span>
          </p>
          <p style="margin:0;font-size:12px;color:{MUTED};">
            Probabilidad estimada de no aprobar {course_name}
          </p>
        </td></tr>
      </table>

      {_recommendation_list([
          "Contacta a tu docente para orientación adicional",
          "Busca tutorías o grupos de estudio en tu institución",
          "Revisa los materiales del curso y refuerza los temas clave",
          "Ingresa a Academic Risk para ver el análisis completo",
      ])}

      <p style="margin:0;font-size:13px;color:{MUTED};
                line-height:1.6;text-align:center;">
        Si crees que hay un error, consulta con tu docente
        o el área de consejería.
      </p>
      {_btn("Ver mi análisis completo")}
    """
    return _base_layout(color, "Alerta de Riesgo", body)


# ============================================================================
# TEMPLATE 3 — Felicitación por buen desempeño (→ Estudiante)
# ============================================================================

def _good_performance_html(
    student_name: str,
    course_name: str,
    risk_pct: float,
) -> str:
    body = f"""
      <h1 class="main-title"
          style="margin:0 0 6px 0;font-size:21px;font-weight:700;
                 color:{DARK};text-align:center;">
        Tu esfuerzo está dando resultados
      </h1>
      <p style="margin:0 0 28px 0;font-size:13px;color:{MUTED};
                text-align:center;">
        Buen desempeño académico · {course_name}
      </p>

      <p style="margin:0 0 16px 0;font-size:15px;line-height:1.7;color:{TEXT};">
        Hola <strong>{student_name}</strong>,
      </p>
      <p style="margin:0 0 20px 0;font-size:15px;line-height:1.7;color:{TEXT};">
        El análisis de riesgo para <strong>{course_name}</strong> muestra
        que vas por muy buen camino. Tu dedicación es evidente
        y los indicadores lo confirman.
      </p>

      <table width="100%" cellpadding="0" cellspacing="0"
             style="background:#F0FDF4;border-left:4px solid {GREEN};
                    border-radius:8px;margin:0 0 20px 0;">
        <tr><td style="padding:16px 20px;text-align:center;">
          <p style="margin:0 0 4px 0;font-size:10px;font-weight:700;
                     color:{GREEN};text-transform:uppercase;
                     letter-spacing:0.7px;">
            Nivel de riesgo actual
          </p>
          <p class="risk-pct"
             style="margin:6px 0 4px 0;font-size:28px;font-weight:700;
                    color:{TEXT};">
            {risk_pct:.0f}%
            <span style="font-size:13px;font-weight:700;
                         color:{GREEN};margin-left:6px;">
              BAJO
            </span>
          </p>
          <p style="margin:0;font-size:12px;color:{MUTED};">
            Probabilidad estimada de no aprobar {course_name}
          </p>
        </td></tr>
      </table>

      {_recommendation_list([
          "Continúa con tu ritmo de estudio actual",
          "Revisa el análisis completo para identificar áreas de mejora",
          "Sigue usando Academic Risk para monitorear tu progreso",
      ])}

      <p style="margin:0;font-size:15px;line-height:1.7;
                color:{TEXT};text-align:center;">
        Sigue así, <strong>{student_name}</strong>. El semestre va bien.
      </p>
      {_btn("Ver mi análisis completo")}
    """
    return _base_layout(GREEN, "Buen Desempeno", body)


# ============================================================================
# TEMPLATE 4 — Resumen de riesgo al profesor (tabla, máx. 15 estudiantes)
# ============================================================================

def _professor_risk_summary_html(
    professor_name: str,
    course_name: str,
    course_code: str,
    students: list[dict],
) -> str:
    MAX_ROWS = 15
    sorted_students = sorted(students, key=lambda x: x["risk_pct"], reverse=True)
    shown    = sorted_students[:MAX_ROWS]
    hidden   = len(sorted_students) - MAX_ROWS if len(sorted_students) > MAX_ROWS else 0
    at_risk  = [s for s in students if s["level"] in ("ALTO", "MEDIO")]

    def _badge(level: str, pct: float) -> str:
        c = RISK_HIGH if level == "ALTO" else (RISK_MED if level == "MEDIO" else RISK_LOW)
        return (f'<span style="display:inline-block;background:{c};color:{WHITE};'
                f'font-size:11px;font-weight:700;padding:3px 10px;'
                f'border-radius:12px;white-space:nowrap;">'
                f'{pct:.0f}% {level}</span>')

    rows_html = "".join(
        f"""<tr style="border-bottom:1px solid #F1F5F9;">
              <td style="padding:9px 12px;font-size:13px;
                         color:{TEXT};font-weight:600;">
                {s["name"]}
              </td>
              <td class="col-email"
                  style="padding:9px 12px;font-size:12px;color:{MUTED};">
                {s.get("email","—")}
              </td>
              <td style="padding:9px 12px;text-align:right;">
                {_badge(s["level"], s["risk_pct"])}
              </td>
            </tr>"""
        for s in shown
    )

    hidden_row = (
        f'<tr><td colspan="3" style="padding:10px 12px;font-size:12px;'
        f'color:{MUTED};text-align:center;">'
        f'+ {hidden} estudiante(s) más — ver todos en la plataforma'
        f'</td></tr>'
    ) if hidden > 0 else ""

    high_c = sum(1 for s in students if s["level"] == "ALTO")
    med_c  = sum(1 for s in students if s["level"] == "MEDIO")

    body = f"""
      <h1 class="main-title"
          style="margin:0 0 6px 0;font-size:21px;font-weight:700;
                 color:{DARK};text-align:center;">
        Resumen de riesgo académico
      </h1>
      <p style="margin:0 0 28px 0;font-size:13px;color:{MUTED};
                text-align:center;">
        {course_code} — {course_name}
      </p>

      <p style="margin:0 0 16px 0;font-size:15px;line-height:1.7;color:{TEXT};">
        Estimado/a <strong>{professor_name}</strong>,
      </p>
      <p style="margin:0 0 20px 0;font-size:15px;line-height:1.7;color:{TEXT};">
        Se identificaron
        <strong style="color:{RISK_HIGH};">{high_c} estudiante(s) con riesgo alto</strong>
        y
        <strong style="color:{RISK_MED};">{med_c} con riesgo medio</strong>
        en su curso.
        {"Puede remitirlos al área de consejería desde la plataforma." if at_risk else ""}
      </p>

      <table width="100%" cellpadding="0" cellspacing="0"
             style="border-radius:10px;overflow:hidden;
                    border:1px solid #E2E8F0;margin:0 0 20px 0;">
        <tr style="background:{DARK};">
          <td style="padding:10px 12px;font-size:11px;font-weight:700;
                     color:{WHITE};text-transform:uppercase;letter-spacing:0.5px;">
            Estudiante
          </td>
          <td class="col-email"
              style="padding:10px 12px;font-size:11px;font-weight:700;
                     color:{WHITE};text-transform:uppercase;letter-spacing:0.5px;">
            Correo
          </td>
          <td style="padding:10px 12px;font-size:11px;font-weight:700;
                     color:{WHITE};text-transform:uppercase;letter-spacing:0.5px;
                     text-align:right;">
            Riesgo
          </td>
        </tr>
        {rows_html}
        {hidden_row}
      </table>

      <p style="margin:0;font-size:13px;color:{MUTED};
                line-height:1.6;text-align:center;">
        Los estudiantes con riesgo alto o medio pueden requerir
        acompañamiento adicional.
      </p>
      {_btn("Ver detalle en la plataforma")}
    """
    return _base_layout(GREEN, "Reporte", body)


# ============================================================================
# TEMPLATE 5 — Notificación de remisión al estudiante
# ============================================================================

def _referral_student_html(
    student_name: str,
    professor_name: str,
    course_name: str,
    tipo_remision: str,
    observaciones: str,
    fecha_remision: str,
) -> str:
    body = f"""
      <h1 class="main-title"
          style="margin:0 0 6px 0;font-size:21px;font-weight:700;
                 color:{DARK};text-align:center;">
        Has sido remitido a consejería académica
      </h1>
      <p style="margin:0 0 28px 0;font-size:13px;color:{MUTED};
                text-align:center;">
        {course_name}
      </p>

      <p style="margin:0 0 16px 0;font-size:15px;line-height:1.7;color:{TEXT};">
        Hola <strong>{student_name}</strong>,
      </p>
      <p style="margin:0 0 20px 0;font-size:15px;line-height:1.7;color:{TEXT};">
        El docente <strong>{professor_name}</strong> ha generado una remisión
        al área de permanencia en tu nombre. El equipo de consejería se
        pondrá en contacto contigo próximamente.
      </p>

      {_info_card([
          ("Tipo de remisión", tipo_remision),
          ("Fecha",            fecha_remision),
          ("Docente",          professor_name),
          ("Materia",          course_name),
      ])}

      {_section_label("Observaciones del docente")}
      <p style="margin:0 0 24px 0;font-size:14px;line-height:1.7;
                color:{TEXT};background:{CANVAS};padding:14px 16px;
                border-radius:8px;border:1px solid #E2E8F0;">
        {observaciones}
      </p>

      <p style="margin:0;font-size:13px;color:{MUTED};
                line-height:1.6;text-align:center;">
        Si tienes dudas, comunícate con tu docente o con el área
        de permanencia de tu institución.
      </p>
    """
    return _base_layout(GREEN, "Remision", body)


# ============================================================================
# TEMPLATE 6 — Notificación de remisión al área de consejería
# ============================================================================

def _referral_consejeria_html(
    student_name: str,
    student_email: str,
    professor_name: str,
    course_name: str,
    tipo_remision: str,
    observaciones: str,
    fecha_remision: str,
) -> str:
    body = f"""
      <h1 class="main-title"
          style="margin:0 0 6px 0;font-size:21px;font-weight:700;
                 color:{DARK};text-align:center;">
        Nueva remisión pendiente de atención
      </h1>
      <p style="margin:0 0 28px 0;font-size:13px;color:{MUTED};
                text-align:center;">
        Caso asignado por docente — {course_name}
      </p>

      <p style="margin:0 0 20px 0;font-size:15px;line-height:1.7;color:{TEXT};">
        El docente <strong>{professor_name}</strong> ha remitido a un estudiante
        al área de permanencia. A continuación los datos del caso:
      </p>

      {_info_card([
          ("Estudiante",       student_name),
          ("Correo",           f'<a href="mailto:{student_email}" style="color:{GREEN};">{student_email}</a>'),
          ("Docente",          professor_name),
          ("Materia",          course_name),
          ("Tipo de remisión", tipo_remision),
          ("Fecha remisión",   fecha_remision),
      ])}

      {_section_label("Observaciones del docente")}
      <p style="margin:0 0 20px 0;font-size:14px;line-height:1.7;
                color:{TEXT};background:{CANVAS};padding:14px 16px;
                border-radius:8px;border:1px solid #E2E8F0;">
        {observaciones}
      </p>

      <table cellpadding="0" cellspacing="0"
             style="margin:0 auto 20px auto;">
        <tr>
          <td style="background:rgba(220,38,38,0.08);
                     border:1px solid rgba(220,38,38,0.25);
                     border-radius:20px;padding:6px 18px;">
            <span style="font-size:12px;font-weight:700;
                         color:{RISK_HIGH};">
              PENDIENTE — requiere atención
            </span>
          </td>
        </tr>
      </table>

      <p style="margin:0;font-size:13px;color:{MUTED};
                line-height:1.6;text-align:center;">
        Actualiza el estado de la remisión desde la plataforma
        una vez hayas atendido al estudiante.
      </p>
    """
    return _base_layout(RISK_HIGH, "Nuevo Caso", body)


# ============================================================================
# ENVÍO ACS
# ============================================================================

def _is_configured() -> bool:
    return bool(getattr(settings, "ACS_CONNECTION_STRING", None))


async def _send_acs(
    to_email: str,
    subject: str,
    html_content: str,
    plain_text: Optional[str] = None,
) -> bool:
    from azure.communication.email import EmailClient

    def _sync_send() -> None:
        client = EmailClient.from_connection_string(settings.ACS_CONNECTION_STRING)
        message = {
            "senderAddress": settings.ACS_SENDER_EMAIL,
            "replyTo": [{"address": settings.ACS_SENDER_EMAIL,
                         "displayName": "Academic Risk"}],
            "recipients": {"to": [{"address": to_email}]},
            "content": {
                "subject":   subject,
                "html":      html_content,
                "plainText": plain_text or subject,
            },
        }
        poller = client.begin_send(message)
        result = poller.result()
        if result.get("status", "").upper() not in ("SUCCEEDED", ""):
            raise RuntimeError(f"ACS status: {result.get('status')}")

    try:
        await asyncio.to_thread(_sync_send)
        logger.info("ACS email enviado a %s — %s", to_email, subject)
        return True
    except Exception as exc:
        logger.error("ACS email falló para %s: %s", to_email, exc, exc_info=True)
        return False


def _guard() -> bool:
    if not _is_configured():
        logger.warning("ACS_CONNECTION_STRING no configurado — ACS desactivado")
        return False
    return True


# ============================================================================
# API PÚBLICA
# ============================================================================

async def send_first_access_reminder(
    student_email: str, student_name: str,
) -> bool:
    if not _guard(): return False
    return await _send_acs(
        to_email=student_email,
        subject="Tu semestre ya lleva un mes — Academic Risk",
        html_content=_first_access_html(student_name),
    )


async def send_student_risk_alert(
    student_email: str, student_name: str,
    course_name: str, risk_pct: float, risk_level: str,
) -> bool:
    if not _guard(): return False
    return await _send_acs(
        to_email=student_email,
        subject=f"Indicadores de riesgo en {course_name} — Academic Risk",
        html_content=_student_risk_alert_html(
            student_name, course_name, risk_pct, risk_level),
    )


async def send_good_performance(
    student_email: str, student_name: str,
    course_name: str, risk_pct: float,
) -> bool:
    if not _guard(): return False
    return await _send_acs(
        to_email=student_email,
        subject=f"Vas por buen camino en {course_name} — Academic Risk",
        html_content=_good_performance_html(student_name, course_name, risk_pct),
    )


async def send_professor_risk_summary(
    professor_email: str, professor_name: str,
    course_name: str, course_code: str,
    students: list[dict],
) -> bool:
    if not _guard(): return False
    return await _send_acs(
        to_email=professor_email,
        subject=f"Resumen de riesgo académico — {course_code}",
        html_content=_professor_risk_summary_html(
            professor_name, course_name, course_code, students),
    )


async def notify_referral_created(
    *,
    student_name: str, student_email: str,
    professor_name: str, course_name: str,
    tipo_remision: str, observaciones: str, fecha_remision: str,
) -> dict[str, bool]:
    if not _guard(): return {"student": False, "consejeria": False}

    student_ok, consejeria_ok = await asyncio.gather(
        _send_acs(
            to_email=student_email,
            subject=f"Remisión a consejería en {course_name} — Academic Risk",
            html_content=_referral_student_html(
                student_name, professor_name, course_name,
                tipo_remision, observaciones, fecha_remision),
        ),
        _send_acs(
            to_email=settings.ACS_CONSEJERIA_EMAIL,
            subject=f"Nueva remisión: {student_name} — {course_name}",
            html_content=_referral_consejeria_html(
                student_name, student_email, professor_name, course_name,
                tipo_remision, observaciones, fecha_remision),
        ),
    )
    return {"student": student_ok, "consejeria": consejeria_ok}
