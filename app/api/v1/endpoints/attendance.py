"""
AttendanceRouter — endpoints para el sistema de asistencias con QR rotativo.

Flujo:
  1. Profesor abre sesión POST /attendance/sessions  → recibe session_id + qr_seed + window_seconds
  2. Frontend del profesor genera el QR en cliente usando compute_qr_token()
     El QR rota automáticamente cada window_seconds sin re-llamar al backend
  3. Estudiante escanea el QR desde la app → POST /attendance/sessions/{session_id}/attend
  4. Backend valida el token (ventana temporal), registra la asistencia
  5. Profesor ve lista GET /attendance/sessions/{session_id}/attendances
  6. Profesor cierra la sesión PATCH /attendance/sessions/{session_id}/close
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import math
import secrets
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies.auth import get_current_user, CurrentUser
from app.core.config import settings
from app.infrastructure.database import get_session
from app.infrastructure.models.attendance import Attendance, ClassSession
from app.infrastructure.models.enrollment import Enrollment
from app.infrastructure.models.user import User
from app.domain.enums import RoleEnum

logger = logging.getLogger(__name__)
COLOMBIA_TZ = ZoneInfo("America/Bogota")

router = APIRouter(prefix="/attendance", tags=["Attendance"])


# ─── WhatsApp helper ──────────────────────────────────────────────────────────

def _fmt_colombia(dt: datetime) -> str:
    """Formatea un datetime (UTC, puede ser naive o aware) como cadena legible en hora colombiana."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    col = dt.astimezone(COLOMBIA_TZ)
    dias = ["lunes","martes","miércoles","jueves","viernes","sábado","domingo"]
    meses = ["enero","febrero","marzo","abril","mayo","junio",
             "julio","agosto","septiembre","octubre","noviembre","diciembre"]
    dia_semana = dias[col.weekday()]
    return f"{dia_semana} {col.day} de {meses[col.month-1]} de {col.year}, {col.strftime('%I:%M %p').lower()}"


async def _send_whatsapp_attendance(
    phone: str,
    student_name: str,
    course_name: str,
    session_label: str | None,
    recorded_at: datetime,
) -> None:
    """Envía al estudiante un WhatsApp confirmando su asistencia."""
    if not settings.WAHA_URL:
        return
    try:
        numero = phone.strip().replace(" ", "").replace("-", "").replace("+", "")
        if not numero.startswith("57") and len(numero) == 10:
            numero = f"57{numero}"
        chat_id = f"{numero}@c.us"

        primer_nombre = student_name.split()[0] if student_name else "estudiante"
        clase_info    = session_label if session_label else course_name
        fecha_hora    = _fmt_colombia(recorded_at)

        texto = (
            f"Hola {primer_nombre}, tu asistencia fue registrada.\n\n"
            f"*Materia:* {course_name}\n"
            f"*Clase:* {clase_info}\n"
            f"*Fecha y hora:* {fecha_hora}\n\n"
            f"La asistencia hace parte de tu seguimiento academico. Sigue adelante!"
        )

        import httpx
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"{settings.WAHA_URL.rstrip('/')}/api/sendText",
                json={"chatId": chat_id, "text": texto, "session": "default"},
                headers={"X-Api-Key": settings.WAHA_API_KEY},
            )
    except Exception as exc:
        logger.warning("WhatsApp attendance alert failed: %s", exc)


# ─── Utilidades de token QR ───────────────────────────────────────────────────

def compute_qr_token(qr_seed: str, window_seconds: int, at: datetime | None = None) -> str:
    """
    Genera el token QR válido para la ventana temporal actual.
    token = HMAC-SHA256(qr_seed, floor(epoch / window_seconds))
    Mismo algoritmo en frontend (JS) y backend (Python) → sin llamadas extra.
    """
    now = at or datetime.now(timezone.utc)
    epoch = int(now.timestamp())
    window_index = math.floor(epoch / window_seconds)
    raw = f"{qr_seed}:{window_index}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def is_token_valid(qr_seed: str, window_seconds: int, token: str) -> bool:
    """Acepta el token con tolerancia ±2 ventanas.

    ±1 cubre desfase de reloj entre el navegador del profesor y el servidor.
    ±2 cubre además el tiempo de login del estudiante (redirección a /login
    y vuelta): con ventana de 60s el token sigue siendo válido 5 minutos.
    """
    now = datetime.now(timezone.utc)
    epoch = int(now.timestamp())
    for offset in (0, -1, +1, -2, +2):
        window_index = math.floor(epoch / window_seconds) + offset
        raw = f"{qr_seed}:{window_index}"
        expected = hashlib.sha256(raw.encode()).hexdigest()[:32]
        if expected == token:
            return True
    return False


