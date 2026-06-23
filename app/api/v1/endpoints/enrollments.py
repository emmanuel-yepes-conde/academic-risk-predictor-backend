"""
EnrollmentRouter — endpoints CRUD para inscripciones de estudiantes en cursos.
Requisitos: 1.1, 1.9, 2.1, 2.7, 3.1, 3.4, 4.1, 4.3, 5.1, 5.3
"""

from decimal import Decimal
from uuid import UUID

import asyncio
import logging
import numpy as np
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query

logger = logging.getLogger(__name__)
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.schemas.enrollment import (
    CourseGradesStructureRead,
    EnrollmentCreate,
    EnrollmentRead,
    EnrollmentStatusUpdate,
    EnrollmentUpdate,
    GradesRead,
    GradesUpdate,
    RiskFromEnrollmentRequest,
)
from app.application.schemas.user import PaginatedResponse
from app.application.services.enrollment_service import EnrollmentService
from app.application.services.grade_service import (
    GradeService,
    extract_cohort_attendance_percentage,
    extract_cohort_parcial,
    extract_cohort_seguimiento,
)
from app.application.services.ml_service import MLApplicationService
from app.application.services.consent_service import ConsentService
from app.api.v1.dependencies.auth import (
    CurrentUser,
    get_current_user,
    require_roles,
    require_student_self_or_roles,
)
from app.domain.enums import EnrollmentStatusEnum, RoleEnum
from app.infrastructure.database import get_session
from app.infrastructure.repositories.consent_repository import ConsentRepository
from app.infrastructure.repositories.enrollment_repository import EnrollmentRepository
from app.infrastructure.models.student_profile import StudentProfile
from app.schemas.student import CohortRiskOutput, PredictionOutput
from app.services.ml_service import AcademicRiskService, get_risk_service


class StudentProfileRead(BaseModel):
    semester:         int     | None
    academic_year:    int     | None
    enrolled_credits: Decimal | None

    model_config = {"from_attributes": True}

router = APIRouter()


# ---------------------------------------------------------------------------
# Dependency helpers
# ---------------------------------------------------------------------------

def _get_enrollment_service(
    session: AsyncSession = Depends(get_session),
) -> EnrollmentService:
    repo = EnrollmentRepository(session)
    return EnrollmentService(repo, session)


def _get_grade_service(
    session: AsyncSession = Depends(get_session),
) -> GradeService:
    repo = EnrollmentRepository(session)
    return GradeService(repo, session)


def _get_ml_service() -> AcademicRiskService:
    return get_risk_service()


def _get_ml_app_service(
    session: AsyncSession = Depends(get_session),
    ml: AcademicRiskService = Depends(_get_ml_service),
) -> MLApplicationService:
    consent_repo = ConsentRepository(session)
    return MLApplicationService(ml, ConsentService(consent_repo))


# ===========================================================================
# CRUD endpoints
# ===========================================================================

@router.post(
    "/enrollments",
    response_model=EnrollmentRead,
    status_code=201,
    summary="Inscribir un estudiante en un curso",
    description=(
        "Crea una nueva inscripción para un estudiante en un curso. "
        "Si ya existe una inscripción cancelada para la misma combinación "
        "(student_id, course_id), se reactiva en lugar de crear una nueva. "
        "Requiere rol ADMIN."
    ),
    tags=["Inscripciones"],
)
async def create_enrollment(
    body: EnrollmentCreate,
    current_user: CurrentUser = Depends(require_roles(RoleEnum.ADMIN)),
    service: EnrollmentService = Depends(_get_enrollment_service),
) -> EnrollmentRead:
    return await service.create_enrollment(body, current_user.id)


@router.patch(
    "/enrollments/{enrollment_id}",
    response_model=EnrollmentRead,
    status_code=200,
    summary="Actualizar inscripción (cambio de curso)",
    description=(
        "Actualiza el curso de una inscripción existente. "
        "Valida que el curso destino exista, esté activo y que no exista "
        "una inscripción activa duplicada en el curso destino. "
        "Requiere rol ADMIN."
    ),
    tags=["Inscripciones"],
)
async def update_enrollment(
    enrollment_id: UUID,
    body: EnrollmentUpdate,
    current_user: CurrentUser = Depends(require_roles(RoleEnum.ADMIN)),
    service: EnrollmentService = Depends(_get_enrollment_service),
) -> EnrollmentRead:
    return await service.update_enrollment(enrollment_id, body, current_user.id)


