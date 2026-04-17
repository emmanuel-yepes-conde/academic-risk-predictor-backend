"""
ConsentService — verifica el consentimiento ML de un estudiante (Req 8.2, 8.3).
"""

from uuid import UUID

from fastapi import HTTPException

from app.domain.interfaces.consent_repository import IConsentRepository


class ConsentService:
    """
    Servicio de aplicación que encapsula la lógica de verificación de consentimiento ML.
    Recibe IConsentRepository como dependencia inyectada (DIP).
    """

    def __init__(self, consent_repo: IConsentRepository) -> None:
        self._consent_repo = consent_repo

    async def verify_ml_consent(self, student_id: UUID) -> None:
        """
        Verifica que el estudiante haya otorgado consentimiento para el procesamiento ML.

        Raises:
            HTTPException(403): Si no existe registro de consentimiento o accepted == False.
        """
        consent = await self._consent_repo.get_consent(student_id)

        if consent is None or not consent.accepted:
            raise HTTPException(
                status_code=403,
                detail="El estudiante no ha otorgado consentimiento para el procesamiento de datos ML",
            )
