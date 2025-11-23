"""
Academic Risk Predictor Backend
Entry Point de la aplicación FastAPI
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.v1.endpoints import prediction


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
    print("✅ SISTEMA INICIADO Y LISTO PARA RECIBIR PETICIONES")
    print("="*80 + "\n")
    
    yield
    
    # Shutdown
    print("\n" + "="*80)
    print("👋 CERRANDO SISTEMA DE PREDICCIÓN DE RIESGO ACADÉMICO")
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
# REGISTRAR ROUTERS
# ============================================================================

# Incluir endpoints de predicción
app.include_router(
    prediction.router,
    prefix="/api/v1",
    tags=["Predicción"]
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


@app.get("/health")
async def health_check():
    """Endpoint para verificar el estado del servicio"""
    from app.services.ml_service import risk_service
    
    return {
        "status": "healthy",
        "modelo_cargado": risk_service.model is not None,
        "scaler_cargado": risk_service.scaler is not None,
        "promedio_aprobados_cargado": risk_service.promedio_estudiantes_aprobados is not None,
        "version": settings.API_VERSION
    }