@router.patch(
    "/enrollments/{enrollment_id}/status",
    response_model=EnrollmentRead,
    status_code=200,
    summary="Actualizar estado de inscripción",
    description=(
        "Actualiza el estado de una inscripción a cualquier estado válido: "
        "PENDING, ACTIVE, COMPLETED o CANCELLED. "
        "El registro se preserva en la base de datos con el campo status actualizado. "
        "Requiere rol ADMIN."
    ),
    tags=["Inscripciones"],
)
async def update_enrollment_status(
    enrollment_id: UUID,
    body: EnrollmentStatusUpdate,
    current_user: CurrentUser = Depends(require_roles(RoleEnum.ADMIN)),
    service: EnrollmentService = Depends(_get_enrollment_service),
) -> EnrollmentRead:
    return await service.update_enrollment_status(enrollment_id, body, current_user.id)


@router.get(
    "/enrollments/{enrollment_id}",
    response_model=EnrollmentRead,
    status_code=200,
    summary="Obtener detalle de una inscripción",
    description=(
        "Retorna los datos completos de una inscripción específica. "
        "Retorna 404 si la inscripción no existe. "
        "Requiere rol ADMIN."
    ),
    tags=["Inscripciones"],
)
async def get_enrollment(
    enrollment_id: UUID,
    current_user: CurrentUser = Depends(require_roles(RoleEnum.ADMIN)),
    service: EnrollmentService = Depends(_get_enrollment_service),
) -> EnrollmentRead:
    return await service.get_enrollment(enrollment_id)


@router.get(
    "/students/{student_id}/profile",
    response_model=StudentProfileRead,
    status_code=200,
    summary="Perfil académico de un estudiante",
    description=(
        "Retorna datos del perfil académico del estudiante (semestre, año académico, "
        "créditos matriculados). Retorna 404 si no existe perfil. "
        "STUDENT: solo su propio perfil. ADMIN/PROFESSOR: acceso amplio."
    ),
    tags=["Inscripciones"],
)
async def get_student_profile(
    student_id: UUID,
    current_user: CurrentUser = Depends(require_student_self_or_roles),
    session: AsyncSession = Depends(get_session),
) -> StudentProfileRead:
    result = await session.execute(
        select(StudentProfile).where(StudentProfile.user_id == student_id)
    )
    profile = result.scalar_one_or_none()
    if profile is None:
        raise HTTPException(status_code=404, detail="Perfil académico no encontrado")
    return StudentProfileRead.model_validate(profile)


@router.get(
    "/students/{student_id}/enrollments",
    response_model=PaginatedResponse[EnrollmentRead],
    status_code=200,
    summary="Listar inscripciones de un estudiante",
    description=(
        "Retorna la lista de inscripciones de un estudiante. "
        "Si el usuario autenticado es STUDENT, permite auto-acceso a sus propias inscripciones "
        "(retorna todos los estados para la vista de progreso). "
        "Si el usuario autenticado es PROFESSOR, solo retorna inscripciones "
        "en cursos asignados al profesor (RB-04). "
        "Acepta un query param opcional `status` para filtrar por estado de inscripción. "
        "Requiere rol STUDENT (auto-acceso), ADMIN o PROFESSOR."
    ),
    tags=["Inscripciones"],
)
async def list_student_enrollments(
    student_id: UUID,
    status: EnrollmentStatusEnum | None = Query(
        default=None, description="Filtrar por estado de inscripción"
    ),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: CurrentUser = Depends(require_student_self_or_roles),
    service: EnrollmentService = Depends(_get_enrollment_service),
) -> PaginatedResponse[EnrollmentRead]:
    return await service.list_student_enrollments(
        student_id, current_user, status, skip=skip, limit=limit
    )


# ===========================================================================
# Grades & Risk endpoints
# ===========================================================================

@router.get(
    "/courses/{course_id}/grades-structure",
    response_model=CourseGradesStructureRead,
    status_code=200,
    summary="Consultar estructura JSON de notas de un curso",
    description=(
        "Retorna la estructura completa del JSON de notas (grades) tomada de una "
        "inscripción del curso. Se usa para persistir y restaurar la distribución "
        "de cortes/actividades en frontend."
    ),
    tags=["Inscripciones"],
)
async def get_course_grades_structure(
    course_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: GradeService = Depends(_get_grade_service),
) -> CourseGradesStructureRead:
    grades = await service.get_course_grades_structure(course_id, current_user)
    return CourseGradesStructureRead(course_id=course_id, grades=grades)


