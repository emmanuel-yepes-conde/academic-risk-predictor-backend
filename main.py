"""
Academic Risk Predictor Backend - Entry Point
Este archivo mantiene compatibilidad con scripts de despliegue
que esperan main.py en la raíz, pero importa desde la nueva estructura modular.

Desarrollado como proyecto final - Semestre 2025-II
Refactorizado siguiendo Clean Architecture (Arquitectura en Capas)
"""

import os

# Importar la aplicación desde la nueva estructura modular
from app.core.config import settings
from app.main import app

# Mantener compatibilidad con el punto de entrada original
if __name__ == "__main__":
    import uvicorn
    
    # Obtener puerto desde variable de entorno (para despliegue) o usar 8000 por defecto
    port = int(os.getenv("PORT", settings.PORT))
    
    print("🎓 academic risk predictor back")
    print(f"🌐 Host: {settings.HOST}")
    print(f"🌐 Puerto: {port}")
    
    uvicorn.run(
        "app.main:app",  # Importante: apuntar a app.main:app
        host=settings.HOST,
        port=port,
        reload=False,  # Desactivar reload en producción
        log_level=settings.LOG_LEVEL,
    )
