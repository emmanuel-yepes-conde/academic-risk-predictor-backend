"""
Health Check Endpoint
Verifica la disponibilidad del servicio y la conectividad con la base de datos.
"""

import asyncio
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import settings
from app.infrastructure.database import engine

router = APIRouter()

DB_TIMEOUT_SECONDS = 2


@router.get("/health")
async def health_check():
    """
    Verifica el estado del servicio y la conectividad con la base de datos.

    Returns:
        - HTTP 200 con status "healthy" si la DB responde dentro del timeout.
        - HTTP 503 con status "unhealthy" si la DB no responde o supera el timeout.
    """
    from app.services.ml_service import risk_service

    db_status = "connected"
    overall_status = "healthy"
    http_status = 200

    try:
        async def _ping():
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))

        await asyncio.wait_for(_ping(), timeout=DB_TIMEOUT_SECONDS)

    except asyncio.TimeoutError:
        db_status = "timeout"
        overall_status = "unhealthy"
        http_status = 503

    except Exception:
        db_status = "unreachable"
        overall_status = "unhealthy"
        http_status = 503

    body = {
        "status": overall_status,
        "database": db_status,
        "modelo_cargado": risk_service.model is not None,
        "scaler_cargado": risk_service.scaler is not None,
        "promedio_aprobados_cargado": risk_service.promedio_estudiantes_aprobados is not None,
        "version": settings.API_VERSION,
    }

    return JSONResponse(content=body, status_code=http_status)
