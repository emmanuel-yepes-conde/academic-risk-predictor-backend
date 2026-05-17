"""
Templates endpoint — devuelve la lista de todas las plantillas de email y
WhatsApp con datos de muestra para previsualización en el panel de administración.

No requiere autenticación.
"""

from fastapi import APIRouter
from typing import Any

from app.services.acs_email_service import (
    _first_access_html,
    _student_risk_alert_html,
    _good_performance_html,
    _professor_risk_summary_html,
    _referral_student_html,
    _referral_consejeria_html,
)

router = APIRouter()


# ── Sample data ───────────────────────────────────────────────────────────────

_PROFESSOR_STUDENTS = [
    {"name": "Laura Sofía Ramírez", "email": "laura@uni.edu",  "risk_pct": 78.4, "level": "ALTO"},
    {"name": "Andrés Torres",        "email": "andres@uni.edu", "risk_pct": 61.2, "level": "MEDIO"},
    {"name": "Valentina Ortiz",      "email": "vale@uni.edu",   "risk_pct": 55.0, "level": "MEDIO"},
    {"name": "Juan Herrera",         "email": "juan@uni.edu",   "risk_pct": 14.3, "level": "BAJO"},
    {"name": "María Pérez",          "email": "maria@uni.edu",  "risk_pct":  8.1, "level": "BAJO"},
]

# ── WhatsApp plain-text previews ──────────────────────────────────────────────

_WA_BIENVENIDA = (
    "👋 ¡Hola! Soy *Risko*, tu asistente virtual de *Academic Risk*. 🎓\n\n"
    "Por favor, ingresa tu *número de documento* de identidad (cédula o TI) "
    "para comenzar el análisis."
)

_WA_DOCUMENTO_NO_ENCONTRADO = (
    "No encontré ningún estudiante con documento *123456789*.\n"
    "Verifica el número e intenta de nuevo.\n\n"
    "_Si es la primera vez que usas este servicio, ingresa tu cédula o TI._"
)

_WA_SIN_MATERIAS = (
    "Hola *Laura Sofía Ramírez*! 👋\n\n"
    "No tienes materias *activas* inscritas en este momento."
)

_WA_SELECCION_INVALIDA = (
    "Por favor responde con el *número* de la materia que deseas analizar.\n"
    "Ejemplo: *1*\n\n"
    "Escribe *0* para analizar otro estudiante."
)

_WA_RIESGO_ALTO = (
    "📊 *Análisis de Riesgo Académico*\n"
    "Estudiante: Laura Sofía Ramírez\n"
    "Materia: *Programación I* (PRG-101) — 2025-1\n\n"
    "🔴 *Riesgo: ALTO*\n"
    "Probabilidad de reprobar: *78.4%*\n\n"
    "📝 *Calificaciones:*\n"
    "  • Corte 1: *2.50*\n"
    "  • Corte 2: *2.30*\n"
    "  • Corte Final: *2.10*\n"
    "  • Total: *2.30*\n\n"
    "⚠️ Necesitas intervención inmediata. Busca asesoría académica cuanto antes.\n\n"
    "---\n"
    "Puedes elegir otra materia escribiendo su número.\n"
    "Escribe *0* para analizar otro estudiante."
)

_WA_RIESGO_MEDIO = (
    "📊 *Análisis de Riesgo Académico*\n"
    "Estudiante: Andrés Felipe Torres\n"
    "Materia: *Cálculo I* (MAT-201) — 2025-1\n\n"
    "🟡 *Riesgo: MEDIO*\n"
    "Probabilidad de reprobar: *55.2%*\n\n"
    "📝 *Calificaciones:*\n"
    "  • Corte 1: *3.20*\n"
    "  • Corte 2: *3.00*\n"
    "  • Corte Final: *2.80*\n"
    "  • Total: *3.00*\n\n"
    "💡 Estás a tiempo de mejorar. Prioriza los temas con menor calificación.\n\n"
    "---\n"
    "Puedes elegir otra materia escribiendo su número.\n"
    "Escribe *0* para analizar otro estudiante."
)

