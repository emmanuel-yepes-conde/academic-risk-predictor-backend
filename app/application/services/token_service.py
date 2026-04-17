"""
Token Service — creates and decodes JWT tokens using PyJWT.

Responsible for:
- Encoding access and refresh tokens with claims (sub, role, type, exp, iat).
- Decoding tokens with signature and expiration validation.
- Raising typed exceptions (TokenExpiredError, InvalidTokenError) on failure.

Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6
"""

from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt

from app.domain.enums import RoleEnum
from app.domain.exceptions import InvalidTokenError, TokenExpiredError
from app.domain.value_objects.token import TokenPayload


class TokenService:
    """Creates and decodes JWT tokens using PyJWT and HS256."""

    def __init__(
        self,
        secret_key: str,
        algorithm: str = "HS256",
        access_expire_minutes: int = 30,
        refresh_expire_days: int = 7,
    ) -> None:
        self._secret_key = secret_key
        self._algorithm = algorithm
        self._access_expire_minutes = access_expire_minutes
        self._refresh_expire_days = refresh_expire_days

    # ------------------------------------------------------------------
    # Token creation
    # ------------------------------------------------------------------

    def create_access_token(self, user_id: UUID, role: RoleEnum) -> str:
        """Create a short-lived access token.

        Claims: sub, role, type="access", exp, iat.
        """
        now = datetime.now(timezone.utc)
        claims = {
            "sub": str(user_id),
            "role": role.value,
            "type": "access",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=self._access_expire_minutes)).timestamp()),
        }
        return jwt.encode(claims, self._secret_key, algorithm=self._algorithm)

    def create_refresh_token(self, user_id: UUID, role: RoleEnum) -> str:
        """Create a long-lived refresh token.

        Claims: sub, role, type="refresh", exp, iat.
        """
        now = datetime.now(timezone.utc)
        claims = {
            "sub": str(user_id),
            "role": role.value,
            "type": "refresh",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(days=self._refresh_expire_days)).timestamp()),
        }
        return jwt.encode(claims, self._secret_key, algorithm=self._algorithm)

    # ------------------------------------------------------------------
    # Token decoding / validation
    # ------------------------------------------------------------------

    def decode_token(self, token: str) -> TokenPayload:
        """Decode and validate a JWT token.

        Returns a ``TokenPayload`` value object on success.

        Raises:
            TokenExpiredError: If the token has expired.
            InvalidTokenError: If the token is malformed, has a bad signature,
                or is missing required claims.
        """
        try:
            payload = jwt.decode(
                token,
                self._secret_key,
                algorithms=[self._algorithm],
                options={"require": ["sub", "role", "type", "exp", "iat"]},
            )
        except jwt.ExpiredSignatureError:
            raise TokenExpiredError()
        except jwt.PyJWTError:
            raise InvalidTokenError()

        # Validate role value against the enum
        try:
            role = RoleEnum(payload["role"])
        except (ValueError, KeyError):
            raise InvalidTokenError()

        return TokenPayload(
            sub=payload["sub"],
            role=role,
            type=payload["type"],
            exp=datetime.fromtimestamp(payload["exp"], tz=timezone.utc),
            iat=datetime.fromtimestamp(payload["iat"], tz=timezone.utc),
        )
