"""
AuthService — orchestrates authentication flow using pluggable providers.

Responsible for:
- Delegating credential verification to an IAuthProvider.
- Checking user status (active/inactive) before issuing tokens.
- Generating access + refresh token pairs via TokenService.
- Handling token refresh flow (decode, verify type, re-issue).
- Stateless logout confirmation.

Requirements: 1.1, 1.4, 4.1, 4.2, 4.3, 4.4, 9.1, 9.2
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from app.application.schemas.auth import TokenResponse
from app.domain.enums import UserStatusEnum
from app.domain.exceptions import AuthenticationError, InvalidTokenError

if TYPE_CHECKING:
    from app.application.services.token_service import TokenService
    from app.domain.interfaces.auth_provider import IAuthProvider


class AuthService:
    """Orchestrates authentication flow using pluggable providers."""

    def __init__(
        self,
        provider: IAuthProvider,
        token_service: TokenService,
    ) -> None:
        self._provider = provider
        self._token_service = token_service

    async def login(self, email: str, password: str) -> TokenResponse:
        """Authenticate a user and return a token pair.

        Delegates credential verification to the configured IAuthProvider,
        then checks that the user account is active before issuing tokens.

        Args:
            email: User email address.
            password: Plain-text password.

        Returns:
            TokenResponse with access_token, refresh_token, token_type,
            and expires_in (seconds).

        Raises:
            AuthenticationError: When credentials are invalid (401) or
                the account is inactive (403).
        """
        user = await self._provider.authenticate(email=email, password=password)

        if user.status != UserStatusEnum.ACTIVE:
            raise AuthenticationError("Cuenta desactivada", 403)

        access_token = self._token_service.create_access_token(user.id, user.role)
        refresh_token = self._token_service.create_refresh_token(user.id, user.role)

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=self._token_service._access_expire_minutes * 60,
        )

    async def refresh(self, refresh_token: str) -> TokenResponse:
        """Issue a new token pair from a valid refresh token.

        Decodes the token, verifies it is a refresh token (not access),
        and generates a fresh access + refresh pair.

        Args:
            refresh_token: JWT refresh token string.

        Returns:
            TokenResponse with new access_token and refresh_token.

        Raises:
            TokenExpiredError: When the refresh token has expired.
            InvalidTokenError: When the token is malformed, has a bad
                signature, or is not a refresh token.
        """
        payload = self._token_service.decode_token(refresh_token)

        if payload.type != "refresh":
            raise InvalidTokenError("Token inválido")

        user_id = UUID(payload.sub)
        role = payload.role

        access_token = self._token_service.create_access_token(user_id, role)
        new_refresh_token = self._token_service.create_refresh_token(user_id, role)

        return TokenResponse(
            access_token=access_token,
            refresh_token=new_refresh_token,
            token_type="bearer",
            expires_in=self._token_service._access_expire_minutes * 60,
        )

    def logout(self) -> dict:
        """Return a stateless logout confirmation.

        The actual token invalidation is handled client-side by
        discarding the tokens. The server relies on short-lived
        access tokens for security.

        Returns:
            Dict with confirmation message.
        """
        return {"message": "Sesión cerrada exitosamente"}
