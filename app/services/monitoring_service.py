"""
Servicio de monitoreo de infraestructura.

Verifica el estado de todos los componentes críticos del sistema y envía
un resumen al grupo de WhatsApp configurado cuando detecta fallas.

Componentes monitoreados:
  - Backend    (self-check de la propia instancia)
  - Base de datos PostgreSQL
  - WAHA       (WhatsApp HTTP API — sesión 'default')
  - Frontend   (Vite/SPA en producción)
  - RAG API    (servicio de búsqueda semántica)
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal
from zoneinfo import ZoneInfo
from uuid import UUID

import httpx
from sqlalchemy import text, select, func
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings

logger = logging.getLogger(__name__)
COLOMBIA_TZ = ZoneInfo("America/Bogota")

# ─── Constantes ───────────────────────────────────────────────────────────────

STATUS_OK   = "✅"
STATUS_FAIL = "❌"
STATUS_WARN = "⚠️"

FRONTEND_URL = settings.FRONTEND_URL or "http://localhost:3000"
RAG_URL = "https://rag-predictor-api.blackgrass-448535b9.brazilsouth.azurecontainerapps.io"

# Timeout por servicio (segundos)
HTTP_TIMEOUT = 10
DB_TIMEOUT   = 8


# ─── Modelos ──────────────────────────────────────────────────────────────────

@dataclass
class ServiceStatus:
    name: str
    ok: bool
    detail: str = ""
    latency_ms: int | None = None

    @property
    def icon(self) -> str:
        return STATUS_OK if self.ok else STATUS_FAIL


@dataclass
class MonitoringReport:
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))  # no se escribe a DB
    services: list[ServiceStatus] = field(default_factory=list)

    @property
    def all_ok(self) -> bool:
        return all(s.ok for s in self.services)

    @property
    def failures(self) -> list[ServiceStatus]:
        return [s for s in self.services if not s.ok]

    def _fmt_colombia(self) -> str:
        """Hora del reporte en zona horaria de Colombia."""
        col = self.timestamp.astimezone(COLOMBIA_TZ)
        dias = ["lunes","martes","miércoles","jueves","viernes","sábado","domingo"]
        meses = ["enero","febrero","marzo","abril","mayo","junio",
                 "julio","agosto","septiembre","octubre","noviembre","diciembre"]
        return (
            f"{dias[col.weekday()]} {col.day} de {meses[col.month-1]} "
            f"de {col.year}, {col.strftime('%I:%M %p').lower()}"
        )

    def to_whatsapp_text(self) -> str:
        estado = "🟢 Todo funciona correctamente" if self.all_ok else "🔴 Se detectaron fallas"
        header = (
            f"{estado}\n"
            f"📅 {self._fmt_colombia()}\n"
            "─────────────────────\n"
        )
        lines = []
        for s in self.services:
            if s.ok:
                lines.append(f"✅ *{s.name}* — operativo")
            else:
                detalle = f": {s.detail}" if s.detail else ""
                lines.append(f"❌ *{s.name}* — no disponible{detalle}")
        footer = (
            "\n─────────────────────\n"
            "_Academic Risk Monitor_"
        )
        return header + "\n".join(lines) + footer


# ─── Checks individuales ──────────────────────────────────────────────────────

async def _check_backend() -> ServiceStatus:
    """El backend está vivo si este código corre. Verificamos al menos que
    el loop de asyncio responde."""
    return ServiceStatus(name="Backend API", ok=True, detail="self-check OK")


async def _check_database() -> ServiceStatus:
    """Ejecuta un SELECT 1 contra la base de datos real."""
    try:
        db_url = (
            f"postgresql+asyncpg://{settings.DB_USER}:{settings.DB_PASSWORD}"
            f"@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"
        )
        engine = create_async_engine(db_url, pool_size=1, max_overflow=0)
        t0 = asyncio.get_event_loop().time()
        async with engine.connect() as conn:
            await asyncio.wait_for(conn.execute(text("SELECT 1")), timeout=DB_TIMEOUT)
        latency = int((asyncio.get_event_loop().time() - t0) * 1000)
        await engine.dispose()
        return ServiceStatus(name="Base de datos", ok=True, latency_ms=latency)
    except asyncio.TimeoutError:
        return ServiceStatus(name="Base de datos", ok=False, detail="Timeout al conectar")
    except Exception as exc:
        return ServiceStatus(name="Base de datos", ok=False, detail=str(exc)[:120])


async def _check_waha() -> ServiceStatus:
    """Consulta el estado de la sesión 'default' en WAHA."""
    if not settings.WAHA_URL:
        return ServiceStatus(name="WAHA (WhatsApp)", ok=False, detail="WAHA_URL no configurado")
    try:
        url = f"{settings.WAHA_URL.rstrip('/')}/api/sessions/default"
        headers = {"X-Api-Key": settings.WAHA_API_KEY}
        t0 = asyncio.get_event_loop().time()
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            resp = await client.get(url, headers=headers)
        latency = int((asyncio.get_event_loop().time() - t0) * 1000)
        if resp.status_code == 200:
            data = resp.json()
            status = data.get("status", "unknown")
            ok = status in ("WORKING", "CONNECTED", "AUTHENTICATED")
            return ServiceStatus(
                name="WAHA (WhatsApp)",
                ok=ok,
                detail="" if ok else f"sesión en estado: {status}",
                latency_ms=latency,
            )
        return ServiceStatus(
            name="WAHA (WhatsApp)",
            ok=False,
            detail=f"HTTP {resp.status_code}",
            latency_ms=latency,
        )
    except httpx.TimeoutException:
        return ServiceStatus(name="WAHA (WhatsApp)", ok=False, detail="Timeout")
    except Exception as exc:
        return ServiceStatus(name="WAHA (WhatsApp)", ok=False, detail=str(exc)[:120])


async def _check_frontend() -> ServiceStatus:
    """Hace GET al frontend y verifica que devuelva 200."""
    try:
        t0 = asyncio.get_event_loop().time()
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(FRONTEND_URL)
        latency = int((asyncio.get_event_loop().time() - t0) * 1000)
        ok = resp.status_code < 400
        return ServiceStatus(
            name="Frontend",
            ok=ok,
            detail="" if ok else f"HTTP {resp.status_code}",
            latency_ms=latency,
        )
    except httpx.TimeoutException:
        return ServiceStatus(name="Frontend", ok=False, detail="Timeout")
    except Exception as exc:
        return ServiceStatus(name="Frontend", ok=False, detail=str(exc)[:120])


async def _check_rag() -> ServiceStatus:
    """Hace GET al health endpoint de la RAG API."""
    try:
        t0 = asyncio.get_event_loop().time()
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            resp = await client.get(f"{RAG_URL}/health")
        latency = int((asyncio.get_event_loop().time() - t0) * 1000)
        ok = resp.status_code < 400
        return ServiceStatus(
            name="RAG API",
            ok=ok,
            detail="" if ok else f"HTTP {resp.status_code}",
            latency_ms=latency,
        )
    except httpx.TimeoutException:
        return ServiceStatus(name="RAG API", ok=False, detail="Timeout")
    except Exception as exc:
        return ServiceStatus(name="RAG API", ok=False, detail=str(exc)[:120])


# ─── Envío al grupo de WhatsApp ───────────────────────────────────────────────

async def _send_to_group(text: str) -> None:
    """Envía un mensaje al grupo de monitoreo configurado."""
    group_jid = settings.WAHA_MONITORING_GROUP
    if not settings.WAHA_URL or not group_jid:
        logger.warning("[Monitor] WAHA_URL o WAHA_MONITORING_GROUP no configurados — omitiendo envío")
        return

    url = f"{settings.WAHA_URL.rstrip('/')}/api/sendText"
    payload = {"session": "default", "chatId": group_jid, "text": text}
    headers = {"X-Api-Key": settings.WAHA_API_KEY}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code >= 400:
            logger.error("[Monitor] Error enviando al grupo (%s): %s", resp.status_code, resp.text[:200])
        else:
            logger.info("[Monitor] Alerta enviada al grupo %s", group_jid)
    except Exception as exc:
        logger.error("[Monitor] Excepción enviando al grupo: %s", exc)


# ─── Class crisis check ──────────────────────────────────────────────────────

CRISIS_THRESHOLD = 0.35   # 35% del grupo en riesgo ALTO = crisis

async def check_class_crisis() -> None:
    """
    Revisa todos los cursos activos. Si ≥35% de estudiantes tienen riesgo ALTO,
    notifica al profesor por WhatsApp + in-app y sugiere acciones pedagógicas.
    """
    try:
        db_url = (
            f"postgresql+asyncpg://{settings.DB_USER}:{settings.DB_PASSWORD}"
            f"@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"
        )
        engine = create_async_engine(db_url, pool_size=1, max_overflow=0)

        async with engine.connect() as conn:
            # Cursos con su % de estudiantes en riesgo ALTO
            # Usa la columna risk_level que guardan los endpoints de predicción
            rows = await conn.execute(text("""
                SELECT
                    c.id               AS course_id,
                    s.name             AS course_name,
                    u.id               AS professor_id,
                    u.full_name        AS professor_name,
                    u.phone            AS professor_phone,
                    u.email            AS professor_email,
                    u.whatsapp_enabled AS wa_enabled,
                    COUNT(e.id)        AS total,
                    SUM(CASE WHEN
                        CAST(e.grades->>'risk_level' AS TEXT) = 'ALTO'
                    THEN 1 ELSE 0 END) AS alto_count
                FROM courses c
                JOIN subjects s ON s.id = c.subject_id
                JOIN users u ON u.id = c.professor_id
                JOIN enrollments e ON e.course_id = c.id
                WHERE c.professor_id IS NOT NULL
                  AND e.status = 'ACTIVE'
                GROUP BY c.id, s.name, u.id, u.full_name, u.phone, u.email, u.whatsapp_enabled
                HAVING COUNT(e.id) >= 3
            """))
            courses = rows.mappings().all()

        await engine.dispose()

        for course in courses:
            total = course["total"] or 0
            alto = course["alto_count"] or 0
            if total == 0:
                continue
            pct = alto / total
            if pct < CRISIS_THRESHOLD:
                continue

            pct_str = f"{round(pct * 100)}%"
            logger.warning(
                "[Crisis] Curso %s — %s/%s estudiantes en riesgo ALTO (%s)",
                course["course_name"], alto, total, pct_str,
            )

            msg = (
                f"⚠️ *Alerta de crisis académica — {course['course_name']}*\n\n"
                f"{alto} de {total} estudiantes ({pct_str}) tienen riesgo ALTO de reprobación.\n\n"
                "💡 *Recomendaciones:*\n"
                "• Realiza una clase de repaso de los temas con mayor dificultad\n"
                "• Propón actividades de recuperación o bonificación\n"
                "• Abre espacios de tutoría individual o grupal\n"
                "• Comunícate directamente con los estudiantes en riesgo\n\n"
                "_Sistema de Seguimiento Académico USB_"
            )

            # WhatsApp al profesor
            if course["wa_enabled"] and course["professor_phone"] and settings.WAHA_URL:
                try:
                    numero = str(course["professor_phone"]).strip().replace("+","")
                    if not numero.startswith("57") and len(numero) == 10:
                        numero = f"57{numero}"
                    async with httpx.AsyncClient(timeout=10) as client:
                        await client.post(
                            f"{settings.WAHA_URL.rstrip('/')}/api/sendText",
                            json={"chatId": f"{numero}@c.us", "text": msg, "session": "default"},
                            headers={"X-Api-Key": settings.WAHA_API_KEY},
                        )
                except Exception as exc:
                    logger.warning("[Crisis] WA to professor failed: %s", exc)

            # Notificación in-app al profesor
            try:
                notif_engine = create_async_engine(db_url, pool_size=1, max_overflow=0)
                async with notif_engine.connect() as conn2:
                    await conn2.execute(text("""
                        INSERT INTO notifications (id, user_id, type, title, body, data, read, created_at)
                        VALUES (
                            gen_random_uuid(),
                            :uid,
                            'CLASS_CRISIS',
                            :title,
                            :body,
                            :data::jsonb,
                            false,
                            NOW()
                        )
                    """), {
                        "uid": str(course["professor_id"]),
                        "title": f"⚠️ Crisis en {course['course_name']}",
                        "body": f"{alto}/{total} estudiantes ({pct_str}) en riesgo alto. Revisa el panel.",
                        "data": f'{{"course_id":"{course["course_id"]}","alto":{alto},"total":{total}}}',
                    })
                    await conn2.commit()
                await notif_engine.dispose()
            except Exception as exc:
                logger.warning("[Crisis] in-app notification failed: %s", exc)

    except Exception as exc:
        logger.error("[Crisis] check_class_crisis error: %s", exc)


# ─── Auto risk alert (estudiantes ALTO) ──────────────────────────────────────

_last_risk_alert_day: int | None = None   # número de día ISO (lunes=1…domingo=7)
RISK_ALERT_DAY = 1                        # 1 = lunes


async def send_at_risk_alerts() -> None:
    """
    Envía WhatsApp + in-app a cada estudiante con riesgo ALTO (risk_level='ALTO'
    en su última predicción).  Se ejecuta una vez por semana (lunes por defecto).
    Solo envía si el usuario tiene whatsapp_enabled=true o email_enabled=true.
    """
    global _last_risk_alert_day
    today = datetime.now(COLOMBIA_TZ).isoweekday()   # 1=lunes, 7=domingo
    if today != RISK_ALERT_DAY:
        return
    if _last_risk_alert_day == today:
        return   # ya enviamos hoy, no spamear
    _last_risk_alert_day = today

    try:
        db_url = (
            f"postgresql+asyncpg://{settings.DB_USER}:{settings.DB_PASSWORD}"
            f"@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"
        )
        engine = create_async_engine(db_url, pool_size=1, max_overflow=0)

        async with engine.connect() as conn:
            rows = await conn.execute(text("""
                SELECT
                    e.id                    AS enrollment_id,
                    u.id                    AS student_id,
                    u.full_name             AS student_name,
                    u.email                 AS student_email,
                    u.phone                 AS student_phone,
                    u.whatsapp_enabled      AS wa_enabled,
                    u.email_enabled         AS email_enabled,
                    s.name                  AS course_name,
                    CAST(e.grades->>'risk_level' AS TEXT) AS risk_level
                FROM enrollments e
                JOIN users u ON u.id = (
                    SELECT sp.user_id
                    FROM student_profiles sp
                    WHERE sp.id = e.student_id
                    LIMIT 1
                )
                JOIN courses c ON c.id = e.course_id
                JOIN subjects s ON s.id = c.subject_id
                WHERE e.status = 'ACTIVE'
                  AND CAST(e.grades->>'risk_level' AS TEXT) = 'ALTO'
            """))
            students_at_risk = rows.mappings().all()

        await engine.dispose()

        if not students_at_risk:
            logger.info("[RiskAlert] Sin estudiantes ALTO esta semana.")
            return

        logger.info("[RiskAlert] Enviando alertas a %d estudiantes en riesgo ALTO.", len(students_at_risk))

        notif_engine = create_async_engine(db_url, pool_size=2, max_overflow=0)

        for student in students_at_risk:
            name_first = str(student["student_name"]).split()[0]
            course_name = student["course_name"]

            # ── WhatsApp ─────────────────────────────────────────────────────
            if student["wa_enabled"] and student["student_phone"] and settings.WAHA_URL:
                wa_msg = (
                    f"⚠️ *Alerta académica — {course_name}*\n\n"
                    f"Hola {name_first}, el sistema detectó que tu nivel de riesgo académico "
                    f"en *{course_name}* es *ALTO*.\n\n"
                    f"📋 *¿Qué puedes hacer?*\n"
                    f"• Revisa tus notas y asistencia en la app\n"
                    f"• Habla con tu docente para pedir apoyo\n"
                    f"• Asiste a las tutorías disponibles\n"
                    f"• Usa el simulador para ver cuánto necesitas sacar\n\n"
                    f"💪 Aún es momento de mejorar. ¡Tú puedes lograrlo!\n\n"
                    f"_Sistema de Seguimiento Académico USB_"
                )
                try:
                    numero = str(student["student_phone"]).strip().replace("+","").replace(" ","")
                    if not numero.startswith("57") and len(numero) == 10:
                        numero = f"57{numero}"
                    async with httpx.AsyncClient(timeout=10) as client:
                        await client.post(
                            f"{settings.WAHA_URL.rstrip('/')}/api/sendText",
                            json={"chatId": f"{numero}@c.us", "text": wa_msg, "session": "default"},
                            headers={"X-Api-Key": settings.WAHA_API_KEY},
                        )
                except Exception as exc:
                    logger.warning("[RiskAlert] WA to %s failed: %s", student["student_email"], exc)

            # ── Email ─────────────────────────────────────────────────────────
            if student["email_enabled"] and student["student_email"]:
                try:
                    from app.services.email_service import send_generic_notification
                    email_body = (
                        f"Hola {name_first},\n\n"
                        f"El sistema de seguimiento académico detectó que tu nivel de riesgo en "
                        f"{course_name} es ALTO.\n\n"
                        f"Te recomendamos:\n"
                        f"• Revisar tus calificaciones y asistencia en la app\n"
                        f"• Hablar con tu docente para solicitar apoyo\n"
                        f"• Asistir a sesiones de tutoría\n"
                        f"• Usar el simulador para calcular cuánto necesitas en los cortes restantes\n\n"
                        f"¡Aún tienes tiempo de mejorar tu situación académica!"
                    )
                    await send_generic_notification(
                        email=student["student_email"],
                        name=student["student_name"],
                        subject=f"⚠️ Alerta de riesgo académico — {course_name}",
                        body=email_body,
                    )
                except Exception as exc:
                    logger.warning("[RiskAlert] Email to %s failed: %s", student["student_email"], exc)

            # ── In-app notification ──────────────────────────────────────────
            try:
                async with notif_engine.connect() as conn:
                    await conn.execute(text("""
                        INSERT INTO notifications (id, user_id, type, title, body, data, read, created_at)
                        VALUES (
                            gen_random_uuid(),
                            :uid,
                            'RISK_ALTO',
                            :title,
                            :body,
                            :data::jsonb,
                            false,
                            NOW()
                        )
                    """), {
                        "uid": str(student["student_id"]),
                        "title": f"⚠️ Riesgo ALTO en {course_name}",
                        "body": (
                            f"Tu nivel de riesgo en {course_name} es ALTO. "
                            f"Consulta la app y habla con tu docente para mejorar."
                        ),
                        "data": f'{{"course_name":"{course_name}","risk_level":"ALTO"}}',
                    })
                    await conn.commit()
            except Exception as exc:
                logger.warning("[RiskAlert] in-app for %s failed: %s", student["student_email"], exc)

        await notif_engine.dispose()
        logger.info("[RiskAlert] Alertas enviadas correctamente.")

    except Exception as exc:
        logger.error("[RiskAlert] Error en send_at_risk_alerts: %s", exc)


# ─── Orquestador principal ────────────────────────────────────────────────────

# Estado persistente entre ejecuciones del cron — solo notifica cuando el
# estado cambia (de OK → FAIL o de FAIL → OK) para no spamear el grupo.
_prev_all_ok: bool | None = None
_prev_failure_names: set[str] = set()


async def run_monitoring_cycle() -> MonitoringReport:
    """
    Ejecuta todos los checks en paralelo, construye el reporte y envía
    al grupo de WhatsApp si hay cambios respecto al ciclo anterior.
    """
    global _prev_all_ok, _prev_failure_names

    # Todos los checks en paralelo + crisis check
    results = await asyncio.gather(
        _check_backend(),
        _check_database(),
        _check_waha(),
        _check_frontend(),
        _check_rag(),
        return_exceptions=True,
    )

    # Crisis de clase (corre en cada ciclo, independiente del informe de servicios)
    asyncio.create_task(check_class_crisis())

    # Alertas semanales a estudiantes ALTO (solo los lunes)
    asyncio.create_task(send_at_risk_alerts())

    # Si un check lanzó excepción lo convertimos en ServiceStatus fallido
    statuses: list[ServiceStatus] = []
    names = ["Backend API", "Base de datos", "WAHA (WhatsApp)", "Frontend", "RAG API"]
    for name, result in zip(names, results):
        if isinstance(result, ServiceStatus):
            statuses.append(result)
        else:
            statuses.append(ServiceStatus(name=name, ok=False, detail=str(result)[:120]))

    report = MonitoringReport(services=statuses)
    current_failure_names = {s.name for s in report.failures}

    # Decidir si notificar:
    # 1. Nuevas fallas que antes no existían
    # 2. Recuperaciones (algo que antes fallaba ahora está bien)
    new_failures    = current_failure_names - _prev_failure_names
    recovered       = _prev_failure_names - current_failure_names
    state_changed   = bool(new_failures or recovered)
    first_run       = _prev_all_ok is None

    should_notify = first_run or state_changed or (not report.all_ok and bool(current_failure_names))

    # En el primer arranque solo notificamos si hay fallas
    if first_run and report.all_ok:
        should_notify = False

    if should_notify:
        msg = report.to_whatsapp_text()
        logger.info("[Monitor] Enviando reporte al grupo (%d fallas)", len(report.failures))
        await _send_to_group(msg)

    _prev_all_ok = report.all_ok
    _prev_failure_names = current_failure_names

    status_str = "OK" if report.all_ok else f"FALLAS: {', '.join(current_failure_names)}"
    logger.info("[Monitor] Ciclo completado — %s", status_str)

    return report


# ─── Loop del cron ────────────────────────────────────────────────────────────

async def start_monitoring_loop() -> None:
    """
    Bucle infinito que ejecuta run_monitoring_cycle() cada
    MONITORING_INTERVAL_MINUTES minutos. Se lanza como asyncio.Task
    en el lifespan de FastAPI.
    """
    interval_seconds = settings.MONITORING_INTERVAL_MINUTES * 60
    logger.info(
        "[Monitor] Cron iniciado — intervalo: %d min | grupo: %s",
        settings.MONITORING_INTERVAL_MINUTES,
        settings.WAHA_MONITORING_GROUP or "NO CONFIGURADO",
    )

    # Primera ejecución al arrancar (con un pequeño retardo para que el
    # servidor termine de inicializarse)
    await asyncio.sleep(15)

    while True:
        try:
            await run_monitoring_cycle()
        except Exception as exc:
            logger.error("[Monitor] Error inesperado en el ciclo: %s", exc)
        await asyncio.sleep(interval_seconds)
