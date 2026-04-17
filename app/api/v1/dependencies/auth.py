"""
Auth dependencies — FastAPI dependency injection for authentication and authorization.

Provides:
- ``CurrentUser``: Pydantic model representing the authenticated user.
- ``get_current_user``: Extracts and validates the JWT from the Authorization header.
- ``require_roles``: Factory that returns a dependency enforcing role-based access.
- ``require_self_or_roles``: Dependency allowing access to own data, ADMIN, or
  PROFESSOR with RB-04 visibility.

Requirements: 3.1–3.6, 5.1–5.6, 6.5, 8.2
"""

from typing import Callable, List
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Path
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.services.token_service import TokenService
from app.core.config import settings
from app.domain.enums import RoleEnum
from app.domain.exceptions import InvalidTokenError, TokenExpiredError
from app.infrastructure.database import get_session
from app.infrastructure.models.enrollment import Enrollment
from app.infrastructure.models.professor_course import ProfessorCourse


# ---------------------------------------------------------------------------
# Singleton-ish TokenService wired to app settings
# ---------------------------------------------------------------------------

def get_token_service() -> TokenService:
    """Provide a ``TokenService`` configured from application settings."""
    return TokenService(
        secret_key=settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
        access_expire_minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES,
        refresh_expire_days=settings.REFRESH_TOKEN_EXPIRE_DAYS,
    )


# ---------------------------------------------------------------------------
# CurrentUser model
# ---------------------------------------------------------------------------

class CurrentUser(BaseModel):
    """Represents the authenticated user extracted from the JWT access token."""

    id: UUID
    role: RoleEnum


# ---------------------------------------------------------------------------
# get_current_user dependency
# ---------------------------------------------------------------------------

async def get_current_user(
    authorization: str | None = Header(default=None, alias="Authorization"),
    token_service: TokenService = Depends(get_token_service),
) -> CurrentUser:
    """Extract and validate the JWT Bearer token from the Authorization header.

    Returns a ``CurrentUser`` on success.

    Raises:
        HTTPException 401: When the header is missing, the token is expired,
            malformed, has a wrong type, or an invalid signature.
    """
    if authorization is None:
        raise HTTPException(status_code=401, detail="Token no proporcionado")

    # Expect "Bearer <token>"
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Token no proporcionado")

    token = parts[1]

    try:
        payload = token_service.decode_token(token)
    except TokenExpiredError:
        raise HTTPException(status_code=401, detail="Token expirado")
    except InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token inválido")

    # Only access tokens are accepted for endpoint protection
    if payload.type != "access":
        raise HTTPException(status_code=401, detail="Token inválido")

    return CurrentUser(id=UUID(payload.sub), role=payload.role)


# ---------------------------------------------------------------------------
# require_roles dependency factory
# ---------------------------------------------------------------------------

def require_roles(*roles: RoleEnum) -> Callable:
    """Return a FastAPI dependency that enforces role-based access.

    ADMIN always has access regardless of the ``roles`` list.

    Usage::

        @router.get("/admin-only", dependencies=[Depends(require_roles(RoleEnum.ADMIN))])
        async def admin_only(): ...
    """
    allowed: set[RoleEnum] = set(roles)

    async def _guard(
        current_user: CurrentUser = Depends(get_current_user),
    ) -> CurrentUser:
        if current_user.role == RoleEnum.ADMIN:
            return current_user
        if current_user.role not in allowed:
            raise HTTPException(
                status_code=403, detail="No tiene permisos para esta acción"
            )
        return current_user

    return _guard


# ---------------------------------------------------------------------------
# require_self_or_roles dependency
# ---------------------------------------------------------------------------

async def require_self_or_roles(
    user_id: UUID = Path(...),
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> CurrentUser:
    """Allow access when the user is accessing their own data, is ADMIN,
    or is a PROFESSOR whose courses include the target student (RB-04).

    This dependency reads ``user_id`` from the path parameter automatically.

    Raises:
        HTTPException 403: When none of the access conditions are met.
    """
    # Self-access: any user can view their own data
    if current_user.id == user_id:
        return current_user

    # ADMIN: full access
    if current_user.role == RoleEnum.ADMIN:
        return current_user

    # PROFESSOR: allowed only if the target student is enrolled in one of
    # the professor's assigned courses (RB-04).
    if current_user.role == RoleEnum.PROFESSOR:
        stmt = (
            select(Enrollment.id)
            .join(
                ProfessorCourse,
                ProfessorCourse.course_id == Enrollment.course_id,
            )
            .where(
                ProfessorCourse.professor_id == current_user.id,
                Enrollment.student_id == user_id,
            )
            .limit(1)
        )
        result = await session.execute(stmt)
        if result.scalar_one_or_none() is not None:
            return current_user

    raise HTTPException(
        status_code=403, detail="No tiene permisos para esta acción"
    )
