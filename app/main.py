"""
Academic Risk Predictor Backend
Entry Point de la aplicación FastAPI
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.core.config import settings
from app.api.v1.endpoints import (
    prediction, health, users, auth,
    notifications, programs, courses, enrollments,
)
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
    print("="*80 + "\n")
    yield
    print("\n" + "="*80)
    print("👋 CERRANDO SISTEMA DE PREDICCIÓN DE RIESGO ACADÉMICO")
    await engine.dispose()
    print("="*80 + "\n")


app = FastAPI(
    title=settings.API_TITLE,
    description=settings.API_DESCRIPTION,
    version=settings.API_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
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
app.include_router(notifications.router, prefix="/api/v1", tags=["Notificaciones"])


@app.get("/")
async def root():
    return {
        "mensaje": "API de Predicción de Riesgo Académico",
        "version": settings.API_VERSION,
        "documentacion": {"swagger": "/docs", "redoc": "/redoc"},
    }