@router.put(
    "/courses/{course_id}/grades-structure",
    response_model=CourseGradesStructureRead,
    status_code=200,
    summary="Guardar estructura JSON de notas en inscripciones del curso",
    description=(
        "Guarda la estructura completa del JSON de notas (grades) en la tabla "
        "`enrollments` para todas las inscripciones del curso."
    ),
    tags=["Inscripciones"],
)
async def set_course_grades_structure(
    course_id: UUID,
    body: GradesUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    service: GradeService = Depends(_get_grade_service),
) -> CourseGradesStructureRead:
    await service.set_course_grades_structure(course_id, body.grades, current_user)
    return CourseGradesStructureRead(course_id=course_id, grades=body.grades)

@router.get(
    "/enrollments/{enrollment_id}/grades",
    response_model=GradesRead,
    status_code=200,
    summary="Consultar notas de una inscripción",
    description=(
        "Retorna las notas registradas para una inscripción junto con las notas "
        "calculadas por cohorte y la nota final. "
        "STUDENT: solo puede consultar sus propias inscripciones. "
        "PROFESSOR: solo puede consultar inscripciones en sus cursos (RB-04). "
        "ADMIN: acceso total."
    ),
    tags=["Inscripciones"],
)
async def get_enrollment_grades(
    enrollment_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: GradeService = Depends(_get_grade_service),
) -> GradesRead:
    return await service.get_grades(enrollment_id, current_user)


async def _send_wa_text(phone: str, text: str) -> None:
    """Envía un mensaje de texto plano por WhatsApp (helper interno)."""
    from app.core.config import settings
    import httpx
    if not settings.WAHA_URL:
        logger.warning("[WhatsApp] WAHA_URL no configurado — omitiendo mensaje")
        return
    numero = phone.strip().replace(" ", "").replace("-", "").replace("+", "")
    if not numero.startswith("57") and len(numero) == 10:
        numero = f"57{numero}"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{settings.WAHA_URL.rstrip('/')}/api/sendText",
                json={"session": "default", "chatId": f"{numero}@c.us", "text": text},
                headers={"X-Api-Key": settings.WAHA_API_KEY},
            )
        if resp.status_code >= 400:
            logger.warning("[WhatsApp] sendText falló → %s %s", resp.status_code, resp.text[:120])
        else:
            logger.info("[WhatsApp] Mensaje enviado → %s@c.us", numero)
    except Exception as exc:
        logger.error("[WhatsApp] Excepcion enviando mensaje: %s", exc)


async def _send_whatsapp_risk_alert(
    phone: str,
    student_name: str,
    course_name: str,
    risk_pct: float,
    nivel: str,
    analisis: str,
    course_id: str,
) -> None:
    """Envía el análisis natural de riesgo por WhatsApp al estudiante."""
    from app.core.config import settings
    import httpx

    if not settings.WAHA_URL:
        logger.warning("[WhatsApp] WAHA_URL no configurado — omitiendo alerta de riesgo")
        return

    # Normalizar número: quitar +, espacios, guiones → agregar código Colombia si falta
    numero = phone.strip().replace(" ", "").replace("-", "").replace("+", "")
    if not numero.startswith("57") and len(numero) == 10:
        numero = f"57{numero}"
    chat_id = f"{numero}@c.us"

    nombre      = student_name or "Estudiante"
    primer      = nombre.split()[0]
    nivel_emoji = {"ALTO": "🔴", "MEDIO": "🟡", "BAJO": "🟢"}.get(nivel, "📊")
    nivel_texto = {"ALTO": "ALTO", "MEDIO": "MEDIO", "BAJO": "BAJO"}.get(nivel, nivel)

    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo
    _col = datetime.now(timezone.utc).astimezone(ZoneInfo("America/Bogota"))
    _dias   = ["Lunes","Martes","Miércoles","Jueves","Viernes","Sábado","Domingo"]
    _meses  = ["Enero","Febrero","Marzo","Abril","Mayo","Junio",
               "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"]
    fecha_hora = (f"{_dias[_col.weekday()]} {_col.day} de {_meses[_col.month-1]} "
                  f"de {_col.year}, {_col.strftime('%I:%M %p').lower()}")

    frontend_url = settings.FRONTEND_URL.rstrip("/")
    texto = (
        f"{nivel_emoji} *Predicción de riesgo académico*\n\n"
        f"Hola {primer}! Risko analizó tu rendimiento en *{course_name}*.\n\n"
        f"📊 *Nivel de riesgo:* {nivel_texto} ({risk_pct:.0f}%)\n\n"
        f"{analisis}\n\n"
        f"🕐 *Calculado el:* {fecha_hora}\n\n"
        f"Para ver el análisis completo y tu simulador, ingresa a la plataforma 👉 {frontend_url}"
    )

    url = f"{settings.WAHA_URL.rstrip('/')}/api/sendText"
    payload = {"session": "default", "chatId": chat_id, "text": texto}
    headers = {"X-Api-Key": settings.WAHA_API_KEY}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code >= 400:
            logger.warning(f"[WhatsApp] Error enviando alerta de riesgo: {resp.status_code} {resp.text[:120]}")
        else:
            logger.info(f"[WhatsApp] Analisis de riesgo enviado → {chat_id}")
    except Exception as exc:
        logger.error(f"[WhatsApp] Excepcion al enviar alerta: {exc}")


