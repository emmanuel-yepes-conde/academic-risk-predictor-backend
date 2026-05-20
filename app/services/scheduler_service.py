"""
scheduler_service — cron jobs reales usando APScheduler.

Lee la configuración desde la tabla `job_configs` (habilitados, cron_expr) y
programa los tres jobs de tipo 'cron':
  - monitoring   → manejado por monitoring_service.start_monitoring_loop()
                   (no se duplica aquí; APScheduler solo gestiona los otros dos)
  - risk-alerts  → send_at_risk_alerts()    cron expr: "0 8 * * 1"
  - class-crisis → check_class_crisis()     cron expr: "*/5 * * * *"

Cuando el admin cambia cron_expr o enabled desde el panel, llamar a:
  reload_job(job_id)  — recarga ese job desde DB y actualiza el scheduler.
"""

from __future__ import annotations

import logging
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

# Scheduler global (singleton)
_scheduler: Optional[AsyncIOScheduler] = None


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(timezone="America/Bogota")
    return _scheduler


# ─── Funciones ejecutadas por cada job ────────────────────────────────────────

async def _run_risk_alerts() -> None:
    try:
        from app.services import monitoring_service as ms
        ms._last_risk_alert_day = None          # forzar ejecución
        await ms.send_at_risk_alerts()
        logger.info("[scheduler] risk-alerts ejecutado")
    except Exception as exc:
        logger.error("[scheduler] risk-alerts falló: %s", exc, exc_info=True)


async def _run_class_crisis() -> None:
    try:
        from app.services.monitoring_service import check_class_crisis
        await check_class_crisis()
        logger.info("[scheduler] class-crisis ejecutado")
    except Exception as exc:
        logger.error("[scheduler] class-crisis falló: %s", exc, exc_info=True)


# Mapeo job_id → coroutine function
_JOB_FN = {
    "risk-alerts":  _run_risk_alerts,
    "class-crisis": _run_class_crisis,
}


# ─── API pública ──────────────────────────────────────────────────────────────

async def start_scheduler(engine) -> AsyncIOScheduler:
    """
    Carga job_configs desde la BD, programa los jobs habilitados y arranca el scheduler.
    Debe llamarse desde el lifespan de FastAPI después de crear el engine.
    """
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession

    scheduler = get_scheduler()
    if scheduler.running:
        return scheduler

    async with AsyncSession(engine) as session:
        rows = await session.execute(
            text(
                "SELECT id, name, cron_expr, enabled "
                "FROM job_configs WHERE job_type = 'cron'"
            )
        )
        db_jobs = [dict(r) for r in rows.mappings().all()]

    for job in db_jobs:
        job_id = job["id"]
        if job_id == "monitoring":
            continue  # ya lo maneja start_monitoring_loop()
        if not job.get("enabled"):
            logger.info("[scheduler] job '%s' deshabilitado — omitido", job_id)
            continue
        cron_expr = job.get("cron_expr")
        if not cron_expr or job_id not in _JOB_FN:
            continue
        _schedule_job(scheduler, job_id, cron_expr)

    scheduler.start()
    logger.info("[scheduler] APScheduler iniciado con %d jobs", len(scheduler.get_jobs()))
    return scheduler


def _schedule_job(scheduler: AsyncIOScheduler, job_id: str, cron_expr: str) -> None:
    """Agrega o reemplaza un job en el scheduler."""
    fn = _JOB_FN.get(job_id)
    if fn is None:
        return
    try:
        trigger = CronTrigger.from_crontab(cron_expr, timezone="America/Bogota")
        # Reemplazar si ya existe
        if scheduler.get_job(job_id):
            scheduler.reschedule_job(job_id, trigger=trigger)
            logger.info("[scheduler] job '%s' reprogramado → %s", job_id, cron_expr)
        else:
            scheduler.add_job(fn, trigger=trigger, id=job_id, replace_existing=True)
            logger.info("[scheduler] job '%s' programado → %s", job_id, cron_expr)
    except Exception as exc:
        logger.error("[scheduler] no se pudo programar '%s': %s", job_id, exc)


async def reload_job(engine, job_id: str) -> None:
    """
    Re-lee un job de la BD y actualiza el scheduler en caliente.
    Llamar desde el endpoint PATCH /admin/jobs/{id} después de guardar.
    """
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession

    if job_id == "monitoring":
        return  # no gestionado por APScheduler

    scheduler = get_scheduler()
    if not scheduler.running:
        return

    async with AsyncSession(engine) as session:
        row = await session.execute(
            text("SELECT id, cron_expr, enabled FROM job_configs WHERE id = :id"),
            {"id": job_id},
        )
        job = row.mappings().first()

    if not job:
        return

    if not job["enabled"]:
        # Deshabilitar: remover del scheduler si existe
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)
            logger.info("[scheduler] job '%s' eliminado del scheduler (deshabilitado)", job_id)
        return

    cron_expr = job.get("cron_expr")
    if cron_expr and job_id in _JOB_FN:
        _schedule_job(scheduler, job_id, cron_expr)


def stop_scheduler() -> None:
    scheduler = get_scheduler()
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("[scheduler] APScheduler detenido")
