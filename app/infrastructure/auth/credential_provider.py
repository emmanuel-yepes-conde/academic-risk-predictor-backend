"""Authentication provider that validates email + password credentials."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.core.security import verify_password
from app.domain.exceptions import AuthenticationError
from app.domain.interfaces.auth_provider import IAuthProvider

if TYPE_CHECKING:
    from app.domain.interfaces.user_repository import IUserRepository
    from app.infrastructure.models.user import User


class CredentialAuthProvider(IAuthProvider):
    """Authenticates users via email + password against the database."""

    def __init__(self, user_repo: IUserRepository) -> None:
        self._user_repo = user_repo

    async def authenticate(self, **kwargs: Any) -> User:
        """Authenticate a user with email and password.

        Args:
            email: User email address.
            password: Plain-text password to verify.

        Returns:
            The authenticated User entity.

        Raises:
            AuthenticationError: When the email does not exist, the password
                is incorrect, or the user has no password_hash (SSO-only).
        """
        email: str | None = kwargs.get("email")
        password: str | None = kwargs.get("password")

        if not email or not password:
            raise AuthenticationError("Credenciales inválidas", 401)

        user = await self._user_repo.get_by_email(email)

        if user is None:
            raise AuthenticationError("Credenciales inválidas", 401)

        if not user.password_hash:
            raise AuthenticationError("Credenciales inválidas", 401)

        if not verify_password(password, user.password_hash):
            raise AuthenticationError("Credenciales inválidas", 401)

        return user
