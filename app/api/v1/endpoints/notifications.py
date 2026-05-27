"""
Endpoints de Notificaciones por Correo Electrónico
Permite enviar alertas de riesgo a profesores y recordatorios a estudiantes.
"""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr, Field

from app.services.email_service import send_risk_alert
from app.services.notification_service import _send_email as _send_via_routing

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# SCHEMAS DE REQUEST / RESPONSE
# ============================================================================

class RiskAlertRequest(BaseModel):
    professor_email: EmailStr = Field(..., description="Correo del profesor destinatario")
    professor_name: str = Field(..., min_length=1, description="Nombre del profesor")
    student_name: str = Field(..., min_length=1, description="Nombre del estudiante")
    student_email: EmailStr = Field(..., description="Correo del estudiante")
    risk_level: str = Field(..., description="Nivel de riesgo (ej. ALTO, MEDIO, BAJO)")
    course_name: str = Field(..., min_length=1, description="Nombre del curso o materia")


class PredictorReminderRequest(BaseModel):
    student_email: EmailStr = Field(..., description="Correo del estudiante destinatario")
    student_name: str = Field(..., min_length=1, description="Nombre del estudiante")


class NotificationResponse(BaseModel):
    success: bool
    message: str


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.post(
    "/notifications/risk-alert",
    response_model=NotificationResponse,
    summary="Enviar alerta de riesgo al profesor",
    description=(
        "Envía un correo HTML al profesor notificando que un estudiante "
        "ha obtenido un nivel de riesgo académico alto."
    ),
)
async def risk_alert_endpoint(body: RiskAlertRequest) -> NotificationResponse:
    """
    POST /api/v1/notifications/risk-alert

    Envía una alerta de riesgo académico al profesor indicado.
    Si el envío falla (error SMTP, etc.) se registra el error pero
    el endpoint retorna 200 con success=False para no romper flujos upstream.
    """
    sent = await send_risk_alert(
        professor_email=body.professor_email,
        professor_name=body.professor_name,
        student_name=body.student_name,
        student_email=body.student_email,
        risk_level=body.risk_level,
        course_name=body.course_name,
    )

    if sent:
        return NotificationResponse(
            success=True,
            message=f"Alerta de riesgo enviada correctamente a {body.professor_email}.",
        )

    logger.warning(
        "No se pudo enviar la alerta de riesgo a %s para el estudiante %s",
        body.professor_email,
        body.student_email,
    )
    raise HTTPException(
        status_code=502,
        detail="No se pudo enviar el correo de alerta. Verifica la configuración SMTP.",
    )


@router.post(
    "/notifications/predictor-reminder",
    response_model=NotificationResponse,
    summary="Enviar recordatorio al estudiante",
    description=(
        "Envía un correo motivacional al estudiante invitándolo a usar "
        "el predictor de riesgo académico."
    ),
)
async def predictor_reminder_endpoint(body: PredictorReminderRequest) -> NotificationResponse:
    """
    POST /api/v1/notifications/predictor-reminder

    Envía un recordatorio al estudiante para que use el predictor.
    Usa el routing unificado (ACS para @uniminuto, SMTP para el resto).
    """
    from app.services.acs_email_service import _reminder_html
    primer_nombre = body.student_name.split()[0] if body.student_name else "estudiante"
    sent = await _send_via_routing(
        email=body.student_email,
        name=body.student_name,
        title="📊 ¿Has revisado tu riesgo académico esta semana?",
        body=(
            f"Hola {primer_nombre}, te invitamos a revisar tu predicción de riesgo académico "
            "y recibir consejos personalizados para este semestre."
        ),
        html_content=_reminder_html(body.student_name),
    )

    if sent:
        logger.warning("[Recordatorio] ✅ Enviado → %s", body.student_email)
        return NotificationResponse(
            success=True,
            message=f"Recordatorio enviado correctamente a {body.student_email}.",
        )

    logger.warning("[Recordatorio] ❌ Falló → %s", body.student_email)
    raise HTTPException(
        status_code=502,
        detail="No se pudo enviar el correo de recordatorio. Revisa los logs del servidor.",
    )
