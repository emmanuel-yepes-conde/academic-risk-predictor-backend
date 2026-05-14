"""
ConsentRouter — endpoints del consentimiento ML para el estudiante autenticado.

Endpoints:
- GET  /consents/me       → Estado del consentimiento ML del estudiante actual.
- POST /consents/me       → Registra aceptación de los términos vigentes.

La aceptación se materializa como un nuevo registro inmutable en la tabla
``consents`` (ver ``ConsentRepository.register_consent``). La revocación se
modela registrando un nuevo consentimiento con ``accepted=False``.

Reglas de autorización:
- Solo el rol STUDENT puede consultar/registrar su propio consentimiento.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies.auth import CurrentUser, require_roles
from app.application.schemas.consent import (
    ConsentAcceptRequest,
    ConsentRead,
    ConsentStatus,
)
from app.core.config import settings
from app.domain.enums import RoleEnum
from app.infrastructure.database import get_session
from app.infrastructure.repositories.consent_repository import ConsentRepository

router = APIRouter()


def _get_repo(session: AsyncSession = Depends(get_session)) -> ConsentRepository:
    return ConsentRepository(session)


@router.get(
    "/consents/me",
    response_model=ConsentStatus,
    status_code=200,
    summary="Estado del consentimiento ML del estudiante autenticado",
    tags=["Consentimiento"],
)
async def get_my_consent(
    current_user: CurrentUser = Depends(require_roles(RoleEnum.STUDENT)),
    repo: ConsentRepository = Depends(_get_repo),
) -> ConsentStatus:
    consent = await repo.get_consent(current_user.id)
    has_accepted = (
        consent is not None
        and consent.accepted
        and consent.terms_version == settings.TERMS_VERSION
    )
    return ConsentStatus(
        has_accepted=has_accepted,
        current_terms_version=settings.TERMS_VERSION,
        consent=ConsentRead.model_validate(consent) if consent is not None else None,
    )


@router.post(
    "/consents/me",
    response_model=ConsentRead,
    status_code=201,
    summary="Registra el consentimiento ML del estudiante autenticado",
    tags=["Consentimiento"],
)
async def register_my_consent(
    body: ConsentAcceptRequest,
    current_user: CurrentUser = Depends(require_roles(RoleEnum.STUDENT)),
    repo: ConsentRepository = Depends(_get_repo),
) -> ConsentRead:
    if not body.accepted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Debe aceptar los términos y condiciones para usar el aplicativo",
        )
    consent = await repo.register_consent(
        student_id=current_user.id,
        version=settings.TERMS_VERSION,
        accepted=True,
    )
    return ConsentRead.model_validate(consent)
