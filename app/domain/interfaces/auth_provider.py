"""Interface for authentication providers (Strategy pattern)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.infrastructure.models.user import User


class IAuthProvider(ABC):
    """Abstract authentication provider.

    Implementations handle a specific authentication method
    (credentials, Microsoft SSO, Google SSO, etc.) and return
    a validated User entity on success.
    """

    @abstractmethod
    async def authenticate(self, **kwargs: Any) -> User:
        """Authenticate a user and return the User entity.

        Raises:
            AuthenticationError: When authentication fails.
        """
        ...
