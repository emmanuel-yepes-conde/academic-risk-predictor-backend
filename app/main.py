"""
Academic Risk Predictor Backend
Entry Point de la aplicación FastAPI
"""

import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.core.config import settings, parse_cors_origins
from app.api.v1.endpoints import (
    prediction, health, users, auth,
    notifications, programs, courses, enrollments, subjects, referrals,
    consents,
)
from app.api.v1.endpoints.templates import router as templates_router
from app.api.v1.endpoints.push import router as push_router
from app.api.v1.endpoints.attendance import router as attendance_router
from app.api.v1.endpoints.inapp_notifications import router as inapp_notif_router
from app.api.v1.endpoints.jobs import router as jobs_router

try:
    from app.api.v1.endpoints import waha_webhook as _waha_mod
    _waha_loaded = True
    print("[WAHA] Módulo cargado correctamente", flush=True)
except Exception as _waha_err:
    import traceback as _tb
    print(f"[WAHA] ERROR al importar módulo: {_waha_err}", flush=True)
    _tb.print_exc()
    _waha_loaded = False
from app.domain.exceptions import (
    AuthenticationError,
    AuthorizationError,
    InvalidTokenError,
    TokenExpiredError,
)
from app.infrastructure.database import engine


# ============================================================================
# EVENTOS DEL CICLO DE VIDA (Lifespan)
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("\n" + "="*80)
    print("INICIANDO SISTEMA DE PREDICCION DE RIESGO ACADEMICO")
    print("="*80 + "\n")
    async with engine.connect():
        pass
    print("✅ SISTEMA INICIADO Y LISTO PARA RECIBIR PETICIONES")

    # ── Cron de monitoreo de servicios ────────────────────────────────────
    _monitoring_task: asyncio.Task | None = None
    if settings.MONITORING_ENABLED:
        try:
            from app.services.monitoring_service import start_monitoring_loop
            _monitoring_task = asyncio.create_task(start_monitoring_loop())
            print(
                f"✅ MONITOR iniciado — intervalo {settings.MONITORING_INTERVAL_MINUTES} min "
                f"| grupo {settings.WAHA_MONITORING_GROUP or 'NO CONFIGURADO'}",
                flush=True,
            )
        except Exception as _mon_err:
            print(f"⚠️  MONITOR no pudo iniciarse: {_mon_err}", flush=True)
    else:
        print("⏸️  MONITOR desactivado (MONITORING_ENABLED=false)", flush=True)

    # ── APScheduler — cron jobs reales (risk-alerts, class-crisis) ──────────
    try:
        from app.services.scheduler_service import start_scheduler
        _ascheduler = await start_scheduler(engine)
        print(
            f"✅ SCHEDULER iniciado — {len(_ascheduler.get_jobs())} job(s) programados",
            flush=True,
        )
    except Exception as _sched_err:
        print(f"⚠️  SCHEDULER no pudo iniciarse: {_sched_err}", flush=True)
        _ascheduler = None

    print("="*80 + "\n")
    yield
    print("\n" + "="*80)
    print("👋 CERRANDO SISTEMA DE PREDICCIÓN DE RIESGO ACADÉMICO")
    if _monitoring_task and not _monitoring_task.done():
        _monitoring_task.cancel()
        try:
            await _monitoring_task
        except asyncio.CancelledError:
            pass
    try:
        from app.services.scheduler_service import stop_scheduler
        stop_scheduler()
    except Exception:
        pass
    await engine.dispose()
    print("="*80 + "\n")


app = FastAPI(
    title=settings.API_TITLE,
    description=settings.API_DESCRIPTION,
    version=settings.API_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    servers=settings.get_openapi_servers(),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=parse_cors_origins(settings.CORS_ORIGINS),
    allow_origin_regex=settings.CORS_ORIGIN_REGEX,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=settings.CORS_ALLOW_METHODS,
    allow_headers=settings.CORS_ALLOW_HEADERS,
)


# ============================================================================
# EXCEPTION HANDLERS
# ============================================================================

@app.exception_handler(AuthenticationError)
async def authentication_error_handler(request: Request, exc: AuthenticationError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})

@app.exception_handler(TokenExpiredError)
async def token_expired_error_handler(request: Request, exc: TokenExpiredError):
    return JSONResponse(status_code=401, content={"detail": exc.message})

@app.exception_handler(InvalidTokenError)
async def invalid_token_error_handler(request: Request, exc: InvalidTokenError):
    return JSONResponse(status_code=401, content={"detail": exc.message})

@app.exception_handler(AuthorizationError)
async def authorization_error_handler(request: Request, exc: AuthorizationError):
    return JSONResponse(status_code=403, content={"detail": exc.message})


# ============================================================================
# ROUTERS
# ============================================================================

app.include_router(auth.router,          prefix="/api/v1", tags=["Autenticación"])
app.include_router(prediction.router,    prefix="/api/v1", tags=["Predicción"])
app.include_router(health.router,                          tags=["Health"])
app.include_router(users.router,         prefix="/api/v1", tags=["Usuarios"])
app.include_router(programs.router,      prefix="/api/v1", tags=["Programas"])
app.include_router(courses.router,       prefix="/api/v1", tags=["Cursos"])
app.include_router(enrollments.router,   prefix="/api/v1", tags=["Inscripciones"])
app.include_router(subjects.router,      prefix="/api/v1", tags=["Materias"])
app.include_router(referrals.router,     prefix="/api/v1", tags=["Remisiones"])
app.include_router(notifications.router, prefix="/api/v1", tags=["Notificaciones"])
app.include_router(consents.router,      prefix="/api/v1", tags=["Consentimiento"])
app.include_router(templates_router,     prefix="/api/v1", tags=["templates"])
app.include_router(push_router,          prefix="/api/v1", tags=["Push Notifications"])
app.include_router(attendance_router,    prefix="/api/v1", tags=["Attendance"])
app.include_router(inapp_notif_router,   prefix="/api/v1", tags=["In-App Notifications"])
app.include_router(jobs_router,          prefix="/api/v1", tags=["Admin — Jobs"])
if _waha_loaded:
    app.include_router(_waha_mod.router, prefix="/api/v1", tags=["WhatsApp Bot"])

@app.get("/")
async def root():
    return {
        "mensaje": "API de Predicción de Riesgo Académico",
        "version": settings.API_VERSION,
        "base_url": settings.get_public_base_url(),
        "documentacion": {"swagger": "/docs", "redoc": "/redoc"},
    }