async def _notify_student_prediction_result(
    enrollment_id: UUID,
    nivel_riesgo: str,
    probability: float,
    analisis_ia: str,
) -> None:
    """
    Background task: al calcular la predicción manualmente desde la plataforma,
    notifica al estudiante por push + WhatsApp + in-app para TODOS los niveles de riesgo.
    - ALTO:  mensaje de alerta urgente
    - MEDIO: mensaje de precaución
    - BAJO:  mensaje de confirmación positiva
    """
    try:
        from app.core.config import settings
        from app.infrastructure.database import BackgroundSessionFactory as AsyncSessionFactory
        from app.infrastructure.models.enrollment import Enrollment as EnrollmentModel
        from app.infrastructure.models.course import Course as CourseModel
        from app.infrastructure.models.subject import Subject as SubjectModel
        from app.infrastructure.models.user import User as UserModel
        from app.services.push_notification_service import send_push_to_user
        from app.services.notification_service import notify_by_user_id

        # ── Fase 1: leer datos de BD y guardar notificación in-app ──────────────
        # La sesión se cierra ANTES de enviar email/WhatsApp para evitar
        # el error "Task got Future attached to a different loop" que ocurre
        # cuando asyncio.to_thread (SMTP) corre mientras hay una conexión
        # asyncpg activa en el mismo contexto.
        student_phone  = None
        student_email  = None
        student_name   = ""
        course_name    = "tu materia"
        wa_enabled     = False
        email_enabled  = False
        course_id_str  = ""
        risk_pct       = probability * 100
        primera_linea  = analisis_ia.split("\n\n")[0]

        async with AsyncSessionFactory() as bg_session:
            enroll_q = await bg_session.execute(
                select(EnrollmentModel).where(EnrollmentModel.id == enrollment_id)
            )
            enrollment = enroll_q.scalar_one_or_none()
            if not enrollment:
                logger.warning("[Prediccion] enrollment no encontrado: %s", enrollment_id)
                return

            course_q, user_q = await asyncio.gather(
                bg_session.execute(select(CourseModel).where(CourseModel.id == enrollment.course_id)),
                bg_session.execute(select(UserModel).where(UserModel.id == enrollment.student_id)),
            )
            course  = course_q.scalar_one_or_none()
            student = user_q.scalar_one_or_none()

            if course:
                subj_q = await bg_session.execute(
                    select(SubjectModel).where(SubjectModel.id == course.subject_id)
                )
                subject = subj_q.scalar_one_or_none()
                course_name = subject.name if subject else "tu materia"

            student_name  = student.full_name if student else ""
            student_phone = student.phone if student else None
            wa_enabled    = getattr(student, "whatsapp_enabled", True) if student else False
            email_enabled = getattr(student, "email_enabled", True) if student else False
            student_email = (
                getattr(student, "institutional_email", None) or getattr(student, "email", None)
            ) if student else None
            course_id_str = str(enrollment.course_id)
            student_id    = enrollment.student_id

            # Título y cuerpo in-app
            if nivel_riesgo == "ALTO":
                notif_type = "RISK_ALTO"
                title      = f"[RIESGO ALTO] {course_name}"
                body       = primera_linea or f"Tu riesgo de reprobar es ALTO ({risk_pct:.0f}%). Busca asesoria cuanto antes."
            elif nivel_riesgo == "MEDIO":
                notif_type = "RISK_MEDIO"
                title      = f"[RIESGO MEDIO] {course_name}"
                body       = primera_linea or f"Tu riesgo de reprobar es MEDIO ({risk_pct:.0f}%). Refuerza los temas pendientes."
            else:
                notif_type = "RISK_BAJO"
                title      = f"[RIESGO BAJO] {course_name}"
                body       = f"Riesgo de reprobar: BAJO ({risk_pct:.0f}%). Vas por buen camino, sigue asi."

            url = f"/materia/{course_id_str}"

            # Push (necesita sesión)
            try:
                sent = await send_push_to_user(
                    user_id=str(student_id), title=title, body=body,
                    url=url, session=bg_session,
                )
            except Exception as _push_err:
                logger.warning("[Prediccion] push falló: %s", _push_err)

            # In-app (necesita sesión)
            try:
                await notify_by_user_id(
                    db=bg_session, user_id=student_id, type=notif_type,
                    title=title, body=body,
                    data={"course_id": course_id_str, "url": url, "risk_pct": round(risk_pct, 1)},
                )
            except Exception as _notif_err:
                logger.warning("[Prediccion] in-app notify falló: %s", _notif_err)
        # ── Sesión cerrada — ahora enviamos WhatsApp y email sin conexión DB ──

        # WhatsApp
        primer_nombre = student_name.split()[0] if student_name else "estudiante"
        from datetime import datetime as _dt, timezone as _tz
        from zoneinfo import ZoneInfo as _ZI
        _col = _dt.now(_tz.utc).astimezone(_ZI("America/Bogota"))
        _dias  = ["Lunes","Martes","Miércoles","Jueves","Viernes","Sábado","Domingo"]
        _meses = ["Enero","Febrero","Marzo","Abril","Mayo","Junio",
                  "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"]
        _fecha = (f"{_dias[_col.weekday()]} {_col.day} de {_meses[_col.month-1]} "
                  f"de {_col.year}, {_col.strftime('%I:%M %p').lower()}")
        _frontend = settings.FRONTEND_URL.rstrip("/")

        if student_phone and wa_enabled:
            try:
                if nivel_riesgo == "BAJO":
                    wa_text = (
                        f"🟢 *Predicción de riesgo académico*\n\n"
                        f"Hola {primer_nombre}! Risko analizó tu rendimiento en *{course_name}*.\n\n"
                        f"📊 *Nivel de riesgo:* BAJO ({risk_pct:.0f}%)\n\n"
                        f"Vas por muy buen camino. Sigue con ese ritmo de estudio y esa dedicación! 💪\n\n"
                        f"🕐 *Calculado el:* {_fecha}\n\n"
                        f"Para ver el análisis completo, ingresa a la plataforma 👉 {_frontend}"
                    )
                    await _send_wa_text(student_phone, wa_text)
                else:
                    await _send_whatsapp_risk_alert(
                        phone=student_phone, student_name=student_name,
                        course_name=course_name, risk_pct=risk_pct,
                        nivel=nivel_riesgo, analisis=analisis_ia,
                        course_id=course_id_str,
                    )
                logger.warning("[Prediccion] ✅ WhatsApp enviado → %s (nivel=%s)", student_phone, nivel_riesgo)
            except Exception as _wa_err:
                logger.warning("[Prediccion] ❌ WhatsApp excepción → %s: %s", student_phone, _wa_err)
        else:
            logger.warning(
                "[Prediccion] ⏭️  WhatsApp omitido → phone=%s wa_enabled=%s",
                bool(student_phone), wa_enabled,
            )

        # Email (fuera de la sesión DB — sin riesgo de event loop conflict)
        if email_enabled and student_email:
            try:
                from app.services.notification_service import _send_email as _send_notif_email
                from app.services.acs_email_service import _prediction_result_html
                nivel_emoji   = {"ALTO": "🔴", "MEDIO": "🟡", "BAJO": "🟢"}.get(nivel_riesgo, "📊")
                email_subject = f"{nivel_emoji} Predicción de riesgo académico — {course_name}"
                email_body = (
                    f"Hola {primer_nombre},\n\n"
                    f"Risko analizó tu rendimiento en {course_name} "
                    f"y determinó un nivel de riesgo {nivel_riesgo} ({risk_pct:.0f}%).\n\n"
                    f"Ingresa a Academic Risk para ver el análisis completo."
                )
                # HTML unificado — usa el mismo header/footer que todos los templates
                html_content = _prediction_result_html(
                    student_name=student_name,
                    course_name=course_name,
                    nivel_riesgo=nivel_riesgo,
                    risk_pct=risk_pct,
                    analisis_ia=analisis_ia,
                    frontend_url=settings.FRONTEND_URL.rstrip("/"),
                )
                ok = await _send_notif_email(
                    email=student_email,
                    name=student_name,
                    title=email_subject,
                    body=email_body,
                    html_content=html_content,
                )
                if ok:
                    logger.warning("[Prediccion] ✅ Email enviado → %s (nivel=%s)", student_email, nivel_riesgo)
                else:
                    logger.warning("[Prediccion] ❌ Email falló (sin excepción) → %s", student_email)
            except Exception as _email_err:
                logger.warning("[Prediccion] ❌ Email excepción → %s: %s", student_email, _email_err)
        else:
            logger.warning(
                "[Prediccion] ⏭️  Email omitido → email=%s email_enabled=%s",
                bool(student_email), email_enabled,
            )

    except Exception as exc:
        logger.error("[Prediccion] Error en notificacion de resultado: %s", exc, exc_info=True)


