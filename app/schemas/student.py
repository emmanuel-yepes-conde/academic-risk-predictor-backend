"""
Schemas de Estudiante - DTOs (Data Transfer Objects)
Define los contratos de datos de entrada y salida para el API
"""

from pydantic import BaseModel, Field
from typing import Dict, List


class StudentInput(BaseModel):
    """
    DTO de Entrada - Datos del estudiante para predicción
    Equivalente a Zod Schema en TypeScript
    """
    promedio_asistencia: float = Field(
        ..., 
        ge=0, 
        le=100, 
        description="Porcentaje de asistencia (0-100)"
    )
    promedio_seguimiento: float = Field(
        ..., 
        ge=0, 
        le=5.0, 
        description="Nota promedio de quizzes y tareas (0-5)"
    )
    nota_parcial_1: float = Field(
        ..., 
        ge=0, 
        le=5.0, 
        description="Nota del primer parcial (Variable crítica, 0-5)"
    )
    inicios_sesion_plataforma: int = Field(
        ..., 
        ge=0, 
        description="Total de logins en el LMS"
    )
    uso_tutorias: int = Field(
        ..., 
        ge=0, 
        le=10, 
        description="Número de tutorías utilizadas (0-10)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "promedio_asistencia": 78.5,
                "promedio_seguimiento": 3.1,
                "nota_parcial_1": 2.8,
                "inicios_sesion_plataforma": 45,
                "uso_tutorias": 2
            }
        }


class PredictionOutput(BaseModel):
    """
    DTO de Salida - Resultado de la predicción
    """
    probabilidad_riesgo: float = Field(
        ...,
        ge=0,
        le=1,
        description="Probabilidad de riesgo (0-1)"
    )
    porcentaje_riesgo: float = Field(
        ...,
        ge=0,
        le=100,
        description="Porcentaje de riesgo (0-100)"
    )
    nivel_riesgo: str = Field(
        ...,
        description="Nivel de riesgo: ALTO, MEDIO, BAJO"
    )
    analisis_ia: str = Field(
        ...,
        description="Análisis personalizado con consejos"
    )
    datos_radar: Dict = Field(
        ...,
        description="Datos para gráfico de radar comparativo"
    )
    detalles_matematicos: Dict = Field(
        ...,
        description="Detalles del cálculo matemático (transparencia)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "probabilidad_riesgo": 0.65,
                "porcentaje_riesgo": 65.0,
                "nivel_riesgo": "MEDIO",
                "analisis_ia": "⚠️ **SITUACIÓN DE RIESGO MODERADO**...",
                "datos_radar": {
                    "labels": ["Asistencia (%)", "Seguimiento", "Parcial 1", "Logins", "Tutorías"],
                    "estudiante": [78.5, 3.1, 2.8, 45, 2],
                    "promedio_aprobado": [85.0, 3.8, 3.5, 50, 5]
                },
                "detalles_matematicos": {
                    "formula_logit": "z = β₀ + Σ(βᵢ × xᵢ)",
                    "valor_z": 0.619,
                    "coeficientes": [-0.35, 0.28, 0.52, 0.15, -0.22]
                }
            }
        }


class ChatInput(BaseModel):
    """
    DTO de Entrada - Datos para el chat consejero
    """
    pregunta: str = Field(
        ...,
        description="Pregunta del estudiante"
    )
    datos_estudiante: StudentInput = Field(
        ...,
        description="Datos actuales del estudiante"
    )
    prediccion_actual: Dict = Field(
        None,
        description="Predicción actual si existe"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "pregunta": "¿Cómo puedo mejorar mi nota?",
                "datos_estudiante": {
                    "promedio_asistencia": 78.5,
                    "promedio_seguimiento": 3.1,
                    "nota_parcial_1": 2.8,
                    "inicios_sesion_plataforma": 45,
                    "uso_tutorias": 2
                },
                "prediccion_actual": {
                    "porcentaje_riesgo": 65.0
                }
            }
        }


class ChatOutput(BaseModel):
    """
    DTO de Salida - Respuesta del chat
    """
    respuesta: str = Field(
        ...,
        description="Respuesta generada por el consejero virtual"
    )

