"""
MLService de capa de aplicación — orquesta verificación de consentimiento y predicción (Req 8.2, 8.3).
Envuelve AcademicRiskService (infraestructura ML) e inyecta ConsentService.
"""

from uuid import UUID
from typing import Dict, List

from app.application.services.consent_service import ConsentService
from app.services.ml_service import AcademicRiskService


class MLApplicationService:
    """
    Servicio de aplicación para predicción de riesgo académico con consent gate.

    Antes de delegar la predicción al motor ML, verifica que el estudiante
    haya otorgado consentimiento explícito (Consent.accepted == True).
    Si no, lanza HTTPException 403.
    """

    def __init__(
        self,
        ml_service: AcademicRiskService,
        consent_service: ConsentService,
    ) -> None:
        self._ml = ml_service
        self._consent = consent_service

    async def predict_with_consent_check(
        self,
        student_id: UUID,
        features: List[float],
    ) -> Dict:
        """
        Verifica consentimiento y ejecuta la predicción ML.

        Args:
            student_id: UUID del estudiante cuyo consentimiento se verifica.
            features: Vector de características para el modelo ML.

        Returns:
            Resultado de la predicción (probability, risk_level, scaled_features).

        Raises:
            HTTPException(403): Si el estudiante no ha otorgado consentimiento.
        """
        await self._consent.verify_ml_consent(student_id)
        return self._ml.predict(features)