async def _push_risk_alert_if_needed(
    enrollment_id: UUID,
    grades_result: GradesRead,
    ml: AcademicRiskService,
) -> None:
    """
    Background task: si los 3 cortes están completos y el riesgo es ALTO,
    envía push notification al estudiante (sin bloquear la respuesta al profesor).
    """
    # Solo actuar si hay notas completas
    if (
        grades_result.first_cohort_grade is None
        or grades_result.second_cohort_grade is None
        or grades_result.third_cohort_grade is None
        or grades_result.final_grade is None
    ):
        return

    try:
        features = [
            float(grades_result.first_cohort_grade),
            float(grades_result.second_cohort_grade),
            float(grades_result.third_cohort_grade),
            float(grades_result.final_grade),
        ]
        result = ml.predict(features)
        if result["risk_level"] != "ALTO":
            return

        # Generar análisis natural ANTES de abrir la sesión BD
        datos_estudiante = {
            "nota_corte_1":    float(grades_result.first_cohort_grade),
            "nota_corte_2":    float(grades_result.second_cohort_grade),
            "nota_corte_final": float(grades_result.third_cohort_grade),
            "nota_total":      float(grades_result.final_grade),
        }
        analisis_completo = ml.generar_analisis_ia(datos_estudiante, result["probability"])
        # Primera línea del análisis para el cuerpo del push (corto)
        primera_linea = analisis_completo.split("\n\n")[0]

        # Abrir sesión propia para el background task
        from app.infrastructure.database import BackgroundSessionFactory as AsyncSessionFactory
        from app.infrastructure.models.enrollment import Enrollment as EnrollmentModel
        from app.infrastructure.models.course import Course as CourseModel
        from app.infrastructure.models.user import User as UserModel
        from app.services.push_notification_service import (
            send_push_to_user, build_risk_alert_message,
        )

        async with AsyncSessionFactory() as bg_session:
            # Obtener enrollment para conocer student_id y course_id
            enroll_q = await bg_session.execute(
                select(EnrollmentModel).where(EnrollmentModel.id == enrollment_id)
            )
            enrollment = enroll_q.scalar_one_or_none()
            if not enrollment:
                return

            # Obtener curso y estudiante en paralelo
            course_q, user_q = await asyncio.gather(
                bg_session.execute(
                    select(CourseModel).where(CourseModel.id == enrollment.course_id)
                ),
                bg_session.execute(
                    select(UserModel).where(UserModel.id == enrollment.student_id)
                ),
            )
            course  = course_q.scalar_one_or_none()
            student = user_q.scalar_one_or_none()

            course_name   = course.name if course else "tu materia"
            student_name  = student.full_name if student else ""
            student_phone = student.phone if student else None

            # ── Push notification (body = primera línea del análisis) ──────────
            msg = build_risk_alert_message(
                student_name=student_name,
                course_name=course_name,
                risk_level=result["risk_level"],
                risk_pct=result["probability"] * 100,
                course_id=str(enrollment.course_id),
                analisis_primera_linea=primera_linea,
            )
            sent = await send_push_to_user(
                user_id=str(enrollment.student_id),
                title=msg["title"],
                body=msg["body"],
                url=msg["url"],
                session=bg_session,
            )
            if sent > 0:
                logger.info(
                    f"[Push] Alerta ALTO enviada → student {enrollment.student_id} "
                    f"en curso {course_name}"
                )

            # Notificación in-app (campanita) — siempre se crea, haya push o no
            try:
                from app.services.notification_service import notify_by_user_id
                await notify_by_user_id(
                    db=bg_session,
                    user_id=enrollment.student_id,
                    type="RISK_ALTO",
                    title=msg["title"],
                    body=msg["body"],
                    data={
                        "course_id": str(enrollment.course_id),
                        "url":       msg["url"],
                        "risk_pct":  round(result["probability"] * 100, 1),
                    },
                )
            except Exception as _notif_err:
                logger.warning("[Push] in-app notify_by_user_id falló: %s", _notif_err)

            # ── WhatsApp al estudiante (análisis completo) ────────────────────
            if student_phone and settings.WAHA_URL:
                await _send_whatsapp_risk_alert(
                    phone=student_phone,
                    student_name=student_name,
                    course_name=course_name,
                    risk_pct=result["probability"] * 100,
                    nivel=result["risk_level"],
                    analisis=analisis_completo,
                    course_id=str(enrollment.course_id),
                )

    except Exception as exc:
        logger.error(f"[Push] Error en background task de riesgo: {exc}")


