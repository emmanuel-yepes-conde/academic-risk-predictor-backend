"""
Configuración de la Aplicación
Centraliza todas las configuraciones y variables de entorno
"""

import os
from typing import List, Union, Annotated
from pydantic_settings import BaseSettings
from pydantic import Field, BeforeValidator


def parse_cors_origins(v):
    """
    Convierte CORS_ORIGINS de string a lista si es necesario.
    Permite usar CORS_ORIGINS=* en .env en lugar de CORS_ORIGINS=["*"]
    """
    if isinstance(v, str):
        # Si es "*", convertir a lista con un elemento
        if v.strip() == "*":
            return ["*"]
        # Si es una lista separada por comas, dividir
        if "," in v:
            return [origin.strip() for origin in v.split(",")]
        # Si es un solo origen, convertir a lista
        return [v.strip()]
    return v


class Settings(BaseSettings):
    """
    Configuración de la aplicación usando Pydantic BaseSettings
    Las variables se cargan desde el entorno o archivo .env
    """
    
    # Configuración del API
    API_TITLE: str = "API de Predicción de Riesgo Académico"
    API_DESCRIPTION: str = "Sistema predictivo basado en Regresión Logística con análisis de IA"
    API_VERSION: str = "1.0.0"
    
    # Configuración del servidor
    HOST: str = Field(default="0.0.0.0", description="Host del servidor")
    PORT: int = Field(default=8000, description="Puerto del servidor")
    
    # Configuración CORS - Usa BeforeValidator para permitir string o lista
    CORS_ORIGINS: Annotated[List[str], BeforeValidator(parse_cors_origins)] = Field(
        default=["*"],
        description="Orígenes permitidos para CORS"
    )
    CORS_ALLOW_CREDENTIALS: bool = False
    CORS_ALLOW_METHODS: List[str] = ["*"]
    CORS_ALLOW_HEADERS: List[str] = ["*"]
    
    # Rutas de archivos ML
    MODEL_PATH: str = Field(
        default="ml_models/modelo_logistico.joblib",
        description="Ruta al archivo del modelo"
    )
    SCALER_PATH: str = Field(
        default="ml_models/scaler.joblib",
        description="Ruta al archivo del scaler"
    )
    DATASET_PATH: str = Field(
        default="datasets/dataset_estudiantes_decimal.csv",
        description="Ruta al dataset de entrenamiento"
    )
    
    # Configuración de logging
    LOG_LEVEL: str = Field(default="info", description="Nivel de logging")
    
    # Configuración de umbrales de riesgo
    UMBRAL_RIESGO_ALTO: float = Field(default=0.7, ge=0, le=1)
    UMBRAL_RIESGO_MEDIO: float = Field(default=0.4, ge=0, le=1)
    
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
        "extra": "ignore",
        # Deshabilitar el parsing JSON automático para listas desde .env
        "env_parse_none_str": None,
    }
    
    def get_base_path(self) -> str:
        """Retorna el path base del proyecto"""
        return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    def get_full_model_path(self) -> str:
        """Retorna la ruta completa al modelo"""
        return os.path.join(self.get_base_path(), self.MODEL_PATH)
    
    def get_full_scaler_path(self) -> str:
        """Retorna la ruta completa al scaler"""
        return os.path.join(self.get_base_path(), self.SCALER_PATH)
    
    def get_full_dataset_path(self) -> str:
        """Retorna la ruta completa al dataset"""
        return os.path.join(self.get_base_path(), self.DATASET_PATH)


# Instancia global de configuración
settings = Settings()

