"""
GradeService — consulta de notas y extracción de features para predicción de riesgo.
"""

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.schemas.enrollment import GradesRead
from app.domain.enums import RoleEnum
from app.domain.interfaces.enrollment_repository import IEnrollmentRepository
from app.infrastructure.models.course import Course


COHORT_KEYS = ("first_cohort", "second_cohort", "third_cohort")


def _parse_weight(weight_str: str | None) -> float:
    if not weight_str:
        return 0.0
    try:
        return float(str(weight_str).replace("%", "")) / 100
    except (ValueError, TypeError):
        return 0.0


def _calculate_cohort_grade(cohort_data: dict) -> float | None:
    total_weight = 0.0
    weighted_sum = 0.0

    parcial = cohort_data.get("parcial", {})
    if isinstance(parcial, dict) and parcial.get("note") is not None:
        w = _parse_weight(parcial.get("weight"))
        weighted_sum += float(parcial["note"]) * w
        total_weight += w

    seguimiento = cohort_data.get("seguimiento", {})
    for activity in seguimiento.values():
        if not isinstance(activity, dict) or activity.get("note") is None:
            continue
        w = _parse_weight(activity.get("weight"))
        weighted_sum += float(activity["note"]) * w
        total_weight += w

    if total_weight == 0:
        return None
    return round(weighted_sum / total_weight, 2)


def _calculate_final_grade(grades: dict) -> float | None:
    total_weight = 0.0
    weighted_sum = 0.0

    for cohort_key in ("first_cohort", "second_cohort", "third_cohort"):
        cohort = grades.get(cohort_key, {})
        cohort_grade = _calculate_cohort_grade(cohort)
        if cohort_grade is None:
            continue
        w = _parse_weight(cohort.get("weight"))
        weighted_sum += cohort_grade * w
        total_weight += w

    if total_weight == 0:
        return None
    return round(weighted_sum / total_weight, 2)


class GradeService:
    def __init__(self, repo: IEnrollmentRepository, session: AsyncSession) -> None:
        self._repo = repo
        self._session = session

    async def get_grades(self, enrollment_id: UUID, current_user: object) -> GradesRead:
        """Retorna las notas de una inscripción. Verifica acceso por rol."""
        enrollment = await self._repo.get_by_id(enrollment_id)
        if enrollment is None:
            raise HTTPException(status_code=404, detail="Inscripción no encontrada")
        await self._check_access(enrollment, current_user)
        return GradesRead.model_validate(enrollment)

    async def set_grades(self, enrollment_id: UUID, grades: dict, current_user: object) -> GradesRead:
        """Registra o reemplaza las notas de una inscripción y recalcula columnas calculadas."""
        enrollment = await self._repo.get_by_id(enrollment_id)
        if enrollment is None:
            raise HTTPException(status_code=404, detail="Inscripción no encontrada")
        await self._check_write_access(enrollment, current_user)

        updated = await self._repo.update_grades(
            enrollment_id,
            grades,
            _calculate_cohort_grade(grades.get("first_cohort", {})),
            _calculate_cohort_grade(grades.get("second_cohort", {})),
            _calculate_cohort_grade(grades.get("third_cohort", {})),
            _calculate_final_grade(grades),
            current_user.id,
        )
        return GradesRead.model_validate(updated)

    async def get_course_grades_structure(
        self, course_id: UUID, current_user: object
    ) -> dict | None:
        """Retorna el JSON grades de la primera inscripción encontrada del curso."""
        course = await self._get_course(course_id)
        await self._check_course_access(course, current_user)

        enrollments = await self._repo.list_by_course(course_id)
        for enrollment in enrollments:
            if enrollment.grades:
                return enrollment.grades
        return None

    async def set_course_grades_structure(
        self, course_id: UUID, grades: dict, current_user: object
    ) -> int:
        """
        Aplica la estructura JSON de notas a todas las inscripciones del curso.
        Guarda el JSON completo en enrollments.grades y recalcula columnas derivadas.
        """
        course = await self._get_course(course_id)
        await self._check_course_write_access(course, current_user)

        enrollments = await self._repo.list_by_course(course_id)
        updated = 0
        for enrollment in enrollments:
            result = await self._repo.update_grades(
                enrollment.id,
                grades,
                _calculate_cohort_grade(grades.get("first_cohort", {})),
                _calculate_cohort_grade(grades.get("second_cohort", {})),
                _calculate_cohort_grade(grades.get("third_cohort", {})),
                _calculate_final_grade(grades),
                current_user.id,
            )
            if result is not None:
                updated += 1
        return updated

    async def _get_course(self, course_id: UUID) -> Course:
        result = await self._session.execute(
            select(Course).where(Course.id == course_id)
        )
        course = result.scalar_one_or_none()
        if course is None:
            raise HTTPException(status_code=404, detail="Curso no encontrado")
        return course

    async def _check_course_access(self, course: Course, current_user: object) -> None:
        if current_user.role == RoleEnum.ADMIN:
            return
        if current_user.role == RoleEnum.PROFESSOR and course.professor_id == current_user.id:
            return
        raise HTTPException(status_code=403, detail="No tiene permisos para esta acción")

    async def _check_course_write_access(self, course: Course, current_user: object) -> None:
        if current_user.role == RoleEnum.ADMIN:
            return
        if current_user.role == RoleEnum.PROFESSOR and course.professor_id == current_user.id:
            return
        raise HTTPException(
            status_code=403,
            detail="Solo profesores y administradores pueden registrar esta configuración",
        )

    async def _check_access(self, enrollment: object, current_user: object) -> None:
        if current_user.role == RoleEnum.ADMIN:
            return

        if current_user.role == RoleEnum.STUDENT:
            if enrollment.student_id == current_user.id:
                return
            raise HTTPException(status_code=403, detail="No tiene permisos para esta acción")

        if current_user.role == RoleEnum.PROFESSOR:
            result = await self._session.execute(
                select(Course).where(Course.id == enrollment.course_id)
            )
            course = result.scalar_one_or_none()
            if course and course.professor_id == current_user.id:
                return
            raise HTTPException(status_code=403, detail="No tiene permisos para esta acción")

        raise HTTPException(status_code=403, detail="No tiene permisos para esta acción")

    async def _check_write_access(self, enrollment: object, current_user: object) -> None:
        if current_user.role == RoleEnum.ADMIN:
            return

        if current_user.role == RoleEnum.PROFESSOR:
            result = await self._session.execute(
                select(Course).where(Course.id == enrollment.course_id)
            )
            course = result.scalar_one_or_none()
            if course and course.professor_id == current_user.id:
                return
            raise HTTPException(status_code=403, detail="No tiene permisos para esta acción")

        raise HTTPException(
            status_code=403,
            detail="Solo profesores y administradores pueden registrar notas",
        )