_WA_RIESGO_BAJO = (
    "📊 *Análisis de Riesgo Académico*\n"
    "Estudiante: María Alejandra Pérez\n"
    "Materia: *Programación I* (PRG-101) — 2025-1\n\n"
    "🟢 *Riesgo: BAJO*\n"
    "Probabilidad de reprobar: *8.1%*\n\n"
    "📝 *Calificaciones:*\n"
    "  • Corte 1: *4.50*\n"
    "  • Corte 2: *4.30*\n"
    "  • Corte Final: *4.20*\n"
    "  • Total: *4.33*\n\n"
    "✅ Vas en buen camino. Mantén el ritmo de estudio.\n\n"
    "---\n"
    "Puedes elegir otra materia escribiendo su número.\n"
    "Escribe *0* para analizar otro estudiante."
)


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.get("/templates", response_model=list[dict[str, Any]])
def list_templates() -> list[dict[str, Any]]:
    """
    Devuelve todas las plantillas de email y WhatsApp con datos de muestra
    para previsualización. No requiere autenticación.
    """
    email_templates: list[dict[str, Any]] = [
        {
            "id": "email_primer_acceso",
            "name": "Recordatorio primer acceso",
            "type": "email",
            "category": "estudiante",
            "subject": "Tu semestre ya lleva un mes — Academic Risk",
            "preview_html": _first_access_html("Laura Sofía Ramírez"),
            "preview_text": "",
        },
        {
            "id": "email_alerta_alto",
            "name": "Alerta de riesgo — ALTO",
            "type": "email",
            "category": "estudiante",
            "subject": "Indicadores de riesgo en Programación I — Academic Risk",
            "preview_html": _student_risk_alert_html(
                "Laura Sofía Ramírez", "Programación I", 78.4, "ALTO"
            ),
            "preview_text": "",
        },
        {
            "id": "email_alerta_medio",
            "name": "Alerta de riesgo — MEDIO",
            "type": "email",
            "category": "estudiante",
            "subject": "Indicadores de riesgo en Cálculo I — Academic Risk",
            "preview_html": _student_risk_alert_html(
                "Andrés Felipe Torres", "Cálculo I", 55.2, "MEDIO"
            ),
            "preview_text": "",
        },
        {
            "id": "email_buen_desempeno",
            "name": "Buen desempeño académico",
            "type": "email",
            "category": "estudiante",
            "subject": "Vas por buen camino en Programación I — Academic Risk",
            "preview_html": _good_performance_html(
                "María Alejandra Pérez", "Programación I", 8.1
            ),
            "preview_text": "",
        },
        {
            "id": "email_resumen_profesor",
            "name": "Resumen de riesgo del curso",
            "type": "email",
            "category": "profesor",
            "subject": "Resumen de riesgo académico — PRG-101",
            "preview_html": _professor_risk_summary_html(
                "Carlos Mendoza",
                "Programación I",
                "PRG-101",
                _PROFESSOR_STUDENTS,
            ),
            "preview_text": "",
        },
        {
            "id": "email_remision_estudiante",
            "name": "Notificación de remisión — Estudiante",
            "type": "email",
            "category": "estudiante",
            "subject": "Remisión a consejería en PRG-101 — Programación I — Academic Risk",
            "preview_html": _referral_student_html(
                "Laura Sofía Ramírez",
                "Carlos Mendoza",
                "PRG-101 — Programación I",
                "Bajo rendimiento académico",
                "El estudiante presenta calificaciones por debajo del mínimo aprobatorio "
                "en los últimos dos cortes evaluativos. Se recomienda seguimiento personalizado.",
                "2025-05-06",
            ),
            "preview_text": "",
        },
        {
            "id": "email_remision_consejeria",
            "name": "Notificación de remisión — Consejería",
            "type": "email",
            "category": "consejeria",
            "subject": "Nueva remisión: Laura Sofía Ramírez — PRG-101 — Programación I",
            "preview_html": _referral_consejeria_html(
                "Laura Sofía Ramírez",
                "laura.ramirez@uniminuto.edu.co",
                "Carlos Mendoza",
                "PRG-101 — Programación I",
                "Bajo rendimiento académico",
                "El estudiante presenta calificaciones por debajo del mínimo aprobatorio "
                "en los últimos dos cortes evaluativos. Se recomienda seguimiento personalizado.",
                "2025-05-06",
            ),
            "preview_text": "",
        },
    ]

    whatsapp_templates: list[dict[str, Any]] = [
        {
            "id": "wa_bienvenida",
            "name": "Bienvenida / Saludo inicial",
            "type": "whatsapp",
            "category": "chatbot",
            "subject": "",
            "preview_html": "",
            "preview_text": _WA_BIENVENIDA,
        },
        {
            "id": "wa_documento_no_encontrado",
            "name": "Documento no encontrado",
            "type": "whatsapp",
            "category": "chatbot",
            "subject": "",
            "preview_html": "",
            "preview_text": _WA_DOCUMENTO_NO_ENCONTRADO,
        },
        {
            "id": "wa_sin_materias",
            "name": "Sin materias activas",
            "type": "whatsapp",
            "category": "chatbot",
            "subject": "",
            "preview_html": "",
            "preview_text": _WA_SIN_MATERIAS,
        },
        {
            "id": "wa_seleccion_invalida",
            "name": "Selección inválida",
            "type": "whatsapp",
            "category": "chatbot",
            "subject": "",
            "preview_html": "",
            "preview_text": _WA_SELECCION_INVALIDA,
        },
        {
            "id": "wa_riesgo_alto",
            "name": "Análisis de riesgo — ALTO",
            "type": "whatsapp",
            "category": "chatbot",
            "subject": "",
            "preview_html": "",
            "preview_text": _WA_RIESGO_ALTO,
        },
        {
            "id": "wa_riesgo_medio",
            "name": "Análisis de riesgo — MEDIO",
            "type": "whatsapp",
            "category": "chatbot",
            "subject": "",
            "preview_html": "",
            "preview_text": _WA_RIESGO_MEDIO,
        },
        {
            "id": "wa_riesgo_bajo",
            "name": "Análisis de riesgo — BAJO",
            "type": "whatsapp",
            "category": "chatbot",
            "subject": "",
            "preview_html": "",
            "preview_text": _WA_RIESGO_BAJO,
        },
    ]

    return email_templates + whatsapp_templates
