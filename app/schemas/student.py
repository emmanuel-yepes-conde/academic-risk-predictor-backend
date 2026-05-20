"""Schemas de entrada/salida para predicción de riesgo académico."""

from __future__ import annotations

from typing import Dict, Literal

from pydantic import BaseModel, Field, model_validator


class StudentInput(BaseModel):
    """Datos de notas para predecir riesgo."""

    nota_corte_1: float = Field(..., ge=0, le=5, description="Nota corte 1 (0-5)")
    nota_corte_2: float = Field(..., ge=0, le=5, description="Nota corte 2 (0-5)")
    nota_corte_final: float = Field(..., ge=0, le=5, description="Nota corte final (0-5)")
    nota_total: float | None = Field(
        default=None,
        ge=0,
        le=5,
        description="Nota total ponderada (0-5). Si no se envía, se calcula desde cortes.",
    )

    @model_validator(mode="after")
    def set_total_if_missing(self):
        if self.nota_total is None:
            self.nota_total = round(
                (self.nota_corte_1 * 0.30)
                + (self.nota_corte_2 * 0.30)
                + (self.nota_corte_final * 0.40),
                2,
            )
        return self

    class Config:
        json_schema_extra = {
            "example": {
                "nota_corte_1": 3.8,
                "nota_corte_2": 3.4,
                "nota_corte_final": 4.1,
                "nota_total": 3.79,
            }
        }


class PredictionOutput(BaseModel):
    probabilidad_riesgo: float = Field(..., ge=0, le=1)
    porcentaje_riesgo: float = Field(..., ge=0, le=100)
    nivel_riesgo: str = Field(..., description="ALTO, MEDIO, BAJO")
    analisis_ia: str
    datos_radar: Dict
    detalles_matematicos: Dict
    # Predicción parcial: True cuando faltan cortes y se usaron valores imputados
    is_partial: bool = Field(default=False, description="True si la predicción usa notas imputadas por falta de datos")
    cortes_disponibles: int = Field(default=3, description="Número de cortes con nota real (0-3)")


class CohortRiskInput(BaseModel):
    cohort_key: Literal["first_cohort", "second_cohort", "third_cohort"] = Field(
        ...,
        description="Cohorte a evaluar",
    )
    nota_parcial: float = Field(..., ge=0, le=5, description="Nota del parcial del cohorte (0-5)")
    promedio_seguimiento: float = Field(
        ..., ge=0, le=5, description="Promedio de actividades de seguimiento del cohorte (0-5)"
    )
    porcentaje_asistencia: float = Field(
        ..., ge=0, le=100, description="Porcentaje de asistencia del cohorte (0-100)"
    )


class CohortRiskOutput(BaseModel):
    cohort_key: str
    cohort_name: str
    probabilidad_riesgo: float = Field(..., ge=0, le=1)
    porcentaje_riesgo: float = Field(..., ge=0, le=100)
    nivel_riesgo: str = Field(..., description="ALTO, MEDIO, BAJO")
    datos_cohorte: Dict
    detalles_modelo: Dict


class ChatInput(BaseModel):
    pregunta: str
    datos_estudiante: StudentInput
    prediccion_actual: Dict | None = None


class ChatOutput(BaseModel):
    respuesta: str