# ---------------------------------------------------------------------------
# Helpers de extracción de features desde el JSON de notas
# ---------------------------------------------------------------------------

def extract_nota_parcial_1(grades: dict) -> float:
    """Extrae la nota del parcial del primer cohorte."""
    try:
        note = grades["first_cohort"]["parcial"]["note"]
    except (KeyError, TypeError):
        raise HTTPException(
            status_code=422,
            detail="La nota del parcial del primer cohorte no está registrada",
        )
    return float(note)


def extract_promedio_seguimiento(grades: dict) -> float:
    """Promedio ponderado de todas las actividades de seguimiento en los 3 cohortes.

    Se normalizan los pesos al total encontrado para que la escala sea 0–5
    incluso si el profesor no completó todos los pesos.
    """
    cohort_keys = ["first_cohort", "second_cohort", "third_cohort"]
    weighted_sum = 0.0
    total_weight = 0.0

    for cohort_key in cohort_keys:
        cohort = grades.get(cohort_key, {})
        seguimiento = cohort.get("seguimiento", {})
        for activity in seguimiento.values():
            if not isinstance(activity, dict):
                continue
            note = activity.get("note")
            weight_str = activity.get("weight", "0%")
            if note is None:
                continue
            try:
                weight = float(str(weight_str).replace("%", "")) / 100
            except ValueError:
                continue
            weighted_sum += float(note) * weight
            total_weight += weight

    if total_weight == 0:
        raise HTTPException(
            status_code=422,
            detail="No hay actividades de seguimiento con notas registradas",
        )

    return round(weighted_sum / total_weight, 2)


def extract_cohort_parcial(grades: dict, cohort_key: str) -> float:
    """Extrae nota del parcial de un cohorte específico."""
    if cohort_key not in COHORT_KEYS:
        raise HTTPException(status_code=422, detail="Cohorte inválido")
    try:
        note = grades[cohort_key]["parcial"]["note"]
    except (KeyError, TypeError):
        raise HTTPException(
            status_code=422,
            detail=f"La nota parcial de {cohort_key} no está registrada",
        )
    if note is None:
        raise HTTPException(
            status_code=422,
            detail=f"La nota parcial de {cohort_key} no está registrada",
        )
    return float(note)


def extract_cohort_seguimiento(grades: dict, cohort_key: str) -> float:
    """Promedio ponderado de seguimiento en un cohorte específico."""
    if cohort_key not in COHORT_KEYS:
        raise HTTPException(status_code=422, detail="Cohorte inválido")

    cohort = grades.get(cohort_key, {})
    seguimiento = cohort.get("seguimiento", {})
    weighted_sum = 0.0
    total_weight = 0.0

    for activity in seguimiento.values():
        if not isinstance(activity, dict):
            continue
        note = activity.get("note")
        if note is None:
            continue
        weight = _parse_weight(activity.get("weight"))
        weighted_sum += float(note) * weight
        total_weight += weight

    if total_weight == 0:
        raise HTTPException(
            status_code=422,
            detail=f"No hay actividades de seguimiento con nota en {cohort_key}",
        )
    return round(weighted_sum / total_weight, 2)


def extract_cohort_attendance_percentage(grades: dict, cohort_key: str) -> float:
    """Calcula porcentaje de asistencia de un cohorte.

    Formatos soportados:
    - attendance JSONB: {"assist": int, "not_asist": int}
    - Campo legacy porcentual: attendance_percentage / porcentaje_asistencia
    """
    if cohort_key not in COHORT_KEYS:
        raise HTTPException(status_code=422, detail="Cohorte inválido")

    cohort = grades.get(cohort_key, {})

    # 1) Formato nuevo: contador attendance JSONB
    attendance = cohort.get("attendance", {})
    if isinstance(attendance, dict):
        try:
            assist = int(attendance.get("assist", 0))
            not_asist = int(attendance.get("not_asist", 0))
            total = assist + not_asist
            if total > 0:
                return round((assist / total) * 100, 2)
        except (TypeError, ValueError):
            pass

    # 2) Formatos legacy: porcentaje ya calculado
    for key in ("attendance_percentage", "porcentaje_asistencia"):
        value = cohort.get(key)
        if value is None:
            continue
        try:
            pct = float(value)
            return round(max(0.0, min(100.0, pct)), 2)
        except (TypeError, ValueError):
            continue

    raise HTTPException(
        status_code=422,
        detail=f"No hay datos de asistencia para {cohort_key}",
    )
