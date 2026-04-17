"""
Academic Risk Predictor Backend
Entry Point de la aplicación FastAPI
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.core.config import settings
from app.api.v1.endpoints import campuses, prediction, health, users, universities, auth
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
    """
    Maneja los eventos de ciclo de vida de la aplicación.
    El código antes del yield se ejecuta al iniciar (startup).
    El código después del yield se ejecuta al cerrar (shutdown).
    """
    # Startup
    print("\n" + "="*80)
    print("🚀 INICIANDO SISTEMA DE PREDICCIÓN DE RIESGO ACADÉMICO")
    print("="*80 + "\n")
    # Inicializar el pool de conexiones a la base de datos
    async with engine.connect():
        pass
    print("✅ SISTEMA INICIADO Y LISTO PARA RECIBIR PETICIONES")
    print("="*80 + "\n")
    
    yield
    
    # Shutdown
    print("\n" + "="*80)
    print("👋 CERRANDO SISTEMA DE PREDICCIÓN DE RIESGO ACADÉMICO")
    # Cerrar todas las conexiones del pool
    await engine.dispose()
    print("="*80 + "\n")


# Crear instancia de FastAPI con lifespan
app = FastAPI(
    title=settings.API_TITLE,
    description=settings.API_DESCRIPTION,
    version=settings.API_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Configuración CORS - Permite peticiones desde el Frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=settings.CORS_ALLOW_METHODS,
    allow_headers=settings.CORS_ALLOW_HEADERS,
)


# ============================================================================
# EXCEPTION HANDLERS — Auth / Token errors
# ============================================================================

@app.exception_handler(AuthenticationError)
async def authentication_error_handler(request: Request, exc: AuthenticationError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message},
    )


@app.exception_handler(TokenExpiredError)
async def token_expired_error_handler(request: Request, exc: TokenExpiredError):
    return JSONResponse(
        status_code=401,
        content={"detail": exc.message},
    )


@app.exception_handler(InvalidTokenError)
async def invalid_token_error_handler(request: Request, exc: InvalidTokenError):
    return JSONResponse(
        status_code=401,
        content={"detail": exc.message},
    )


@app.exception_handler(AuthorizationError)
async def authorization_error_handler(request: Request, exc: AuthorizationError):
    return JSONResponse(
        status_code=403,
        content={"detail": exc.message},
    )


# ============================================================================
# REGISTRAR ROUTERS
# ============================================================================

# Incluir endpoints de autenticación
app.include_router(
    auth.router,
    prefix="/api/v1",
    tags=["Autenticación"],
)

# Incluir endpoints de predicción
app.include_router(
    prediction.router,
    prefix="/api/v1",
    tags=["Predicción"]
)

# Incluir endpoint de health check
app.include_router(
    health.router,
    tags=["Health"]
)

# Incluir endpoints de usuarios
app.include_router(
    users.router,
    prefix="/api/v1",
    tags=["Usuarios"]
)

# Incluir endpoints de universidades y jerarquía académica
app.include_router(
    universities.router,
    prefix="/api/v1",
    tags=["Universidades"]
)

# Incluir endpoints de campus y jerarquía campus → programa → curso
app.include_router(
    campuses.router,
    prefix="/api/v1",
    tags=["Campus"]
)


# ============================================================================
# ENDPOINTS GENERALES
# ============================================================================

@app.get("/")
async def root():
    """Endpoint raíz con información del API"""
    return {
        "mensaje": "API de Predicción de Riesgo Académico",
        "version": settings.API_VERSION,
        "endpoints": {
            "POST /api/v1/predict": "Realizar predicción de riesgo académico",
            "POST /api/v1/chat": "Chat con el consejero académico virtual",
            "GET /health": "Verificar estado del servicio"
        },
        "documentacion": {
            "swagger": "/docs",
            "redoc": "/redoc"
        },
        "proyecto": "Sistema de Predicción de Riesgo Académico - Semestre 2025-II"
    }


