"""Endpoints de predicción de riesgo académico."""

from __future__ import annotations

from typing import Optional
from uuid import UUID

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.services.consent_service import ConsentService
from app.application.services.ml_service import MLApplicationService
from app.infrastructure.database import get_session
from app.infrastructure.repositories.consent_repository import ConsentRepository
from app.schemas.student import (
    ChatInput,
    ChatOutput,
    CohortRiskInput,
    CohortRiskOutput,
    PredictionOutput,
    StudentInput,
)
from app.services.ml_service import AcademicRiskService, risk_service

router = APIRouter()


def get_ml_service() -> AcademicRiskService:
    return risk_service


def get_ml_application_service(
    session: AsyncSession = Depends(get_session),
    ml_service: AcademicRiskService = Depends(get_ml_service),
) -> MLApplicationService:
    consent_repo = ConsentRepository(session)
    consent_service = ConsentService(consent_repo)
    return MLApplicationService(ml_service, consent_service)


@router.post("/predict", response_model=PredictionOutput)
async def predecir_riesgo(
    estudiante: StudentInput,
    student_id: Optional[UUID] = None,
    service: AcademicRiskService = Depends(get_ml_service),
    ml_app_service: MLApplicationService = Depends(get_ml_application_service),
):
    """Predicción de riesgo usando únicamente notas por cohorte y total."""
    try:
        datos_estudiante = {
            "nota_corte_1": estudiante.nota_corte_1,
            "nota_corte_2": estudiante.nota_corte_2,
            "nota_corte_final": estudiante.nota_corte_final,
            "nota_total": estudiante.nota_total,
        }
        feature_vector = [
            estudiante.nota_corte_1,
            estudiante.nota_corte_2,
            estudiante.nota_corte_final,
            estudiante.nota_total,
        ]

        if student_id is not None:
            result = await ml_app_service.predict_with_consent_check(student_id, feature_vector)
        else:
            result = service.predict(feature_vector)

        probabilidad_riesgo = result["probability"]
        nivel_riesgo = result["risk_level"]
        features_scaled = np.array(result["scaled_features"])

        analisis_ia = service.generar_analisis_ia(datos_estudiante, probabilidad_riesgo)
        detalles_matematicos = service.calcular_detalles_matematicos(
            features_scaled, probabilidad_riesgo
        )

        promedio_aprobados = service.get_promedio_aprobados()
        datos_radar = {
            "labels": ["Corte 1", "Corte 2", "Corte final", "Total"],
            "estudiante": [
                estudiante.nota_corte_1,
                estudiante.nota_corte_2,
                estudiante.nota_corte_final,
                estudiante.nota_total,
            ],
            "promedio_aprobado": [
                promedio_aprobados["nota_corte_1"],
                promedio_aprobados["nota_corte_2"],
                promedio_aprobados["nota_corte_final"],
                promedio_aprobados["nota_total"],
            ],
        }

        return PredictionOutput(
            probabilidad_riesgo=probabilidad_riesgo,
            porcentaje_riesgo=probabilidad_riesgo * 100,
            nivel_riesgo=nivel_riesgo,
            analisis_ia=analisis_ia,
            datos_radar=datos_radar,
            detalles_matematicos=detalles_matematicos,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Error al procesar la predicción: {exc}",
        ) from exc


@router.post("/predict/cohort", response_model=CohortRiskOutput)
async def predecir_riesgo_cohorte(
    data: CohortRiskInput,
    student_id: Optional[UUID] = None,
    service: AcademicRiskService = Depends(get_ml_service),
    ml_app_service: MLApplicationService = Depends(get_ml_application_service),
):
    """Predicción de riesgo por cohorte (parcial + seguimiento + asistencia)."""
    try:
        if student_id is not None:
            result = await ml_app_service.predict_cohort_with_consent_check(
                student_id=student_id,
                cohort_key=data.cohort_key,
                nota_parcial=data.nota_parcial,
                promedio_seguimiento=data.promedio_seguimiento,
                porcentaje_asistencia=data.porcentaje_asistencia,
            )
        else:
            result = service.predict_cohort_risk(
                cohort_key=data.cohort_key,
                nota_parcial=data.nota_parcial,
                promedio_seguimiento=data.promedio_seguimiento,
                porcentaje_asistencia=data.porcentaje_asistencia,
            )

        return CohortRiskOutput(
            cohort_key=result["cohort_key"],
            cohort_name=result["cohort_name"],
            probabilidad_riesgo=result["probability"],
            porcentaje_riesgo=result["probability"] * 100,
            nivel_riesgo=result["risk_level"],
            datos_cohorte={
                "nota_parcial": data.nota_parcial,
                "promedio_seguimiento": data.promedio_seguimiento,
                "porcentaje_asistencia": data.porcentaje_asistencia,
            },
            detalles_modelo=result["component_scores"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Error al procesar la predicción por cohorte: {exc}",
        ) from exc


@router.post("/chat", response_model=ChatOutput)
async def chat_consejero(chat_input: ChatInput):
    """Respuesta breve de orientación basada en notas por cohorte."""
    datos = chat_input.datos_estudiante
    riesgo = (chat_input.prediccion_actual or {}).get("porcentaje_riesgo")

    respuesta = (
        f"Tus notas actuales son: Corte 1 {datos.nota_corte_1:.1f}, "
        f"Corte 2 {datos.nota_corte_2:.1f}, Corte final {datos.nota_corte_final:.1f}, "
        f"Total {datos.nota_total:.1f}.\n"
    )

    if riesgo is None:
        respuesta += "Te recomiendo correr la predicción para priorizar qué cohorte reforzar primero."
    elif riesgo >= 70:
        respuesta += "Riesgo alto: enfócate de inmediato en el cohorte con menor nota y plan de recuperación semanal."
    elif riesgo >= 40:
        respuesta += "Riesgo medio: estás a tiempo, prioriza subir al menos 0.5 en el cohorte más bajo."
    else:
        respuesta += "Riesgo bajo: mantén constancia y protege el rendimiento en el cohorte final."

    return ChatOutput(respuesta=respuesta)
