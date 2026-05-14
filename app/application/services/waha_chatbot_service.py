"""
Servicio de chatbot para WhatsApp via WAHA.
Gestiona el flujo conversacional: documento → materias inscritas → análisis de riesgo.
Estado por número de teléfono almacenado en memoria (in-process).
"""

from __future__ import annotations

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

# Estado de conversación por número de teléfono: phone -> session dict
_sessions: Dict[str, dict] = {}


class WahaChatbotService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def handle_message(self, phone: str, text: str) -> str:
        state = _sessions.get(phone, {"step": "WAITING_DOCUMENT"})
        step = state.get("step", "WAITING_DOCUMENT")

        text = text.strip()

        # Comandos globales de reinicio
        if text.lower() in ("0", "reiniciar", "reset", "inicio", "start", "hola", "hi"):
            _sessions.pop(phone, None)
            return self._greeting()

        if step == "WAITING_DOCUMENT":
            return await self._handle_document(phone, text)
        if step == "WAITING_SUBJECT":
            return await self._handle_subject_selection(phone, text, state)

        _sessions.pop(phone, None)
        return self._greeting()

    # ─── Paso 1: recibir número de documento ───────────────────────────────────

    async def _handle_document(self, phone: str, doc_number: str) -> str:
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
                f"Hola *{student_name}*! 👋\n\n"
                "No tienes materias *activas* inscritas en este momento."
            )

        _sessions[phone] = {
            "step": "WAITING_SUBJECT",
            "student_id": str(profile.user_id),
            "student_name": student_name,
            "document_number": doc_number,
            "enrollments": enrollments,
        }

        return self._build_subject_menu(student_name, enrollments)

    # ─── Paso 2: seleccionar materia y generar análisis ────────────────────────

    async def _handle_subject_selection(
        self, phone: str, text: str, state: dict
    ) -> str:
        enrollments: List[dict] = state.get("enrollments", [])
        student_name: str = state.get("student_name", "")

        try:
            selection = int(text)
        except ValueError:
            return (
                "Por favor responde con el *número* de la materia que deseas analizar.\n"
                "Ejemplo: *1*\n\n"
                "Escribe *0* para analizar otro estudiante."
            )

        if selection < 1 or selection > len(enrollments):
            return (
                f"Selección inválida. Elige un número entre *1* y *{len(enrollments)}*.\n"
                "Escribe *0* para reiniciar."
            )

        enroll = enrollments[selection - 1]
        analysis = await self._run_prediction(enroll, student_name)

        footer = (
            "\n\n---\n"
            "Puedes elegir otra materia escribiendo su número.\n"
            "Escribe *0* para analizar otro estudiante."
        )
        return analysis + footer

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
            f"Estudiante: {student_name}",
            f"Materia: *{name}* ({code}) — {period}",
            "",
        ]

        if c1 is not None and c2 is not None and c3 is not None and final is not None:
            predict_url = f"{settings.get_public_base_url()}/api/v1/predict"
            payload = {
                "nota_corte_1": c1,
                "nota_corte_2": c2,
                "nota_corte_final": c3,
                "nota_total": final,
            }
            print(f"[WAHA] Llamando predicción: POST {predict_url}", flush=True)
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(predict_url, json=payload)
                response.raise_for_status()
                result = response.json()

            prob = result["probabilidad_riesgo"]
            nivel = result["nivel_riesgo"]
            emoji = "🔴" if nivel == "ALTO" else "🟡" if nivel == "MEDIO" else "🟢"

            lines += [
                f"{emoji} *Riesgo: {nivel}*",
                f"Probabilidad de reprobar: *{prob * 100:.1f}%*",
                "",
                f"Corte 1: {c1:.2f}  |  Corte 2: {c2:.2f}  |  Corte Final: {c3:.2f}  |  Total: {final:.2f}",
                "",
                _recommendation(nivel),
            ]

        else:
            lines.append("ℹ️ Aún no hay calificaciones completas registradas para esta materia.")
            available = _available_grades(enroll)
            if available:
                lines.append("Notas disponibles: " + "  |  ".join(available))

        return "\n".join(lines)

    # ─── Helpers de UI ────────────────────────────────────────────────────────

    @staticmethod
    def _greeting() -> str:
        return (
            "👋 Hola! Soy el asistente de *Riesgo Académico*.\n\n"
            "Por favor, ingresa tu *número de documento* de identidad "
            "(cédula, TI, etc.) para comenzar el análisis."
        )

    @staticmethod
    def _build_subject_menu(student_name: str, enrollments: List[dict]) -> str:
        lines = [
            f"Hola *{student_name}*! 👋",
            "",
            "Tus materias activas inscritas:",
            "",
        ]
        for i, e in enumerate(enrollments, 1):
            lines.append(f"  *{i}.* {e['subject_name']} ({e['subject_code']})")
        lines += [
            "",
            "Responde con el *número* de la materia que deseas analizar.",
            "Escribe *0* para reiniciar.",
        ]
        return "\n".join(lines)


# ─── Utilidades puras ─────────────────────────────────────────────────────────

def _to_float(value) -> Optional[float]:
    return float(value) if value is not None else None


def _recommendation(nivel: str) -> str:
    if nivel == "ALTO":
        return "⚠️ Necesitas intervención inmediata. Busca asesoría académica cuanto antes."
    if nivel == "MEDIO":
        return "💡 Estás a tiempo de mejorar. Prioriza los temas con menor calificación."
    return "✅ Vas en buen camino. Mantén el ritmo de estudio."


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
