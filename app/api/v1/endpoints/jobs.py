"""
Admin — gestión de jobs y disparadores automáticos.

Endpoints:
  GET  /admin/jobs              → lista todos los jobs/triggers
  PATCH /admin/jobs/{id}        → edita cron_expr, name, description o enabled
  POST  /admin/jobs/{id}/trigger → ejecuta el job manualmente ahora
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies.auth import get_current_user, require_roles
from app.core.config import settings
from app.domain.enums import RoleEnum
from app.infrastructure.database import get_db

logger = logging.getLogger(__name__)
router = APIRouter()

CurrentUser = dict  # simplificado; el dep real devuelve el objeto User


# ─── Schemas ──────────────────────────────────────────────────────────────────

class JobRead(BaseModel):
    id:             str
    name:           str
    description:    str
    job_type:       str          # 'cron' | 'trigger'
    cron_expr:      str | None
    trigger_event:  str | None
    channels:       list[str]
    enabled:        bool
    last_run_at:    datetime | None

    class Config:
        from_attributes = True


class JobUpdate(BaseModel):
    name:        str | None = None
    description: str | None = None
    cron_expr:   str | None = None
    enabled:     bool | None = None


# ─── Helpers ──────────────────────────────────────────────────────────────────

async def _get_job(job_id: str, db: AsyncSession) -> dict:
    row = await db.execute(
        text("SELECT * FROM job_configs WHERE id = :id"),
        {"id": job_id},
    )
    job = row.mappings().first()
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' no encontrado")
    return dict(job)


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.get(
    "/admin/jobs",
    response_model=list[JobRead],
    summary="Listar todos los jobs y disparadores",
    tags=["Admin — Jobs"],
)
async def list_jobs(
    current_user=Depends(require_roles(RoleEnum.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    rows = await db.execute(
        text("SELECT * FROM job_configs ORDER BY job_type DESC, id")
    )
    return [dict(r) for r in rows.mappings().all()]


@router.patch(
    "/admin/jobs/{job_id}",
    response_model=JobRead,
    summary="Editar configuración de un job",
    tags=["Admin — Jobs"],
)
async def update_job(
    job_id: str,
    body: JobUpdate,
    current_user=Depends(require_roles(RoleEnum.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    await _get_job(job_id, db)  # verifica que exista

    updates: dict[str, object] = {}
    if body.name        is not None: updates["name"]        = body.name
    if body.description is not None: updates["description"] = body.description
    if body.cron_expr   is not None: updates["cron_expr"]   = body.cron_expr
    if body.enabled     is not None: updates["enabled"]     = body.enabled

    if not updates:
        return await _get_job(job_id, db)

    set_clause = ", ".join(f"{k} = :{k}" for k in updates)
    updates["id"] = job_id
    await db.execute(
        text(f"UPDATE job_configs SET {set_clause} WHERE id = :id"),
        updates,
    )
    await db.commit()
    return await _get_job(job_id, db)


@router.post(
    "/admin/jobs/{job_id}/trigger",
    summary="Ejecutar un job manualmente ahora",
    tags=["Admin — Jobs"],
)
async def trigger_job(
    job_id: str,
    current_user=Depends(require_roles(RoleEnum.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    job = await _get_job(job_id, db)

    if not job["enabled"]:
        raise HTTPException(status_code=400, detail="El job está deshabilitado")

    result_msg = "Ejecutado correctamente"

    try:
        if job_id == "monitoring":
            from app.services.monitoring_service import run_monitoring_cycle
            import asyncio
            asyncio.create_task(run_monitoring_cycle())
            result_msg = "Ciclo de monitoreo iniciado en segundo plano"

        elif job_id == "risk-alerts":
            from app.services.monitoring_service import send_at_risk_alerts
            import asyncio
            # Forzar ejecución ignorando el día de la semana
            from app.services import monitoring_service as ms
            ms._last_risk_alert_day = None
            asyncio.create_task(send_at_risk_alerts())
            result_msg = "Alertas de riesgo iniciadas en segundo plano"

        elif job_id == "class-crisis":
            from app.services.monitoring_service import check_class_crisis
            import asyncio
            asyncio.create_task(check_class_crisis())
            result_msg = "Verificación de crisis de clase iniciada en segundo plano"

        else:
            # Triggers y jobs sin implementación de disparo manual
            result_msg = f"El job '{job['name']}' se activa por eventos y no puede dispararse manualmente"

    except Exception as exc:
        logger.error("[Jobs] Error disparando %s: %s", job_id, exc)
        raise HTTPException(status_code=500, detail=str(exc))

    # Actualizar last_run_at
    await db.execute(
        text("UPDATE job_configs SET last_run_at = NOW() WHERE id = :id"),
        {"id": job_id},
    )
    await db.commit()

    return {"ok": True, "message": result_msg}
