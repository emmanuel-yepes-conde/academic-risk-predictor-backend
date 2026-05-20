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
from app.infrastructure.database import get_session as get_db

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


class JobTestPayload(BaseModel):
    email: str | None = None
    phone: str | None = None


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

    # Actualizar el scheduler en caliente si cambió cron_expr o enabled
    if "cron_expr" in updates or "enabled" in updates:
        try:
            from app.infrastructure.database import engine
            from app.services.scheduler_service import reload_job
            await reload_job(engine, job_id)
        except Exception as _reload_err:
            logger.warning("[Jobs] No se pudo recargar scheduler para %s: %s", job_id, _reload_err)

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


@router.post(
    "/admin/jobs/{job_id}/test",
    summary="Enviar notificación de prueba de un job",
    tags=["Admin — Jobs"],
)
async def test_job(
    job_id: str,
    body: JobTestPayload,
    current_user=Depends(require_roles(RoleEnum.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """
    Envía una notificación de prueba al email y/o teléfono indicados,
    simulando lo que haría el job cuando se ejecute en producción.
    """
    job = await _get_job(job_id, db)

    if not body.email and not body.phone:
        raise HTTPException(
            status_code=422,
            detail="Debes proporcionar al menos un email o número de teléfono para la prueba",
        )

    sent_channels: list[str] = []

    try:
        # ── Email de prueba ──────────────────────────────────────────────────
        if body.email:
            from app.services.acs_email_service import _dispatch
            subject = f"[PRUEBA] {job['name']} — Academic Risk"
            html = f"""<!DOCTYPE html><html><body
              style="margin:0;padding:24px;background:#f8fafc;
                     font-family:Arial,Helvetica,sans-serif;">
              <div style="max-width:520px;margin:0 auto;background:#fff;
                          border-radius:12px;padding:32px;
                          box-shadow:0 2px 12px rgba(0,0,0,0.08);">
                <div style="background:#1E3932;border-radius:8px;
                            padding:14px 20px;margin-bottom:24px;">
                  <span style="color:#fff;font-size:15px;font-weight:700;">
                    Academic <span style="color:#d4e9e2;">Risk</span>
                    <span style="background:#D97706;color:#fff;font-size:10px;
                                 font-weight:700;padding:3px 10px;border-radius:10px;
                                 margin-left:10px;letter-spacing:0.5px;">PRUEBA</span>
                  </span>
                </div>
                <h2 style="color:#1E3932;font-size:17px;margin:0 0 8px 0;">
                  Notificación de prueba
                </h2>
                <p style="color:#4a5568;font-size:14px;line-height:1.7;margin:0 0 16px 0;">
                  Este es un mensaje de prueba para el job
                  <strong>{job['name']}</strong>.
                </p>
                <div style="background:#f0fdf4;border-left:4px solid #00754A;
                            border-radius:6px;padding:14px 16px;">
                  <p style="margin:0;font-size:13px;color:#1E3932;">
                    <strong>Job:</strong> {job['name']}<br/>
                    <strong>Tipo:</strong> {job['job_type']}<br/>
                    <strong>Canales:</strong> {", ".join(job.get("channels") or ["—"])}<br/>
                    <strong>Descripción:</strong> {job['description']}
                  </p>
                </div>
                <hr style="border:none;border-top:1px solid #e2e8f0;margin:20px 0 0 0"/>
                <p style="color:#9ca3af;font-size:11px;margin:14px 0 0 0;">
                  Enviado desde el panel de administración de Academic Risk
                </p>
              </div>
            </body></html>"""
            ok = await _dispatch(to_email=body.email, subject=subject, html_content=html)
            if ok:
                sent_channels.append(f"email → {body.email}")
            else:
                logger.warning("[Jobs/test] Email falló para %s", body.email)

        # ── WhatsApp de prueba ───────────────────────────────────────────────
        if body.phone:
            try:
                import httpx
                numero = body.phone.strip().replace(" ", "").replace("-", "").replace("+", "")
                if not numero.startswith("57") and len(numero) == 10:
                    numero = f"57{numero}"
                texto = (
                    f"🧪 *[PRUEBA] {job['name']} — Academic Risk*\n\n"
                    f"Este es un mensaje de prueba para el job "
                    f"*{job['name']}*.\n\n"
                    f"📋 *Descripción:* {job['description']}\n"
                    f"📡 *Canales:* {', '.join(job.get('channels') or ['—'])}\n\n"
                    f"_Enviado desde el panel de administración_"
                )
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.post(
                        f"{settings.WAHA_URL.rstrip('/')}/api/sendText",
                        json={"chatId": f"{numero}@c.us", "text": texto, "session": "default"},
                        headers={"X-Api-Key": settings.WAHA_API_KEY},
                    )
                if resp.status_code < 400:
                    sent_channels.append(f"whatsapp → {body.phone}")
                else:
                    logger.warning("[Jobs/test] WhatsApp respondió %s", resp.status_code)
            except Exception as wa_exc:
                logger.warning("[Jobs/test] WhatsApp falló: %s", wa_exc)

    except Exception as exc:
        logger.error("[Jobs/test] Error en prueba de %s: %s", job_id, exc)
        raise HTTPException(status_code=500, detail=str(exc))

    if not sent_channels:
        raise HTTPException(
            status_code=502,
            detail="No se pudo enviar la prueba por ningún canal. Verifica la configuración.",
        )

    return {
        "ok": True,
        "message": f"Prueba enviada correctamente → {', '.join(sent_channels)}",
    }