@router.put(
    "/enrollments/{enrollment_id}/grades",
    response_model=GradesRead,
    status_code=200,
    summary="Registrar / actualizar notas de una inscripción",
    description=(
        "Registra o reemplaza el JSON de notas de una inscripción y recalcula "
        "automáticamente las notas por cohorte y la nota final. "
        "La estructura del JSON debe incluir los cohortes con sus pesos y actividades. "
        "PROFESSOR: solo puede registrar notas en inscripciones de sus cursos. "
        "ADMIN: acceso total. "
        "STUDENT: sin acceso."
    ),
    tags=["Inscripciones"],
)
async def set_enrollment_grades(
    enrollment_id: UUID,
    body: GradesUpdate,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser = Depends(get_current_user),
    service: GradeService = Depends(_get_grade_service),
    ml: AcademicRiskService = Depends(_get_ml_service),
) -> GradesRead:
    result = await service.set_grades(enrollment_id, body.grades, current_user)
    # Verificar riesgo y enviar push en segundo plano (no bloquea la respuesta)
    background_tasks.add_task(_push_risk_alert_if_needed, enrollment_id, result, ml)
    return result


@router.post(
    "/enrollments/{enrollment_id}/risk",
    response_model=PredictionOutput,
    status_code=200,
    summary="Calcular riesgo académico desde las notas de la inscripción",
    description=(
        "Calcula el riesgo de reprobación del estudiante usando exclusivamente "
        "las notas por cohorte y la nota total calculadas en la inscripción. "
        "Requiere consentimiento ML activo. "
        "STUDENT: solo puede calcular riesgo de sus propias inscripciones. "
        "PROFESSOR: solo puede calcular riesgo de estudiantes en sus cursos (RB-04). "
        "ADMIN: acceso total."
    ),
)
async def calculate_enrollment_risk(
    enrollment_id: UUID,
    background_tasks: BackgroundTasks,
    notify: bool = Query(False, description="Enviar notificación al estudiante si riesgo es ALTO o MEDIO"),
    current_user: CurrentUser = Depends(get_current_user),
    grade_service: GradeService = Depends(_get_grade_service),
    ml: AcademicRiskService = Depends(_get_ml_service),
    ml_app: MLApplicationService = Depends(_get_ml_app_service),
) -> PredictionOutput:
    # 1. Obtener notas (también verifica acceso por rol)
    grades_data = await grade_service.get_grades(enrollment_id, current_user)

    if grades_data.grades is None:
        raise HTTPException(
            status_code=422,
            detail="No hay notas registradas para esta inscripción",
        )

    # 2. Extraer features — predicción parcial con imputación si faltan cortes
    raw_c1    = float(grades_data.first_cohort_grade)  if grades_data.first_cohort_grade  is not None else None
    raw_c2    = float(grades_data.second_cohort_grade) if grades_data.second_cohort_grade is not None else None
    raw_c3    = float(grades_data.third_cohort_grade)  if grades_data.third_cohort_grade  is not None else None
    raw_total = float(grades_data.final_grade)         if grades_data.final_grade         is not None else None

    available_cohort_grades = [g for g in [raw_c1, raw_c2, raw_c3] if g is not None]
    if not available_cohort_grades:
        raise HTTPException(
            status_code=422,
            detail=(
                "Aún no hay calificaciones registradas para este curso. "
                "El docente debe ingresar al menos la nota del primer corte para activar el predictor."
            ),
        )

    # Impute missing cohort grades with the average of the available ones ("at current pace")
    avg_available = round(sum(available_cohort_grades) / len(available_cohort_grades), 2)
    nota_corte_1   = raw_c1    if raw_c1    is not None else avg_available
    nota_corte_2   = raw_c2    if raw_c2    is not None else avg_available
    nota_corte_final = raw_c3  if raw_c3    is not None else avg_available
    nota_total     = raw_total if raw_total is not None else avg_available

    is_partial = len(available_cohort_grades) < 3 or raw_total is None
    cortes_disponibles = len(available_cohort_grades)

    feature_vector = [
        nota_corte_1,
        nota_corte_2,
        nota_corte_final,
        nota_total,
    ]

    datos_estudiante = {
        "nota_corte_1": nota_corte_1,
        "nota_corte_2": nota_corte_2,
        "nota_corte_final": nota_corte_final,
        "nota_total": nota_total,
    }

    # 3. Predecir con verificación de consentimiento ML
    result = await ml_app.predict_with_consent_check(
        grades_data.student_id, feature_vector
    )
    probabilidad_riesgo = result["probability"]
    nivel_riesgo = result["risk_level"]
    features_scaled = np.array(result["scaled_features"])

    # 4. Construir respuesta completa
    analisis_ia = ml.generar_analisis_ia(datos_estudiante, probabilidad_riesgo)
    detalles_matematicos = ml.calcular_detalles_matematicos(features_scaled, probabilidad_riesgo)
    promedio_aprobados = ml.get_promedio_aprobados()

    output = PredictionOutput(
        probabilidad_riesgo=probabilidad_riesgo,
        porcentaje_riesgo=probabilidad_riesgo * 100,
        nivel_riesgo=nivel_riesgo,
        analisis_ia=analisis_ia,
        is_partial=is_partial,
        cortes_disponibles=cortes_disponibles,
        datos_radar={
            "labels": ["Corte 1", "Corte 2", "Corte final", "Total"],
            "estudiante": [
                nota_corte_1,
                nota_corte_2,
                nota_corte_final,
                nota_total,
            ],
            "promedio_aprobado": [
                promedio_aprobados["nota_corte_1"],
                promedio_aprobados["nota_corte_2"],
                promedio_aprobados["nota_corte_final"],
                promedio_aprobados["nota_total"],
            ],
        },
        detalles_matematicos=detalles_matematicos,
    )

    # Enviar notificación al estudiante para todos los niveles de riesgo
    if notify:
        background_tasks.add_task(
            _notify_student_prediction_result,
            enrollment_id,
            nivel_riesgo,
            probabilidad_riesgo,
            analisis_ia,
        )

    return output