# ─── Schemas ──────────────────────────────────────────────────────────────────

class SessionCreate(BaseModel):
    course_id: UUID
    window_seconds: int = Field(default=60, ge=15, le=600, description="Duración de cada ventana QR en segundos")
    label: Optional[str] = Field(default=None, max_length=120)


class SessionRead(BaseModel):
    id: UUID
    course_id: UUID
    professor_id: UUID
    window_seconds: int
    qr_seed: str           # El frontend usa esto para generar el QR localmente
    label: Optional[str]
    is_active: bool
    created_at: datetime
    closed_at: Optional[datetime]

    # Token actual (para debug/preview en el mismo request)
    current_token: str

    class Config:
        from_attributes = True


class AttendRecord(BaseModel):
    """Payload que envía el estudiante al escanear el QR."""
    token: str = Field(..., description="Token extraído del QR escaneado")


class AttendanceRead(BaseModel):
    id: UUID
    student_id: UUID
    student_name: str
    recorded_at: datetime

    class Config:
        from_attributes = True


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post(
    "/sessions",
    response_model=SessionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Crear sesión de clase (profesor)",
)
async def create_session(
    body: SessionCreate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> SessionRead:
    """El profesor inicia una sesión de clase y obtiene la semilla del QR rotativo."""
    if current_user.role not in (RoleEnum.PROFESSOR, RoleEnum.ADMIN):
        raise HTTPException(status_code=403, detail="Solo profesores pueden crear sesiones")

    session = ClassSession(
        course_id=body.course_id,
        professor_id=current_user.id,
        window_seconds=body.window_seconds,
        qr_seed=secrets.token_hex(16),
        label=body.label,
        is_active=True,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    return SessionRead(
        id=session.id,
        course_id=session.course_id,
        professor_id=session.professor_id,
        window_seconds=session.window_seconds,
        qr_seed=session.qr_seed,
        label=session.label,
        is_active=session.is_active,
        created_at=session.created_at,
        closed_at=session.closed_at,
        current_token=compute_qr_token(session.qr_seed, session.window_seconds),
    )


@router.get(
    "/sessions/course/{course_id}",
    response_model=list[SessionRead],
    summary="Listar sesiones de un curso",
)
async def list_sessions(
    course_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> list[SessionRead]:
    result = await db.execute(
        select(ClassSession)
        .where(ClassSession.course_id == course_id)
        .order_by(ClassSession.created_at.desc())
    )
    sessions = result.scalars().all()
    return [
        SessionRead(
            id=s.id,
            course_id=s.course_id,
            professor_id=s.professor_id,
            window_seconds=s.window_seconds,
            qr_seed=s.qr_seed,
            label=s.label,
            is_active=s.is_active,
            created_at=s.created_at,
            closed_at=s.closed_at,
            current_token=compute_qr_token(s.qr_seed, s.window_seconds),
        )
        for s in sessions
    ]


@router.post(
    "/sessions/{session_id}/attend",
    status_code=status.HTTP_201_CREATED,
    summary="Registrar asistencia escaneando el QR (estudiante)",
)
async def register_attendance(
    session_id: UUID,
    body: AttendRecord,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> dict:
    """
    Valida el token QR y registra la asistencia del estudiante autenticado.
    Validaciones:
      1. Sesión existe y está activa
      2. Token válido para la ventana temporal actual (tolerancia ±1 ventana)
      3. Estudiante está matriculado en el curso de la sesión
      4. No existe registro previo del estudiante en esta sesión
    """
    # 1. Verificar que es estudiante
    if current_user.role not in (RoleEnum.STUDENT, RoleEnum.ADMIN):
        raise HTTPException(status_code=403, detail="Solo estudiantes pueden registrar asistencia")

    # 2. Obtener sesión
    sess_q = await db.execute(select(ClassSession).where(ClassSession.id == session_id))
    session = sess_q.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")
    if not session.is_active:
        raise HTTPException(status_code=409, detail="Esta sesión ya fue cerrada por el profesor")

    # 3. Validar token QR
    if not is_token_valid(session.qr_seed, session.window_seconds, body.token):
        raise HTTPException(
            status_code=400,
            detail="El código QR ha expirado o es inválido. Pide al profesor que muestre el QR actualizado.",
        )

    # 4. Verificar que el estudiante está matriculado
    enroll_q = await db.execute(
        select(Enrollment).where(
            Enrollment.course_id == session.course_id,
            Enrollment.student_id == current_user.id,
        )
    )
    enrollment = enroll_q.scalar_one_or_none()
    if not enrollment:
        raise HTTPException(
            status_code=403,
            detail="No estás matriculado en el curso de esta sesión",
        )

    # 5. Verificar que no haya registro previo
    prev_q = await db.execute(
        select(Attendance).where(
            Attendance.session_id == session_id,
            Attendance.student_id == current_user.id,
        )
    )
    if prev_q.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Ya registraste tu asistencia en esta sesión")

    # 6. Crear registro
    attendance = Attendance(
        session_id=session_id,
        student_id=current_user.id,
        qr_token_used=body.token,
    )
    db.add(attendance)
    await db.commit()

    # 7. Hora Colombia (se usa en mensajes de respuesta y notificaciones)
    recorded_utc = attendance.recorded_at.replace(tzinfo=timezone.utc)
    col_time = recorded_utc.astimezone(COLOMBIA_TZ)
    hora_col = col_time.strftime("%I:%M %p").lower()

    # 8. Obtener nombre del curso (necesario para WhatsApp e in-app)
    from app.infrastructure.models.course import Course
    from app.infrastructure.models.subject import Subject
    course_q = await db.execute(
        select(Subject.name)
        .join(Course, Course.subject_id == Subject.id)
        .where(Course.id == session.course_id)
    )
    course_name = course_q.scalar_one_or_none() or "tu materia"

    # 9. Notificaciones in-app (campanita) — síncronas para que aparezcan de inmediato
    try:
        from app.services.notification_service import notify
        # 9a. Notificar al propio estudiante
        await notify(
            db=db,
            user=current_user,
            type="ATTENDANCE",
            title="Asistencia registrada",
            body=f"Tu asistencia a {course_name} fue registrada correctamente — {hora_col}",
            data={
                "session_id": str(session_id),
                "course_id":  str(session.course_id),
            },
            send_whatsapp=False,   # WhatsApp se envía por separado abajo
            send_email=False,
        )
    except Exception as _notif_err:
        logger.warning("[Attendance] in-app notify estudiante falló: %s", _notif_err)

    # 9b. Notificar al profesor que un estudiante se acaba de unir
    try:
        from app.services.notification_service import notify_by_user_id
        # Obtener el profesor de la sesión
        from app.infrastructure.models.course import Course as _Course
        course_obj_q = await db.execute(select(_Course).where(_Course.id == session.course_id))
        course_obj = course_obj_q.scalar_one_or_none()
        if course_obj and course_obj.professor_id:
            await notify_by_user_id(
                db=db,
                user_id=course_obj.professor_id,
                type="ATTENDANCE",
                title="Asistencia registrada",
                body=f"{current_user.full_name} registró su asistencia en {course_name} — {hora_col}",
                data={
                    "session_id": str(session_id),
                    "course_id":  str(session.course_id),
                    "student_id": str(current_user.id),
                },
            )
    except Exception as _prof_notif_err:
        logger.warning("[Attendance] in-app notify profesor falló: %s", _prof_notif_err)

    # 10. WhatsApp de confirmación al estudiante (en background)
    if current_user.phone:
        background_tasks.add_task(
            _send_whatsapp_attendance,
            phone=current_user.phone,
            student_name=current_user.full_name,
            course_name=course_name,
            session_label=session.label,
            recorded_at=attendance.recorded_at,
        )
    else:
        # Sin número de teléfono → aviso in-app para que lo registre
        try:
            from app.services.notification_service import notify
            await notify(
                db=db,
                user=current_user,
                type="SYSTEM",
                title="Sin número de WhatsApp",
                body="No pudimos enviarte la confirmación por WhatsApp. Registra tu número en tu perfil para recibir alertas.",
                send_whatsapp=False,
                send_email=False,
            )
        except Exception:
            pass

    return {
        "ok": True,
        "message": f"Asistencia registrada correctamente — {hora_col}",
        "session_label": session.label or "Sesión de clase",
        "recorded_at": attendance.recorded_at.isoformat(),
    }


@router.get(
    "/sessions/{session_id}/attendances",
    response_model=list[AttendanceRead],
    summary="Ver lista de asistentes a una sesión (profesor)",
)
async def get_attendances(
    session_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> list[AttendanceRead]:
    if current_user.role not in (RoleEnum.PROFESSOR, RoleEnum.ADMIN):
        raise HTTPException(status_code=403, detail="Solo profesores pueden ver la lista")

    result = await db.execute(
        select(Attendance, User)
        .join(User, Attendance.student_id == User.id)
        .where(Attendance.session_id == session_id)
        .order_by(Attendance.recorded_at)
    )
    rows = result.all()
    return [
        AttendanceRead(
            id=att.id,
            student_id=att.student_id,
            student_name=user.full_name,
            recorded_at=att.recorded_at,
        )
        for att, user in rows
    ]


@router.patch(
    "/sessions/{session_id}/close",
    summary="Cerrar sesión de clase (profesor)",
)
async def close_session(
    session_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> dict:
    if current_user.role not in (RoleEnum.PROFESSOR, RoleEnum.ADMIN):
        raise HTTPException(status_code=403, detail="Solo el profesor puede cerrar la sesión")

    sess_q = await db.execute(select(ClassSession).where(ClassSession.id == session_id))
    session = sess_q.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")

    session.is_active = False
    session.closed_at = datetime.utcnow()
    await db.commit()

    return {"ok": True, "message": "Sesión cerrada"}


# ─── Notificación de asistencia manual ────────────────────────────────────────

class ManualAttendanceNotifyBody(BaseModel):
    student_id: UUID
    course_name: str
    cohort: str


@router.post(
    "/notify-manual",
    summary="Notificar al estudiante asistencia registrada manualmente (profesor)",
)
async def notify_manual_attendance(
    body: ManualAttendanceNotifyBody,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> dict:
    """
    El profesor registró la asistencia de un estudiante manualmente (no por QR).
    Envía al estudiante una notificación in-app y WhatsApp confirmando el registro.
    """
    if current_user.role not in (RoleEnum.PROFESSOR, RoleEnum.ADMIN):
        raise HTTPException(status_code=403, detail="Solo profesores pueden usar esta función")

    student_q = await db.execute(select(User).where(User.id == body.student_id))
    student = student_q.scalar_one_or_none()
    if not student:
        return {"ok": False, "message": "Estudiante no encontrado"}

    hora_col = _fmt_colombia(datetime.now(timezone.utc))

    try:
        from app.services.notification_service import notify
        await notify(
            db=db,
            user=student,
            type="ATTENDANCE",
            title="Asistencia registrada",
            body=f"Tu docente registró tu asistencia a *{body.course_name}* el {hora_col}. Que sigan las clases con esa puntualidad!",
            data={"course_name": body.course_name, "cohort": body.cohort},
            send_whatsapp=True,
        )
    except Exception as exc:
        logger.warning("[Manual Attendance Notify] falló para %s: %s", body.student_id, exc)

    return {"ok": True, "message": "Notificación enviada"}


# ─── Historial de asistencia ──────────────────────────────────────────────────

class AttendanceHistoryItem(BaseModel):
    session_id: UUID
    session_label: Optional[str]
    recorded_at: datetime
    recorded_at_colombia: str   # formato legible "lun 12 may, 08:30 am"

    class Config:
        from_attributes = True


class SessionHistoryItem(BaseModel):
    """Para el profesor: una sesión con su lista de asistentes."""
    id: UUID
    label: Optional[str]
    created_at: datetime
    closed_at: Optional[datetime]
    is_active: bool
    total_attendees: int
    attendees: list[AttendanceRead]


@router.get(
    "/student/me/history",
    response_model=list[AttendanceHistoryItem],
    summary="Historial de asistencias del estudiante autenticado",
)
async def get_my_attendance_history(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> list[AttendanceHistoryItem]:
    """Devuelve todas las asistencias registradas del estudiante, con hora en Colombia."""
    if current_user.role not in (RoleEnum.STUDENT, RoleEnum.ADMIN):
        raise HTTPException(status_code=403, detail="Solo estudiantes pueden ver su historial")

    result = await db.execute(
        select(Attendance, ClassSession)
        .join(ClassSession, Attendance.session_id == ClassSession.id)
        .where(Attendance.student_id == current_user.id)
        .order_by(Attendance.recorded_at.desc())
    )
    rows = result.all()

    items = []
    for att, sess in rows:
        utc = att.recorded_at.replace(tzinfo=timezone.utc)
        col = utc.astimezone(COLOMBIA_TZ)
        dias = ["lun","mar","mié","jue","vie","sáb","dom"]
        meses = ["ene","feb","mar","abr","may","jun","jul","ago","sep","oct","nov","dic"]
        readable = f"{dias[col.weekday()]} {col.day} {meses[col.month-1]}, {col.strftime('%I:%M %p').lower()}"
        items.append(AttendanceHistoryItem(
            session_id=sess.id,
            session_label=sess.label,
            recorded_at=att.recorded_at,
            recorded_at_colombia=readable,
        ))
    return items


@router.get(
    "/student/me/history/course/{course_id}",
    response_model=list[AttendanceHistoryItem],
    summary="Historial de asistencias del estudiante en un curso específico",
)
async def get_my_course_attendance(
    course_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> list[AttendanceHistoryItem]:
    """Asistencias del estudiante filtradas por curso."""
    result = await db.execute(
        select(Attendance, ClassSession)
        .join(ClassSession, Attendance.session_id == ClassSession.id)
        .where(
            Attendance.student_id == current_user.id,
            ClassSession.course_id == course_id,
        )
        .order_by(Attendance.recorded_at.desc())
    )
    rows = result.all()

    items = []
    for att, sess in rows:
        utc = att.recorded_at.replace(tzinfo=timezone.utc)
        col = utc.astimezone(COLOMBIA_TZ)
        dias = ["lun","mar","mié","jue","vie","sáb","dom"]
        meses = ["ene","feb","mar","abr","may","jun","jul","ago","sep","oct","nov","dic"]
        readable = f"{dias[col.weekday()]} {col.day} {meses[col.month-1]}, {col.strftime('%I:%M %p').lower()}"
        items.append(AttendanceHistoryItem(
            session_id=sess.id,
            session_label=sess.label,
            recorded_at=att.recorded_at,
            recorded_at_colombia=readable,
        ))
    return items


@router.get(
    "/sessions/course/{course_id}/history",
    response_model=list[SessionHistoryItem],
    summary="Historial completo de sesiones de un curso (profesor)",
)
async def get_course_sessions_history(
    course_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> list[SessionHistoryItem]:
    """Profesor ve todas las sesiones de su curso con lista de asistentes."""
    if current_user.role not in (RoleEnum.PROFESSOR, RoleEnum.ADMIN):
        raise HTTPException(status_code=403, detail="Solo profesores pueden ver el historial")

    sessions_q = await db.execute(
        select(ClassSession)
        .where(ClassSession.course_id == course_id)
        .order_by(ClassSession.created_at.desc())
    )
    sessions = sessions_q.scalars().all()

    result = []
    for sess in sessions:
        att_q = await db.execute(
            select(Attendance, User)
            .join(User, Attendance.student_id == User.id)
            .where(Attendance.session_id == sess.id)
            .order_by(Attendance.recorded_at)
        )
        attendees = [
            AttendanceRead(
                id=att.id,
                student_id=att.student_id,
                student_name=user.full_name,
                recorded_at=att.recorded_at,
            )
            for att, user in att_q.all()
        ]
        result.append(SessionHistoryItem(
            id=sess.id,
            label=sess.label,
            created_at=sess.created_at,
            closed_at=sess.closed_at,
            is_active=sess.is_active,
            total_attendees=len(attendees),
            attendees=attendees,
        ))
    return result


# ─── QR Code image endpoint ───────────────────────────────────────────────────

from fastapi.responses import Response as FastAPIResponse
import io

@router.get("/qr")
async def generate_qr_image(data: str, size: int = 220):
    """
    Genera un QR code como imagen PNG a partir del texto `data`.
    Usado por el frontend para renderizar QRs escaneables.
    """
    import qrcode
    from qrcode.image.pil import PilImage

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)

    img = qr.make_image(image_factory=PilImage)
    img = img.resize((size, size))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    return FastAPIResponse(
        content=buf.read(),
        media_type="image/png",
        headers={"Cache-Control": "no-store"},
    )
