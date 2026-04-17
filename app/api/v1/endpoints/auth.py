"""
AuthRouter — endpoints de autenticación JWT.

Endpoints públicos:
- POST /auth/login   — autenticación por credenciales (email + password)
- POST /auth/refresh — renovación de access token mediante refresh token

Endpoint protegido:
- POST /auth/logout  — confirmación stateless de cierre de sesión

Requirements: 1.1, 4.1, 6.7, 9.1, 9.2, 9.3
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.schemas.auth import (
    LoginRequest,
    LogoutResponse,
    RefreshRequest,
    TokenResponse,
)
from app.application.services.auth_service import AuthService
from app.application.services.token_service import TokenService
from app.api.v1.dependencies.auth import (
    CurrentUser,
    get_current_user,
    get_token_service,
)
from app.infrastructure.auth.credential_provider import CredentialAuthProvider
from app.infrastructure.database import get_session
from app.infrastructure.repositories.user_repository import UserRepository

router = APIRouter()


# ---------------------------------------------------------------------------
# Dependency helpers
# ---------------------------------------------------------------------------

def _get_auth_service(
    session: AsyncSession = Depends(get_session),
    token_service: TokenService = Depends(get_token_service),
) -> AuthService:
    """Wire up AuthService with its dependencies."""
    user_repo = UserRepository(session)
    provider = CredentialAuthProvider(user_repo)
    return AuthService(provider=provider, token_service=token_service)


# ---------------------------------------------------------------------------
# Public endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/auth/login",
    response_model=TokenResponse,
    status_code=200,
    summary="Iniciar sesión",
    description=(
        "Autentica un usuario con correo electrónico y contraseña. "
        "Retorna un par de tokens JWT (access + refresh)."
    ),
    tags=["Autenticación"],
)
async def login(
    body: LoginRequest,
    auth_service: AuthService = Depends(_get_auth_service),
) -> TokenResponse:
    return await auth_service.login(body.email, body.password)


@router.post(
    "/auth/refresh",
    response_model=TokenResponse,
    status_code=200,
    summary="Renovar token de acceso",
    description=(
        "Emite un nuevo par de tokens JWT a partir de un refresh token válido. "
        "El refresh token anterior queda implícitamente reemplazado."
    ),
    tags=["Autenticación"],
)
async def refresh(
    body: RefreshRequest,
    auth_service: AuthService = Depends(_get_auth_service),
) -> TokenResponse:
    return await auth_service.refresh(body.refresh_token)


# ---------------------------------------------------------------------------
# Protected endpoint
# ---------------------------------------------------------------------------

@router.post(
    "/auth/logout",
    response_model=LogoutResponse,
    status_code=200,
    summary="Cerrar sesión",
    description=(
        "Cierre de sesión stateless. El servidor confirma la acción; "
        "la invalidación real ocurre en el cliente al descartar los tokens."
    ),
    tags=["Autenticación"],
)
async def logout(
    current_user: CurrentUser = Depends(get_current_user),
    auth_service: AuthService = Depends(_get_auth_service),
) -> LogoutResponse:
    result = auth_service.logout()
    return LogoutResponse(**result)
