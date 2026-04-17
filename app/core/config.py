"""
Configuración de la Aplicación
Centraliza todas las configuraciones y variables de entorno
"""

import os
import uuid
from typing import List, Union, Annotated, Optional
from pydantic_settings import BaseSettings
from pydantic import Field, BeforeValidator, model_validator


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

    # Configuración de base de datos
    DB_USER: str = Field(default="mpra_user", description="Usuario de la base de datos")
    DB_PASSWORD: str = Field(default="mpra_secret", description="Contraseña de la base de datos")
    DB_HOST: str = Field(default="localhost", description="Host de la base de datos")
    DB_PORT: int = Field(default=5432, description="Puerto de la base de datos")
    DB_NAME: str = Field(default="mpra_db", description="Nombre de la base de datos")
    DATABASE_URL: Optional[str] = Field(default=None, description="URL de conexión a la base de datos")

    # Universidad por defecto para migración de datos existentes
    DEFAULT_UNIVERSITY_ID: uuid.UUID | None = Field(
        default=None,
        description="UUID de la universidad por defecto para migración de datos existentes"
    )

    # Configuración JWT
    JWT_SECRET_KEY: str = Field(..., description="Clave secreta para firmar tokens JWT")
    JWT_ALGORITHM: str = Field(default="HS256", description="Algoritmo de firma JWT")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30, description="Tiempo de expiración del access token en minutos")
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7, description="Tiempo de expiración del refresh token en días")

    # Pool de conexiones
    DB_POOL_MIN: int = Field(default=5, description="Tamaño mínimo del pool de conexiones")
    DB_POOL_MAX: int = Field(default=20, description="Tamaño máximo del pool de conexiones")
    DB_ECHO: bool = Field(default=False, description="Habilitar logging SQL de SQLAlchemy")

    @model_validator(mode='before')
    @classmethod
    def build_database_url(cls, values: dict) -> dict:
        """Construye DATABASE_URL automáticamente si no está definida en el entorno."""
        if not values.get("DATABASE_URL"):
            user = values.get("DB_USER", "mpra_user")
            password = values.get("DB_PASSWORD", "mpra_secret")
            host = values.get("DB_HOST", "localhost")
            port = values.get("DB_PORT", 5432)
            name = values.get("DB_NAME", "mpra_db")
            values["DATABASE_URL"] = (
                f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{name}"
            )
        return values

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