@router.post(
    "/enrollments/{enrollment_id}/risk/cohort",
    response_model=CohortRiskOutput,
    status_code=200,
    summary="Calcular riesgo por cohorte desde notas de la inscripción",
    description=(
        "Calcula riesgo de un cohorte específico usando su parcial, promedio "
        "de seguimiento y asistencia del mismo cohorte. Requiere consentimiento ML activo."
    ),
)
async def calculate_enrollment_cohort_risk(
    enrollment_id: UUID,
    cohort_key: str = Query(
        ...,
        description="Cohorte a evaluar: first_cohort, second_cohort o third_cohort",
    ),
    current_user: CurrentUser = Depends(get_current_user),
    grade_service: GradeService = Depends(_get_grade_service),
    ml: AcademicRiskService = Depends(_get_ml_service),
    ml_app: MLApplicationService = Depends(_get_ml_app_service),
) -> CohortRiskOutput:
    grades_data = await grade_service.get_grades(enrollment_id, current_user)
    if grades_data.grades is None:
        raise HTTPException(
            status_code=422,
            detail="No hay notas registradas para esta inscripción",
        )

    nota_parcial = extract_cohort_parcial(grades_data.grades, cohort_key)
    promedio_seguimiento = extract_cohort_seguimiento(grades_data.grades, cohort_key)
    porcentaje_asistencia = extract_cohort_attendance_percentage(grades_data.grades, cohort_key)

    result = await ml_app.predict_cohort_with_consent_check(
        student_id=grades_data.student_id,
        cohort_key=cohort_key,
        nota_parcial=nota_parcial,
        promedio_seguimiento=promedio_seguimiento,
        porcentaje_asistencia=porcentaje_asistencia,
    )

    return CohortRiskOutput(
        cohort_key=result["cohort_key"],
        cohort_name=result["cohort_name"],
        probabilidad_riesgo=result["probability"],
        porcentaje_riesgo=result["probability"] * 100,
        nivel_riesgo=result["risk_level"],
        datos_cohorte={
            "nota_parcial": nota_parcial,
            "promedio_seguimiento": promedio_seguimiento,
            "porcentaje_asistencia": porcentaje_asistencia,
        },
        detalles_modelo=result["component_scores"],
    )
