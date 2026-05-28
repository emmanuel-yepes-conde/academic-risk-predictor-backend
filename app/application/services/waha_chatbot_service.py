"""
Servicio de chatbot para WhatsApp via WAHA.
Gestiona el flujo conversacional: documento → materias inscritas → análisis de riesgo.
Estado por número de teléfono almacenado en memoria (in-process).

Timeout:
  - Después de enviar un análisis (step=WAITING_SUBJECT) y 3 min de inactividad:
    envía mensaje de seguimiento preguntando si necesita más ayuda.
  - Después de enviar el seguimiento (step=WAITING_FOLLOWUP) y 3 min más sin respuesta:
    envía despedida y cierra la sesión.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import httpx

from app.core.config import settings
from app.domain.enums import EnrollmentStatusEnum
from app.infrastructure.models.course import Course
from app.infrastructure.models.enrollment import Enrollment
from app.infrastructure.models.student_profile import StudentProfile
from app.infrastructure.models.subject import Subject
from app.infrastructure.models.user import User

logger = logging.getLogger(__name__)

# Estado de conversación por número de teléfono: phone -> session dict
_sessions: Dict[str, dict] = {}

TIMEOUT_SECONDS = 3 * 60  # 3 minutos


def _now() -> datetime:
    return datetime.now(timezone.utc)


class WahaChatbotService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def handle_message(self, phone: str, text: str) -> str:
        state = _sessions.get(phone, {"step": "WAITING_DOCUMENT"})
        step = state.get("step", "WAITING_DOCUMENT")

        text = text.strip()

        # Actualizar última actividad del usuario
        if phone in _sessions:
            _sessions[phone]["last_user_at"] = _now()

        # Comandos globales de reinicio — incluye cualquier saludo conocido
        if text.lower() in ("0", "reiniciar", "reset") or _is_greeting(text):
            _sessions.pop(phone, None)
            # Crear sesión mínima para poder trackear timeout si no responde
            _sessions[phone] = {
                "step": "WAITING_DOCUMENT",
                "last_bot_at": _now(),
                "last_user_at": _now(),
            }
            return self._greeting()

        if step == "WAITING_DOCUMENT":
            return await self._handle_document(phone, text)

        if step == "WAITING_SUBJECT":
            return await self._handle_subject_selection(phone, text, state)

        if step == "WAITING_THANKS_RESPONSE":
            return self._handle_thanks_response(phone, text, state)

        if step == "WAITING_FOLLOWUP":
            return self._handle_followup_response(phone, text, state)

        _sessions.pop(phone, None)
        return self._greeting()

    # ─── Paso 1: recibir número de documento ───────────────────────────────────

    async def _handle_document(self, phone: str, doc_number: str) -> str:
        # Agradecimientos / despedidas → respuesta cálida sin error
        if _is_thanks(doc_number) or _is_farewell(doc_number):
            return (
                "¡Con mucho gusto! 😊\n\n"
                "Si en algún momento quieres revisar tu progreso académico, "
                "solo escríbeme tu *número de documento* y te ayudo enseguida. 👋"
            )

        # Texto que claramente no es un número de documento
        if not _looks_like_document(doc_number):
            return (
                "Hola! Soy *Risko*, tu asistente de *Academic Risk* 🤖\n\n"
                "Solo puedo ayudarte con tu rendimiento académico.\n\n"
                "Para comenzar, ingresa tu *número de documento* "
                "de identidad _(cédula o TI)_ y te muestro tu análisis de riesgo. 📊"
            )

        profile_result = await self._session.execute(
            select(StudentProfile).where(StudentProfile.document_number == doc_number)
        )
        profile = profile_result.scalar_one_or_none()

        if profile is None:
            return (
                f"No encontré ningún estudiante con documento *{doc_number}*.\n"
                "Verifica el número e intenta de nuevo.\n\n"
                "_Si es la primera vez que usas este servicio, ingresa tu cédula o TI._"
            )

        user_result = await self._session.execute(
            select(User).where(User.id == profile.user_id)
        )
        user = user_result.scalar_one_or_none()
        student_name = user.full_name if user else doc_number

        enrollments = await self._get_active_enrollments(profile.user_id)

        if not enrollments:
            return (
                f"Hola *{student_name}*!\n\n"
                "No tienes materias *activas* inscritas en este momento."
            )

        _sessions[phone] = {
            "step": "WAITING_SUBJECT",
            "student_id": str(profile.user_id),
            "student_name": student_name,
            "document_number": doc_number,
            "enrollments": enrollments,
            "last_user_at": _now(),
            "last_bot_at": _now(),
            "followup_sent": False,
        }

        return self._build_subject_menu(student_name, enrollments)

    # ─── Paso 2: seleccionar materia y generar análisis ────────────────────────

    async def _handle_subject_selection(
        self, phone: str, text: str, state: dict
    ) -> str:
        enrollments: List[dict] = state.get("enrollments", [])
        student_name: str = state.get("student_name", "")
        first = student_name.split()[0] if student_name else "estudiante"

        # Detectar agradecimiento antes de intentar procesar como materia
        if _is_thanks(text):
            _sessions[phone]["step"] = "WAITING_THANKS_RESPONSE"
            _sessions[phone]["last_bot_at"] = _now()
            return (
                f"¡Con todo gusto, {first}! 😊\n\n"
                "¿Deseas *finalizar* el chat o te gustaría *consultar otra materia*? 📚\n\n"
                "_Responde *finalizar* para cerrar la sesión o *otra materia* para continuar._"
            )

        # Si el texto parece un número de documento (≥8 dígitos), redirigir al paso 1
        if text.strip().isdigit() and len(text.strip()) >= 8:
            _sessions.pop(phone, None)
            return await self._handle_document(phone, text.strip())

        # Intentar primero como número de materia
        try:
            selection = int(text)
            if selection < 1 or selection > len(enrollments):
                return (
                    f"Selección inválida. Elige un número entre *1* y *{len(enrollments)}*.\n"
                    "Escribe *0* para reiniciar."
                )
            enroll = enrollments[selection - 1]

        except ValueError:
            # No es número → buscar por texto en nombre o código de la materia
            query = text.lower().strip()
            matches = [
                (i + 1, e)
                for i, e in enumerate(enrollments)
                if query in e["subject_name"].lower() or query in e["subject_code"].lower()
            ]

            if len(matches) == 0:
                # Ninguna coincidencia → mostrar menú de nuevo
                return (
                    f"No encontré ninguna materia con el nombre '{text}'.\n\n"
                    + self._build_subject_menu(student_name, enrollments)
                )

            if len(matches) > 1:
                # Varias coincidencias → pedir que especifique
                lines = [f"Encontré {len(matches)} materias que coinciden con '{text}':",""]
                for num, e in matches:
                    lines.append(f"  *{num}.* {e['subject_name']} ({e['subject_code']})")
                lines += ["", "Responde con el *número* de la que deseas analizar."]
                return "\n".join(lines)

            # Coincidencia única → proceder directamente
            _num, enroll = matches[0]

        analysis = await self._run_prediction(enroll, student_name)

        # Reset timeout after answering
        _sessions[phone]["last_bot_at"] = _now()
        _sessions[phone]["followup_sent"] = False

        footer = (
            "\n\n💡 Puedes escribir el número de otra materia para analizarla,\n"
            "o *0* para consultar otro estudiante."
        )
        return analysis + footer

    # ─── Paso 3: respuesta a "gracias" tras un análisis ──────────────────────

    def _handle_thanks_response(self, phone: str, text: str, state: dict) -> str:
        t = text.lower().strip()
        name = state.get("student_name", "")

        _end_words = {"finalizar", "terminar", "no", "nada", "listo", "ok",
                      "bye", "adios", "adiós", "chao", "hasta luego", "no gracias"}
        _continue_words = {"otra materia", "otra", "si", "sí", "quiero",
                           "consultar", "menu", "menú", "continuar", "más", "mas"}

        if t in _end_words or any(t.startswith(w) for w in ("finali", "termin")):
            _sessions.pop(phone, None)
            return self._goodbye(name)

        if t in _continue_words or any(t.startswith(w) for w in ("otra", "si ", "sí ", "consu")):
            _sessions[phone]["step"] = "WAITING_SUBJECT"
            _sessions[phone]["last_bot_at"] = _now()
            return self._build_subject_menu(name, state.get("enrollments", []))

        # Respuesta no reconocida → repetir la pregunta suavemente
        first = name.split()[0] if name else "estudiante"
        return (
            f"No entendí bien tu respuesta, {first} 😅\n\n"
            "¿Quieres *finalizar* el chat o *consultar otra materia*? 📚"
        )

    # ─── Paso 4: respuesta al mensaje de seguimiento por timeout ──────────────

    def _handle_followup_response(self, phone: str, text: str, state: dict) -> str:
        negative = {"no", "n", "gracias", "nada", "listo", "ok", "bye", "adios", "adiós"}
        if text.lower().strip() in negative:
            _sessions.pop(phone, None)
            return self._goodbye(state.get("student_name", ""))

        # Respuesta afirmativa → volver al menú de materias
        _sessions[phone]["step"] = "WAITING_SUBJECT"
        _sessions[phone]["last_bot_at"] = _now()
        enrollments = state.get("enrollments", [])
        return self._build_subject_menu(state.get("student_name", ""), enrollments)

    # ─── Consulta de inscripciones activas ────────────────────────────────────

    async def _get_active_enrollments(self, student_id: UUID) -> List[dict]:
        result = await self._session.execute(
            select(
                Enrollment.first_cohort_grade,
                Enrollment.second_cohort_grade,
                Enrollment.third_cohort_grade,
                Enrollment.final_grade,
                Course.section,
                Course.academic_period,
                Subject.name,
                Subject.code,
            )
            .join(Course, Course.id == Enrollment.course_id)
            .join(Subject, Subject.id == Course.subject_id)
            .where(
                Enrollment.student_id == student_id,
                Enrollment.status == EnrollmentStatusEnum.ACTIVE,
            )
        )
        rows = result.all()

        return [
            {
                "subject_name": row.name,
                "subject_code": row.code,
                "section": row.section,
                "academic_period": row.academic_period,
                "first_cohort_grade": _to_float(row.first_cohort_grade),
                "second_cohort_grade": _to_float(row.second_cohort_grade),
                "third_cohort_grade": _to_float(row.third_cohort_grade),
                "final_grade": _to_float(row.final_grade),
            }
            for row in rows
        ]

    # ─── Lógica de predicción ─────────────────────────────────────────────────

    async def _run_prediction(self, enroll: dict, student_name: str) -> str:
        name = enroll["subject_name"]
        code = enroll["subject_code"]
        period = enroll["academic_period"]

        c1 = enroll["first_cohort_grade"]
        c2 = enroll["second_cohort_grade"]
        c3 = enroll["third_cohort_grade"]
        final = enroll["final_grade"]

        lines: List[str] = [
            f"📊 *Análisis de Riesgo Académico*",
            f"👤 {student_name}",
            f"📚 *{name}* ({code}) — {period}",
            "",
        ]

        available = [g for g in [c1, c2, c3] if g is not None]
        if available:
            # Imputar notas faltantes con el promedio de las disponibles
            avg = sum(available) / len(available)
            c1_pred = c1 if c1 is not None else avg
            c2_pred = c2 if c2 is not None else avg
            c3_pred = c3 if c3 is not None else avg
            total_pred = final if final is not None else avg

            predict_url = f"{settings.get_public_base_url()}/api/v1/predict"
            payload = {
                "nota_corte_1": c1_pred,
                "nota_corte_2": c2_pred,
                "nota_corte_final": c3_pred,
                "nota_total": total_pred,
            }
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(predict_url, json=payload)
                    response.raise_for_status()
                    result = response.json()

                prob = result["probabilidad_riesgo"]
                nivel = result["nivel_riesgo"]
                nivel_label = {"ALTO": "ALTO", "MEDIO": "MEDIO", "BAJO": "BAJO"}.get(nivel, nivel)
                is_partial = len(available) < 3 or final is None

                # Ícono según nivel de riesgo
                risk_icon = {"ALTO": "🔴", "MEDIO": "🟡", "BAJO": "🟢"}.get(nivel, "⚪")
                lines += [
                    f"{risk_icon} *Riesgo: {nivel_label}*",
                    f"Probabilidad de reprobar: *{prob * 100:.1f}%*",
                ]
                if is_partial:
                    lines.append(
                        f"_⚠️ Predicción con {len(available)} de 3 cortes registrados "
                        f"(los faltantes se estimaron con promedio {avg:.2f})_"
                    )
                lines += [
                    "",
                    "📝 *Calificaciones:*",
                ]
                if c1 is not None:
                    lines.append(f"  • Corte 1: *{c1:.2f}*")
                if c2 is not None:
                    lines.append(f"  • Corte 2: *{c2:.2f}*")
                if c3 is not None:
                    lines.append(f"  • Corte Final: *{c3:.2f}*")
                if final is not None:
                    lines.append(f"  • Total: *{final:.2f}*")
                lines += ["", _recommendation(nivel)]

            except Exception as exc:
                logger.warning("[WAHA chatbot] prediccion fallo: %s", exc)
                lines.append("No se pudo calcular el riesgo en este momento. Intenta de nuevo mas tarde.")
        else:
            lines.append("Tu docente aun no ha registrado calificaciones para esta materia.")

        return "\n".join(lines)

    # ─── Helpers de UI ────────────────────────────────────────────────────────

    @staticmethod
    def _greeting() -> str:
        return (
            "👋 Hola! Soy *Risko*, tu asistente de *Academic Risk*.\n\n"
            "Estoy aqui para ayudarte a revisar tu rendimiento academico.\n\n"
            "Para comenzar, ingresa tu *numero de documento* de identidad (cedula o TI)."
        )

    @staticmethod
    def _goodbye(name: str) -> str:
        first = name.split()[0] if name else "estudiante"
        return (
            f"Fue un placer ayudarte, {first}! 🎓\n\n"
            "Recuerda que puedes escribir *hola* en cualquier momento "
            "para revisar tu progreso. Mucho exito en tu semestre!"
        )

    @staticmethod
    def _build_subject_menu(student_name: str, enrollments: List[dict]) -> str:
        lines = [
            f"Hola *{student_name}*!",
            "",
            "Tus materias activas inscritas:",
            "",
        ]
        for i, e in enumerate(enrollments, 1):
            lines.append(f"  *{i}.* {e['subject_name']} ({e['subject_code']})")
        lines += [
            "",
            "Responde con el *numero* de la materia que deseas analizar.",
            "Escribe *0* para reiniciar.",
        ]
        return "\n".join(lines)


# ─── Timeout checker (llamado desde APScheduler cada minuto) ─────────────────

async def check_chatbot_timeouts(force: bool = False) -> None:
    """
    Verifica conversaciones inactivas:
    - WAITING_DOCUMENT + 3 min → aviso de que seguimos disponibles, cierra sesión
    - WAITING_SUBJECT   + 3 min → seguimiento cálido preguntando si necesita más ayuda
    - WAITING_FOLLOWUP / WAITING_THANKS_RESPONSE + 3 min → despedida y cierra sesión

    Si force=True se ignora el tiempo transcurrido (útil para pruebas manuales).
    """
    if not settings.WAHA_URL:
        return

    now = _now()
    to_delete: List[str] = []

    for phone, state in list(_sessions.items()):
        step = state.get("step")
        last_bot_at: datetime = state.get("last_bot_at", now)
        elapsed = (now - last_bot_at).total_seconds()
        timed_out = force or elapsed >= TIMEOUT_SECONDS

        # ── Documento sin responder ───────────────────────────────────────────
        if step == "WAITING_DOCUMENT" and timed_out:
            msg = (
                "Hola de nuevo! 👋 Parece que te fuiste...\n\n"
                "No hay problema — cuando quieras revisar tu rendimiento académico "
                "estoy aquí. Solo escríbeme tu *número de documento* y te ayudo enseguida. 😊"
            )
            await _send_wa(phone, msg)
            to_delete.append(phone)

        # ── Análisis enviado, esperando selección ─────────────────────────────
        elif step == "WAITING_SUBJECT" and not state.get("followup_sent") and timed_out:
            name = state.get("student_name", "")
            first = name.split()[0] if name else "estudiante"
            msg = (
                f"Psst, {first}... ¿sigues ahí? 👀\n\n"
                "¿Hay algo más en lo que te pueda ayudar?\n\n"
                "Escribe el *número* de otra materia para analizarla, "
                "o *0* si ya terminaste. ¡Aquí estoy!"
            )
            await _send_wa(phone, msg)
            _sessions[phone]["followup_sent"] = True
            _sessions[phone]["step"] = "WAITING_FOLLOWUP"
            _sessions[phone]["last_bot_at"] = now

        # ── Sin respuesta al seguimiento ──────────────────────────────────────
        elif step in ("WAITING_FOLLOWUP", "WAITING_THANKS_RESPONSE") and timed_out:
            name = state.get("student_name", "")
            first = name.split()[0] if name else "estudiante"
            msg = (
                f"Entiendo, {first} — parece que ya no estás por aquí. 😊\n\n"
                "Fue un gusto acompañarte hoy! 🎓\n\n"
                "Recuerda que puedes escribirme *hola* en cualquier momento "
                "para revisar tu progreso. ¡Mucho éxito en tu semestre! 💪"
            )
            await _send_wa(phone, msg)
            to_delete.append(phone)

    for phone in to_delete:
        _sessions.pop(phone, None)


async def _send_wa(phone: str, text: str) -> None:
    """Envía un mensaje de WhatsApp directamente (uso interno del timeout).

    `phone` puede ser un JID completo (e.g. '573126226684@c.us') o un número
    puro (e.g. '3126226684'). Se normaliza igual que en el webhook.
    """
    try:
        # Si ya es un JID completo, usarlo tal cual; si no, construirlo
        if "@" in phone:
            chat_id = phone
        else:
            numero = phone.strip().replace(" ", "").replace("-", "").replace("+", "")
            if not numero.startswith("57") and len(numero) == 10:
                numero = f"57{numero}"
            chat_id = f"{numero}@c.us"

        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"{settings.WAHA_URL.rstrip('/')}/api/sendText",
                json={"chatId": chat_id, "text": text, "session": "default"},
                headers={"X-Api-Key": settings.WAHA_API_KEY},
            )
    except Exception as exc:
        logger.warning("[chatbot-timeout] WhatsApp falló → %s: %s", phone, exc)


# ─── Utilidades puras ─────────────────────────────────────────────────────────

_THANKS_PREFIXES = ("gracias", "muchas gracias", "mil gracias", "ok gracias",
                    "grax", "grasias", "thank you", "thanks")

_GREETING_WORDS = {
    "hola", "hi", "hey", "hello", "inicio", "start", "buenas",
    "oe", "oye", "epa", "epale", "quiubo", "quiubole", "buen",
    "saludos", "saludo", "qué más", "que mas", "q mas", "alo",
}
_GREETING_PREFIXES = (
    "buenos días", "buenas tardes", "buenas noches", "buen día",
    "buenos dias", "buenas tarde", "buenas noche", "buen dia",
    "hola ", "hola,", "hola!", "hey ", "hi ", "buenos ",
    "buenas ", "qué más", "que más",
)

_FAREWELL_WORDS = {
    "chao", "bye", "adios", "adiós", "ciao", "hasta luego",
    "hasta pronto", "nos vemos", "hasta mañana", "hasta manana",
    "hasta otra", "cuídate", "cuídate mucho",
}


def _is_greeting(text: str) -> bool:
    """Devuelve True si el texto es un saludo."""
    t = text.lower().strip().rstrip("!.,¡¿").strip()
    if t in _GREETING_WORDS:
        return True
    return any(t.startswith(p) for p in _GREETING_PREFIXES)


def _is_farewell(text: str) -> bool:
    """Devuelve True si el texto es una despedida."""
    t = text.lower().strip().rstrip("!.,").strip()
    return t in _FAREWELL_WORDS or any(t.startswith(w) for w in _FAREWELL_WORDS)


def _looks_like_document(text: str) -> bool:
    """Devuelve True si el texto parece un número de documento (solo dígitos, 5-12 chars)."""
    cleaned = text.strip().replace(" ", "").replace("-", "")
    return cleaned.isdigit() and 5 <= len(cleaned) <= 12


def _is_thanks(text: str) -> bool:
    """Devuelve True si el texto es una expresión de agradecimiento."""
    t = text.lower().strip().rstrip("!").strip()
    return any(t == p or t.startswith(p) for p in _THANKS_PREFIXES)


def _to_float(value) -> Optional[float]:
    return float(value) if value is not None else None


def _recommendation(nivel: str) -> str:
    if nivel == "ALTO":
        return (
            "🚨 *Recomendación:* Necesitas atención inmediata en esta materia. "
            "Te sugerimos buscar asesoría académica cuanto antes. ¡Tú puedes revertir esto!"
        )
    if nivel == "MEDIO":
        return (
            "💪 *Recomendación:* Estás a tiempo de mejorar. "
            "Prioriza los temas con menor calificación y no dudes en pedir ayuda."
        )
    return (
        "🌟 *Recomendación:* ¡Vas excelente! Mantén el ritmo de estudio "
        "y sigue así de comprometido con tu aprendizaje."
    )


def _available_grades(enroll: dict) -> List[str]:
    parts = []
    if enroll["first_cohort_grade"] is not None:
        parts.append(f"Corte 1: {enroll['first_cohort_grade']:.2f}")
    if enroll["second_cohort_grade"] is not None:
        parts.append(f"Corte 2: {enroll['second_cohort_grade']:.2f}")
    if enroll["third_cohort_grade"] is not None:
        parts.append(f"Corte Final: {enroll['third_cohort_grade']:.2f}")
    if enroll["final_grade"] is not None:
        parts.append(f"Total: {enroll['final_grade']:.2f}")
    return parts
